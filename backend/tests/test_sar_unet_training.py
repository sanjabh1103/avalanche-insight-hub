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
    _postprocess_binary_mask,
    _validation_quality_gate,
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
                report = train_sar_unet(
                    request,
                    artifact_root=root / 'artifacts',
                    device='cpu',
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


if __name__ == '__main__':
    unittest.main()
