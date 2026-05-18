from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
import torch.nn as nn

from backend.sar_unet_training import (
    _component_summaries,
    _postprocess_binary_mask,
    _validation_quality_gate,
    build_sar_validation_error_diagnostics,
    evaluate_sar_checkpoint,
    evaluate_sar_checkpoint_scene_blended,
    train_sar_unet,
)


class _TinyBiTemporalModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(4, 8, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(8, 1, kernel_size=1),
        )

    def forward(self, pre: torch.Tensor, post: torch.Tensor) -> torch.Tensor:
        return self.encoder(torch.cat([pre, post], dim=1))


class SarUnetTrainingTests(unittest.TestCase):
    def test_validation_quality_gate_rejects_inflated_positive_rate(self) -> None:
        gate = _validation_quality_gate(
            [{
                'scene_id': 'scene-1',
                'predicted_positive_rate': 0.45,
                'truth_positive_rate': 0.01,
                'positive_rate_ratio': 45.0,
            }],
            max_positive_rate_ratio=20.0,
            max_positive_rate_absolute=0.15,
        )

        self.assertFalse(gate['passed'])
        self.assertEqual(gate['blocked_gate'], 'validation_positive_rate')
        self.assertEqual(gate['failures'][0]['scene_id'], 'scene-1')

    def test_validation_quality_gate_rejects_missing_precision_floor(self) -> None:
        gate = _validation_quality_gate(
            [{
                'scene_id': 'scene-1',
                'predicted_positive_rate': 0.01,
                'truth_positive_rate': 0.01,
                'positive_rate_ratio': 1.0,
            }],
            max_positive_rate_ratio=20.0,
            max_positive_rate_absolute=0.15,
            threshold_metrics=[
                {'threshold': 0.95, 'precision': 0.38, 'recall': 0.72},
                {'threshold': 0.99, 'precision': 0.41, 'recall': 0.60},
            ],
            precision_floor=0.60,
        )

        self.assertFalse(gate['passed'])
        self.assertEqual(gate['blocked_gate'], 'precision_floor')
        self.assertFalse(gate['precision_floor_met'])
        self.assertEqual(gate['max_precision'], 0.41)
        self.assertEqual(gate['best_precision_threshold'], 0.99)

    def test_validation_quality_gate_rejects_recall_floor_after_postprocess_selection(self) -> None:
        gate = _validation_quality_gate(
            [{
                'scene_id': 'scene-1',
                'predicted_positive_rate': 0.01,
                'truth_positive_rate': 0.01,
                'positive_rate_ratio': 1.0,
            }],
            max_positive_rate_ratio=20.0,
            max_positive_rate_absolute=0.15,
            threshold_metrics=[
                {'threshold': 0.997, 'precision': 0.65, 'recall': 0.45},
                {'threshold': 0.999, 'precision': 0.80, 'recall': 0.20},
            ],
            precision_floor=0.60,
            recall_floor=0.50,
            selection_floor_met=False,
        )

        self.assertFalse(gate['passed'])
        self.assertEqual(gate['blocked_gate'], 'recall_floor')
        self.assertTrue(gate['precision_floor_met'])
        self.assertFalse(gate['recall_floor_met'])
        self.assertEqual(gate['failures'][0]['reason'], 'recall_floor_not_met')
        self.assertEqual(gate['best_precision_recall'], 0.20)

    def test_validation_quality_gate_reports_joint_pass_fields(self) -> None:
        gate = _validation_quality_gate(
            [{
                'scene_id': 'scene-1',
                'predicted_positive_rate': 0.01,
                'truth_positive_rate': 0.01,
                'positive_rate_ratio': 1.0,
            }],
            max_positive_rate_ratio=20.0,
            max_positive_rate_absolute=0.15,
            threshold_metrics=[
                {'threshold': 0.995, 'precision': 0.62, 'recall': 0.51},
            ],
            validation_metrics={'threshold': 0.995, 'precision': 0.62, 'recall': 0.51},
            precision_floor=0.60,
            recall_floor=0.50,
            selection_floor_met=True,
        )

        self.assertTrue(gate['passed'])
        self.assertTrue(gate['precision_floor_met'])
        self.assertTrue(gate['recall_floor_met'])
        self.assertTrue(gate['joint_floor_met'])
        self.assertEqual(gate['selected_threshold'], 0.995)

    def test_train_sar_unet_writes_status_before_materialization_and_error_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            progress_events: list[dict[str, object]] = []

            def _fail_materialization(**kwargs: object) -> dict[str, object]:
                artifact_dir = Path(kwargs['output_root']).parent
                status_path = artifact_dir / 'train_sar_unet_status.json'
                self.assertTrue(status_path.exists())
                status = json.loads(status_path.read_text(encoding='utf-8'))
                self.assertEqual(status['phase'], 'materializing_dataset')
                raise RuntimeError('materialization failed for unit test')

            request = {
                'training_manifest_path': '/artifacts/european-shadow-sar/missing.json',
                'candidate_model_version': 'swin-shadow-unit-failure',
                'model_family': 'swinunet_tiny_diff',
                'patch_size': 4,
                'stride': 4,
            }

            with patch('backend.sar_unet_training.materialize_sar_training_dataset', side_effect=_fail_materialization):
                with self.assertRaisesRegex(RuntimeError, 'materialization failed'):
                    train_sar_unet(
                        request,
                        artifact_root=root / 'artifacts',
                        device='cpu',
                        progress_callback=progress_events.append,
                    )

            artifact_dirs = [path for path in (root / 'artifacts').iterdir() if path.is_dir()]
            self.assertEqual(len(artifact_dirs), 1)
            status_payload = json.loads((artifact_dirs[0] / 'train_sar_unet_status.json').read_text(encoding='utf-8'))
            error_payload = json.loads((artifact_dirs[0] / 'train_sar_unet_error.json').read_text(encoding='utf-8'))
            self.assertEqual(status_payload['phase'], 'failed')
            self.assertEqual(error_payload['status'], 'failed')
            self.assertEqual(error_payload['error_type'], 'RuntimeError')
            self.assertIn('materialization failed', error_payload['failure_reason'])
            self.assertIn('initializing', [event['phase'] for event in progress_events])
            self.assertIn('materializing_dataset', [event['phase'] for event in progress_events])

    def test_postprocess_binary_mask_noops_when_disabled(self) -> None:
        predictions = np.array([[True, False], [True, True]])

        processed = _postprocess_binary_mask(predictions)

        np.testing.assert_array_equal(processed, predictions)

    def test_postprocess_binary_mask_removes_small_components(self) -> None:
        predictions = np.zeros((5, 5), dtype=bool)
        predictions[0, 0] = True
        predictions[2:4, 2:4] = True

        processed = _postprocess_binary_mask(predictions, min_component_area_px=3)

        self.assertFalse(bool(processed[0, 0]))
        self.assertEqual(int(processed.sum()), 4)

    def test_component_summaries_rank_largest_components(self) -> None:
        mask = np.zeros((6, 6), dtype=bool)
        mask[0, 0] = True
        mask[2:5, 2:5] = True

        summaries = _component_summaries(
            mask,
            scene_id='scene-1',
            patch_id='patch-1',
            component_type='false_negative',
            limit=2,
        )

        self.assertEqual([row['pixel_count'] for row in summaries], [9, 1])
        self.assertEqual(summaries[0]['scene_id'], 'scene-1')
        self.assertEqual(summaries[0]['component_type'], 'false_negative')

    def test_scene_blended_checkpoint_evaluation_counts_full_scene_pixels_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            checkpoint_path = root / 'sar_model.pt'
            checkpoint_path.write_bytes(b'placeholder')
            truth_path = root / 'truth.npy'
            np.save(truth_path, np.array([[1, 0], [0, 1]], dtype=np.float32))
            request = {
                'training_manifest': {
                    'version': 'sar_training_manifest_v1',
                    'dataset_version': 'scene-blended-unit-v1',
                    'scenes': [
                        {
                            'source_dataset': 'avalcd',
                            'event_id': 'evt-train-1',
                            'scene_id': 'train-scene',
                            'region_key': 'livigno',
                            'split': 'train',
                            'stack_ref': 'unused-train-stack.npy',
                            'truth_mask_ref': str(truth_path),
                        },
                        {
                            'source_dataset': 'avalcd',
                            'event_id': 'evt-val-1',
                            'scene_id': 'val-scene',
                            'region_key': 'livigno',
                            'split': 'val',
                            'stack_ref': 'unused-val-stack.npy',
                            'truth_mask_ref': str(truth_path),
                        },
                    ],
                },
                'checkpoint_path': str(checkpoint_path),
                'candidate_model_version': 'scene-blended-unit-model',
                'source_key': 'avalcd_zenodo_v1',
                'license_review_id': 'license-review-unit',
                'model_family': 'swinunet_tiny_diff',
                'patch_size': 4,
                'stride': 4,
                'threshold_grid': [0.5],
                'precision_floor': 0.5,
                'postprocess_min_component_area_px': 0,
                'postprocess_apply_to_threshold_selection': True,
                'postprocess_recall_floor': 0.5,
                'export_validation_prediction_artifact': True,
            }

            with patch('backend.sar_unet_worker.build_unet_model') as build_mock, \
                    patch('backend.sar_unet_worker.predict_scene_probability_mask') as predict_mock:
                build_mock.return_value = type('Loaded', (), {
                    'normalization': {'img_mean': np.array([0, 0]), 'img_std': np.array([1, 1])},
                })()
                predict_mock.return_value = np.array([[0.9, 0.1], [0.1, 0.9]], dtype=np.float32)
                report = evaluate_sar_checkpoint_scene_blended(
                    request,
                    artifact_root=root / 'artifacts',
                    device='cpu',
                )

            self.assertEqual(report['status'], 'ok')
            self.assertEqual(report['evaluation_mode'], 'scene_blended')
            artifact = json.loads(Path(report['sar_prediction_artifact_path']).read_text(encoding='utf-8'))
            self.assertEqual(artifact['evaluation_mode'], 'scene_blended')
            self.assertEqual(artifact['metrics']['tp'], 2)
            self.assertEqual(artifact['metrics']['tn'], 2)
            self.assertEqual(artifact['scene_breakdown'][0]['total_pixels'], 4)

    def test_train_sar_unet_persists_checkpoint_metadata_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            train_stack_path = root / 'train_stack.npz'
            train_mask_path = root / 'train_mask.npz'
            val_stack_path = root / 'val_stack.npz'
            val_mask_path = root / 'val_mask.npz'

            train_stack = np.stack([
                np.ones((8, 8), dtype=np.float32) * 1.0,
                np.ones((8, 8), dtype=np.float32) * 2.0,
                np.ones((8, 8), dtype=np.float32) * 3.0,
                np.ones((8, 8), dtype=np.float32) * 4.0,
            ], axis=0)
            val_stack = np.stack([
                np.ones((8, 8), dtype=np.float32) * 1.5,
                np.ones((8, 8), dtype=np.float32) * 2.5,
                np.ones((8, 8), dtype=np.float32) * 3.5,
                np.ones((8, 8), dtype=np.float32) * 4.5,
            ], axis=0)
            train_mask = np.zeros((8, 8), dtype=np.float32)
            val_mask = np.zeros((8, 8), dtype=np.float32)
            train_mask[:4, :4] = 1.0
            val_mask[4:, 4:] = 1.0
            scratch_dataset_root = root / 'scratch_sar_training_dataset'

            np.savez_compressed(train_stack_path, stack=train_stack)
            np.savez_compressed(train_mask_path, mask=train_mask)
            np.savez_compressed(val_stack_path, stack=val_stack)
            np.savez_compressed(val_mask_path, mask=val_mask)

            request = {
                'training_manifest': {
                    'version': 'sar_training_manifest_v1',
                    'dataset_version': 'sar-train-unit-v1',
                    'scenes': [
                        {
                            'source_dataset': 'avalcd',
                            'event_id': 'evt-train-1',
                            'scene_id': 'scene-train-1',
                            'region_key': 'livigno',
                            'split': 'train',
                            'stack_ref': str(train_stack_path),
                            'truth_mask_ref': str(train_mask_path),
                        },
                        {
                            'source_dataset': 'avalcd',
                            'event_id': 'evt-val-1',
                            'scene_id': 'scene-val-1',
                            'region_key': 'livigno',
                            'split': 'val',
                            'stack_ref': str(val_stack_path),
                            'truth_mask_ref': str(val_mask_path),
                        },
                    ],
                },
                'model_family': 'swinunet_tiny_diff',
                'patch_size': 4,
                'stride': 4,
                'epochs': 2,
                'batch_size': 2,
                'learning_rate': 0.01,
                'patience': 2,
                'candidate_model_version': 'swin-shadow-unit-v1',
                'loss': 'focal_tversky',
                'seed': 7,
                'source_key': 'avalcd_zenodo_v1',
                'license_review_id': 'license-review-unit',
                'materialized_dataset_root': str(scratch_dataset_root),
                'export_validation_prediction_artifact': True,
            }

            with patch('backend.sar_unet_training.build_model_architecture', side_effect=lambda *args, **kwargs: _TinyBiTemporalModel()), \
                    patch('backend.sar_unet_training._validation_quality_gate', return_value={'passed': True, 'blocked_gate': None, 'failures': []}):
                progress_events: list[dict[str, object]] = []
                report = train_sar_unet(
                    request,
                    artifact_root=root / 'artifacts',
                    device='cpu',
                    progress_callback=progress_events.append,
                )

            self.assertEqual(report['status'], 'ok')
            self.assertEqual(report['request_type'], 'train_sar_unet')
            self.assertEqual(report['candidate_model_version'], 'swin-shadow-unit-v1')
            self.assertTrue(Path(report['artifact_dir']).exists())
            self.assertTrue(Path(report['model_checkpoint_path']).exists())
            self.assertEqual(report['dataset_version'], 'sar-train-unit-v1')
            self.assertEqual(report['train_events'], ['evt-train-1'])
            self.assertEqual(report['val_events'], ['evt-val-1'])
            self.assertEqual(report['materialized_dataset_root'], str(scratch_dataset_root))
            self.assertTrue(scratch_dataset_root.exists())
            self.assertFalse((Path(report['artifact_dir']) / 'sar_training_dataset').exists())
            self.assertGreaterEqual(report['best_threshold'], 0.05)
            self.assertLessEqual(report['best_threshold'], 0.95)
            self.assertTrue(Path(report['sar_prediction_artifact_path']).exists())
            status_payload = json.loads((Path(report['artifact_dir']) / 'train_sar_unet_status.json').read_text(encoding='utf-8'))
            self.assertEqual(status_payload['phase'], 'completed')
            self.assertEqual(status_payload['candidate_model_version'], 'swin-shadow-unit-v1')
            progress_phases = [event['phase'] for event in progress_events]
            self.assertIn('initializing', progress_phases)
            self.assertIn('epoch_started', progress_phases)
            self.assertIn('writing_metrics', progress_phases)
            self.assertEqual(progress_phases[-1], 'completed')

            checkpoint_payload = torch.load(report['model_checkpoint_path'], map_location='cpu')
            metadata = checkpoint_payload['metadata']
            self.assertEqual(metadata['model_family'], 'swinunet_tiny_diff')
            self.assertEqual(metadata['candidate_model_version'], 'swin-shadow-unit-v1')
            self.assertEqual(metadata['dataset_version'], 'sar-train-unit-v1')
            self.assertIn('best_threshold', metadata)
            self.assertIn('validation_auprc', metadata)
            prediction_artifact = json.loads(Path(report['sar_prediction_artifact_path']).read_text(encoding='utf-8'))
            self.assertEqual(prediction_artifact['version'], 'european_sar_prediction_artifact_v1')
            self.assertEqual(prediction_artifact['source_key'], 'avalcd_zenodo_v1')
            self.assertEqual(prediction_artifact['license_review_id'], 'license-review-unit')
            self.assertIn('tp', prediction_artifact['metrics'])
            self.assertEqual(prediction_artifact['evaluated_scene_ids'], ['evt-val-1'])

            eval_request = {
                **request,
                'checkpoint_path': report['model_checkpoint_path'],
                'candidate_model_version': 'swin-shadow-unit-v1-eval',
                'materialized_dataset_root': str(root / 'eval_sar_training_dataset'),
                'threshold_grid': [0.5],
                'precision_floor': 0.0,
                'postprocess_min_component_area_px': 0,
                'postprocess_apply_to_threshold_selection': True,
            }
            with patch('backend.sar_unet_training.build_model_architecture', side_effect=lambda *args, **kwargs: _TinyBiTemporalModel()):
                eval_report = evaluate_sar_checkpoint(
                    eval_request,
                    artifact_root=root / 'eval_artifacts',
                    device='cpu',
                )
            self.assertEqual(eval_report['request_type'], 'evaluate_sar_checkpoint')
            self.assertEqual(eval_report['candidate_model_version'], 'swin-shadow-unit-v1-eval')
            self.assertTrue(Path(eval_report['sar_prediction_artifact_path']).exists())

            with patch('backend.sar_unet_training.build_model_architecture', side_effect=lambda *args, **kwargs: _TinyBiTemporalModel()):
                diagnostics_report = build_sar_validation_error_diagnostics(
                    {
                        **eval_request,
                        'threshold': eval_report['best_threshold'],
                    },
                    artifact_root=root / 'diagnostic_artifacts',
                    device='cpu',
                )
            self.assertEqual(diagnostics_report['request_type'], 'sar_validation_error_diagnostics')
            self.assertTrue(Path(diagnostics_report['diagnostics_path']).exists())


if __name__ == '__main__':
    unittest.main()
