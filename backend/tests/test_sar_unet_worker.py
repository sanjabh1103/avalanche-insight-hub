from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from backend.common.label_governance import GOVERNANCE_VERSION
from backend.sar_unet_worker import (
    SAR_UNET_SHADOW_REASON,
    SegmentationDetection,
    _normalize_stack,
    build_unet_model,
    build_shadow_event_record,
    evaluate_scene_manifest,
    flip_to_training_eligible,
    load_bitemporal_scene_inputs,
    load_scene_stack,
    polygonize_probability_mask,
    persist_shadow_detections,
    run_infer_mtslstm,
    run_train_mtslstm,
    run_worker_request,
    _load_mask_array,
)


class SarUnetWorkerTests(unittest.TestCase):
    @staticmethod
    def _fake_tiff_payload(array: np.ndarray) -> bytes:
        return json.dumps(array.tolist()).encode('utf-8')

    def test_normalize_stack_rejects_single_channel_2d_input(self) -> None:
        with self.assertRaisesRegex(ValueError, 'Expected 2-channel VV\\+VH stack'):
            _normalize_stack(np.zeros((16, 16), dtype=np.float32))

    def test_polygonize_probability_mask_returns_polygon_for_positive_region(self) -> None:
        probability_mask = np.zeros((6, 6), dtype=np.float32)
        probability_mask[2:4, 2:5] = 0.9

        geometry = polygonize_probability_mask(
            probability_mask,
            bbox=(-106.6, 39.4, -106.4, 39.6),
            threshold=0.5,
        )

        self.assertIsNotNone(geometry)
        self.assertEqual(geometry['type'], 'Polygon')
        self.assertTrue(len(geometry['coordinates'][0]) >= 4)

    def test_build_shadow_event_record_materializes_governance_for_shadow_mode(self) -> None:
        detection = SegmentationDetection(
            scene_id='S1A_TEST_001',
            region_key='colorado_rockies',
            scene_time='2026-04-25T00:00:00+00:00',
            bbox=(-106.6, 39.4, -106.4, 39.6),
            probability=0.78,
            centroid={'lat': 39.5, 'lng': -106.5},
            geometry={
                'type': 'Polygon',
                'coordinates': [[
                    [-106.55, 39.45],
                    [-106.55, 39.55],
                    [-106.45, 39.55],
                    [-106.45, 39.45],
                    [-106.55, 39.45],
                ]],
            },
            mask_asset_ref='sar-masks/2026-04-25/colorado_rockies/S1A_TEST_001.tif',
            model_version='sar_unet_resnet34_shadow_v1',
            source_scene_ids=['S1A_TEST_001'],
        )

        record = build_shadow_event_record(detection, promoted=False)

        self.assertEqual(record['source'], 'sar_unet')
        self.assertFalse(record['training_eligible'])
        self.assertEqual(record['training_eligible_reason'], SAR_UNET_SHADOW_REASON)
        self.assertEqual(record['mask_asset_ref'], detection.mask_asset_ref)
        self.assertEqual(record['geometry_type'], 'polygon')
        self.assertEqual(record['governance_version'], GOVERNANCE_VERSION)
        self.assertIn('governed_at', record)
        self.assertEqual(record['features']['sar_centroid']['lat'], 39.5)
        self.assertEqual(record['source_scene_ids'], ['S1A_TEST_001'])

    def test_load_mask_array_reads_local_npz(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.npz') as handle:
            np.savez(handle, mask=np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32))
            handle.flush()
            loaded = _load_mask_array(handle.name)

        self.assertEqual(loaded.shape, (2, 2))
        self.assertEqual(float(loaded[0, 1]), 1.0)

    def test_load_mask_array_rejects_unsupported_format(self) -> None:
        with self.assertRaisesRegex(ValueError, 'unsupported evaluation mask reference'):
            _load_mask_array('sar-masks/heldout/mask.csv')

    @patch('backend.sar_unet_worker.storage_download_bytes')
    def test_load_scene_stack_reads_storage_ref_npz(self, storage_download_bytes_mock) -> None:
        payload = io.BytesIO()
        np.savez(payload, stack=np.ones((2, 4, 4), dtype=np.float32))
        storage_download_bytes_mock.return_value = payload.getvalue()

        loaded = load_scene_stack({
            'scene_id': 'S1A_001',
            'stack_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz',
        })

        self.assertEqual(loaded.shape, (2, 4, 4))
        self.assertAlmostEqual(float(loaded[0, 0, 0]), 1.0, places=5)

    def test_load_bitemporal_scene_inputs_splits_four_channel_stack(self) -> None:
        pre_stack, post_stack = load_bitemporal_scene_inputs({
            'scene_id': 'S1A_002',
            'channels': np.stack([
                np.ones((4, 4), dtype=np.float32) * 1.0,
                np.ones((4, 4), dtype=np.float32) * 2.0,
                np.ones((4, 4), dtype=np.float32) * 3.0,
                np.ones((4, 4), dtype=np.float32) * 4.0,
            ], axis=0),
        })

        self.assertEqual(pre_stack.shape, (2, 4, 4))
        self.assertEqual(post_stack.shape, (2, 4, 4))
        self.assertAlmostEqual(float(pre_stack[0, 0, 0]), 1.0, places=5)
        self.assertAlmostEqual(float(post_stack[1, 0, 0]), 4.0, places=5)

    def test_load_bitemporal_scene_inputs_rejects_two_channel_scene_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, 'expected a 4-channel bi-temporal stack'):
            load_bitemporal_scene_inputs({
                'scene_id': 'S1A_003',
                'channels': np.ones((2, 4, 4), dtype=np.float32),
            })

    @patch('backend.sar_unet_worker.requests.get')
    def test_load_mask_array_reads_http_npy(self, requests_get_mock) -> None:
        payload = io.BytesIO()
        np.save(payload, np.array([[0.1, 0.7], [0.4, 1.0]], dtype=np.float32))
        response = Mock()
        response.content = payload.getvalue()
        response.raise_for_status.return_value = None
        requests_get_mock.return_value = response

        loaded = _load_mask_array('https://example.com/prediction_mask.npy')

        self.assertEqual(loaded.shape, (2, 2))
        self.assertAlmostEqual(float(loaded[0, 1]), 0.7, places=5)

    @patch('backend.sar_unet_worker.storage_download_bytes')
    @patch('backend.sar_unet_worker.MemoryFile')
    def test_load_mask_array_reads_storage_ref_tiff(
        self,
        memory_file_mock,
        storage_download_bytes_mock,
    ) -> None:
        class _FakeDataset:
            def __init__(self, payload: bytes):
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, band: int):
                self._band = band
                return np.asarray(json.loads(self._payload.decode('utf-8')), dtype=np.float32)

        class _FakeMemoryFile:
            def __init__(self, payload: bytes):
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def open(self):
                return _FakeDataset(self._payload)

        memory_file_mock.side_effect = _FakeMemoryFile
        storage_download_bytes_mock.return_value = self._fake_tiff_payload(
            np.array([[0.0, 255.0], [204.0, 51.0]], dtype=np.float32),
        )

        loaded = _load_mask_array('sar-masks/heldout/colorado_rockies/prediction_mask.tif')

        self.assertEqual(loaded.shape, (2, 2))
        self.assertGreater(float(loaded[0, 1]), 200.0)

    @patch('backend.sar_unet_worker.SAR_UNET_PROMOTED', False)
    def test_build_unet_model_reports_checkpoint_key_mismatch_in_shadow_mode(self) -> None:
        class _DummyModel:
            def load_state_dict(self, state_dict, strict=False):
                self.strict = strict
                return SimpleNamespace(
                    missing_keys=['encoder.layer1.weight'],
                    unexpected_keys=['decoder.legacy.bias'],
                )

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                self.evaluated = True

        stderr = io.StringIO()
        with tempfile.NamedTemporaryFile() as handle, \
                patch('backend.sar_unet_worker.smp', SimpleNamespace(Unet=lambda **_: _DummyModel())), \
                patch('backend.sar_unet_worker.torch', SimpleNamespace(load=lambda *args, **kwargs: {'state_dict': {}})), \
                patch('sys.stderr', stderr):
            loaded = build_unet_model(Path(handle.name), device='cpu')

        self.assertTrue(loaded.checkpoint_key_mismatch['has_mismatch'])
        self.assertEqual(loaded.checkpoint_key_mismatch['missing_count'], 1)
        self.assertEqual(loaded.checkpoint_key_mismatch['unexpected_count'], 1)
        self.assertIn('load_state_dict key mismatch', stderr.getvalue())

    @patch('backend.sar_unet_worker.SAR_UNET_PROMOTED', True)
    def test_build_unet_model_rejects_key_mismatch_in_promoted_mode(self) -> None:
        class _DummyModel:
            def load_state_dict(self, state_dict, strict=False):
                return SimpleNamespace(missing_keys=['encoder.layer1.weight'], unexpected_keys=[])

            def to(self, device):
                return self

            def eval(self):
                return None

        with tempfile.NamedTemporaryFile() as handle, \
                patch('backend.sar_unet_worker.smp', SimpleNamespace(Unet=lambda **_: _DummyModel())), \
                patch('backend.sar_unet_worker.torch', SimpleNamespace(load=lambda *args, **kwargs: {'state_dict': {}})):
            with self.assertRaisesRegex(RuntimeError, 'Promoted SAR U-Net checkpoints must load cleanly'):
                build_unet_model(Path(handle.name), device='cpu')

    @patch('backend.sar_unet_worker._build_swinunet_tiny_diff_model')
    @patch('backend.sar_unet_worker.torch')
    def test_build_unet_model_routes_to_swin_family_builder(self, torch_mock, swin_builder_mock) -> None:
        class _DummyModel:
            def load_state_dict(self, state_dict, strict=False):
                return SimpleNamespace(missing_keys=[], unexpected_keys=[])

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                self.evaluated = True

        swin_builder_mock.return_value = _DummyModel()
        torch_mock.load.return_value = {'state_dict': {'sar_encoder.model.patch_embed.proj.weight': 1}}

        with tempfile.NamedTemporaryFile() as handle:
            loaded = build_unet_model(
                Path(handle.name),
                device='cpu',
                model_family='swinunet_tiny_diff',
                image_size=128,
            )

        swin_builder_mock.assert_called_once_with(image_size=128)
        self.assertEqual(loaded.model_family, 'swinunet_tiny_diff')

    @patch('backend.sar_unet_worker.SAR_UNET_PROMOTED', False)
    def test_build_unet_model_rejects_cross_family_checkpoint_in_shadow_mode(self) -> None:
        class _DummyModel:
            def load_state_dict(self, state_dict, strict=False):
                return SimpleNamespace(
                    missing_keys=['encoder.layer1.weight', 'decoder.blocks.0.weight'],
                    unexpected_keys=list(state_dict.keys()),
                )

            def to(self, device):
                return self

            def eval(self):
                return None

        checkpoint_keys = {
            f'sar_encoder.stage{i}.block{j}.weight': 1
            for i in range(5)
            for j in range(2)
        }
        with tempfile.NamedTemporaryFile() as handle, \
                patch('backend.sar_unet_worker.smp', SimpleNamespace(Unet=lambda **_: _DummyModel())), \
                patch('backend.sar_unet_worker.torch', SimpleNamespace(load=lambda *args, **kwargs: {'state_dict': checkpoint_keys})):
            with self.assertRaisesRegex(RuntimeError, 'SAR_UNET_MODEL_FAMILY=resnet34_unet'):
                build_unet_model(
                    Path(handle.name),
                    device='cpu',
                    model_family='resnet34_unet',
                    promoted=False,
                )

    @patch('backend.sar_unet_worker.has_supabase_credentials', return_value=True)
    @patch('backend.sar_unet_worker.persist_sar_artifacts', return_value=1)
    @patch('backend.sar_unet_worker.rest_insert')
    def test_persist_shadow_detections_warns_and_truncates_on_insert_mismatch(
        self,
        rest_insert_mock,
        persist_sar_artifacts_mock,
        _has_creds_mock,
    ) -> None:
        rest_insert_mock.return_value = [{'id': 'evt-1'}]
        records = [
            {'source_model': 'sar_unet_resnet34_shadow_v1', 'features': {'region_key': 'colorado_rockies'}},
            {'source_model': 'sar_unet_resnet34_shadow_v1', 'features': {'region_key': 'colorado_rockies'}},
        ]

        stderr = io.StringIO()
        with patch('sys.stderr', stderr):
            summary = persist_shadow_detections(records)

        self.assertEqual(summary['persisted_events'], 1)
        self.assertEqual(summary['artifact_rows_persisted'], 1)
        self.assertIn('artifact persistence truncated', stderr.getvalue())
        persist_sar_artifacts_mock.assert_called_once_with([{'id': 'evt-1'}], records[:1])

    def test_evaluate_scene_manifest_rejects_missing_baseline_data(self) -> None:
        report = evaluate_scene_manifest({
            'scenes': [{
                'region_key': 'colorado_rockies',
                'prediction_mask': np.ones((2, 2), dtype=np.float32),
                'truth_mask': np.ones((2, 2), dtype=np.float32),
            }],
        })

        self.assertEqual(report['status'], 'invalid_manifest')
        self.assertIn('baseline_f1_floor', report['reason'])
        self.assertFalse(report['beats_baseline'])

    def test_evaluate_scene_manifest_uses_derived_baseline_and_reports_gate(self) -> None:
        report = evaluate_scene_manifest({
            'baseline_margin': 0.05,
            'scenes': [{
                'region_key': 'colorado_rockies',
                'prediction_mask': np.ones((2, 2), dtype=np.float32),
                'truth_mask': np.ones((2, 2), dtype=np.float32),
                'baseline_mask': np.array([[1, 1], [1, 0]], dtype=np.float32),
            }],
        })

        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['scene_count'], 1)
        self.assertIn('colorado_rockies', report['region_coverage'])
        self.assertGreater(float(report['baseline_f1_floor_used']), 0.0)
        self.assertIn('baseline_metrics', report)

    @patch('backend.sar_unet_worker.storage_download_bytes')
    @patch('backend.sar_unet_worker.requests.get')
    @patch('backend.sar_unet_worker.MemoryFile')
    def test_evaluate_scene_manifest_supports_remote_and_storage_refs(
        self,
        memory_file_mock,
        requests_get_mock,
        storage_download_bytes_mock,
    ) -> None:
        class _FakeDataset:
            def __init__(self, payload: bytes):
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, band: int):
                self._band = band
                return np.asarray(json.loads(self._payload.decode('utf-8')), dtype=np.float32)

        class _FakeMemoryFile:
            def __init__(self, payload: bytes):
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def open(self):
                return _FakeDataset(self._payload)

        memory_file_mock.side_effect = _FakeMemoryFile
        prediction_payload = io.BytesIO()
        truth_payload = io.BytesIO()
        np.save(prediction_payload, np.ones((2, 2), dtype=np.float32))
        np.save(truth_payload, np.ones((2, 2), dtype=np.float32))
        requests_get_mock.side_effect = [
            Mock(content=prediction_payload.getvalue(), raise_for_status=Mock()),
            Mock(content=truth_payload.getvalue(), raise_for_status=Mock()),
        ]
        storage_download_bytes_mock.return_value = self._fake_tiff_payload(
            np.array([[255.0, 255.0], [255.0, 0.0]], dtype=np.float32),
        )

        report = evaluate_scene_manifest({
            'baseline_margin': 0.05,
            'scenes': [{
                'region_key': 'colorado_rockies',
                'prediction_mask': 'https://example.com/prediction_mask.npy',
                'truth_mask': 'https://example.com/truth_mask.npy',
                'baseline_mask': 'sar-masks/heldout/colorado_rockies/gee_threshold_mask.tif',
            }],
        })

        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['scene_count'], 1)
        self.assertIn('baseline_metrics', report)

    def test_evaluate_scene_manifest_requires_strict_improvement_over_floor(self) -> None:
        report = evaluate_scene_manifest({
            'baseline_f1_floor': 1.0,
            'scenes': [{
                'region_key': 'colorado_rockies',
                'prediction_mask': np.ones((2, 2), dtype=np.float32),
                'truth_mask': np.ones((2, 2), dtype=np.float32),
            }],
        })

        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['f1'], 1.0)
        self.assertFalse(report['beats_baseline'])

    @patch('backend.sar_release_manifest.build_release_manifest_from_reference_set')
    @patch('backend.sar_unet_worker.dump_json')
    @patch('backend.sar_unet_worker.create_artifact_dir')
    def test_run_worker_request_evaluate_release_builds_from_reference_set(
        self,
        create_artifact_dir_mock,
        dump_json_mock,
        build_manifest_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / '20260425T020000Z'
            artifact_dir.mkdir()
            create_artifact_dir_mock.return_value = artifact_dir
            build_manifest_mock.return_value = {
                'baseline_margin': 0.05,
                'scenes': [{
                    'region_key': 'colorado_rockies',
                    'prediction_mask': np.ones((2, 2), dtype=np.float32),
                    'truth_mask': np.ones((2, 2), dtype=np.float32),
                    'baseline_mask': np.array([[1, 1], [1, 0]], dtype=np.float32),
                }],
            }

            report = run_worker_request(
                'evaluate-release',
                {
                    'reference_set_key': 'snowslide-validation-v1',
                    'prediction_model_version': 'sar_unet_resnet34_shadow_v1',
                    'skip_validate_refs': True,
                },
                artifact_root=Path(tmpdir),
            )

        self.assertEqual(report['status'], 'ok')
        self.assertTrue(build_manifest_mock.called)
        dump_json_mock.assert_called_once()

    @patch('backend.sar_unet_worker._run_python_module')
    def test_run_train_mtslstm_returns_wave4_gate_summary(self, run_python_module_mock) -> None:
        run_python_module_mock.return_value = subprocess.CompletedProcess(
            args=['python', '-m', 'backend.train_model'],
            returncode=0,
            stdout='training ok\n',
            stderr='',
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            artifact_dir = artifact_root / '20260425T000000Z'
            artifact_dir.mkdir()
            (artifact_dir / 'training_metrics.json').write_text(
                '{"dataset_snapshot_id":"real_event_join_v1:2026-04-25T00:00:00+00:00","lstm_head_meta":{"dataset_snapshot_id":"real_event_join_v1:2026-04-25T00:00:00+00:00","pss_holdout":0.54,"rf_pss_holdout":0.48,"brier_score":0.17,"rf_brier_score":0.19,"shadow_quality_gate_passed":true,"sar_release_gate_passed":false,"production_eligibility_gate_passed":false,"promotion_gate_passed":false,"epochs_requested":50,"epochs_completed":18,"early_stopped":true}}',
                encoding='utf-8',
            )

            report = run_train_mtslstm(
                {
                    'hazard_type': 'avalanche',
                    'request_type': 'train_mtslstm',
                    'dataset_snapshot_id': 'latest',
                },
                artifact_root=artifact_root,
            )

        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['dataset_snapshot_id'], 'real_event_join_v1:2026-04-25T00:00:00+00:00')
        self.assertTrue(report['shadow_quality_gate_passed'])
        self.assertFalse(report['production_eligibility_gate_passed'])
        self.assertEqual(report['epochs_requested'], 50)
        self.assertTrue(report['early_stopped'])
        env = run_python_module_mock.call_args.kwargs['env']
        self.assertEqual(env['DEM_ROOT'], str(artifact_root / 'dem'))
        self.assertEqual(env['DEM_DIR'], str(artifact_root / 'dem'))
        self.assertEqual(env['ALLOW_MODEL_STATUS_PUBLISH'], 'false')

    @patch('backend.sar_unet_worker._run_python_module')
    def test_run_train_mtslstm_ignores_support_directories_when_training_fails_early(self, run_python_module_mock) -> None:
        run_python_module_mock.return_value = subprocess.CompletedProcess(
            args=['python', '-m', 'backend.train_model'],
            returncode=1,
            stdout='',
            stderr='training failed\n',
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            (artifact_root / 'dem').mkdir()
            (artifact_root / 'models').mkdir()

            report = run_train_mtslstm(
                {
                    'hazard_type': 'avalanche',
                    'request_type': 'train_mtslstm',
                    'dataset_snapshot_id': 'latest',
                },
                artifact_root=artifact_root,
            )

        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['artifact_dir'])

    @patch('backend.sar_unet_worker._run_python_module')
    def test_run_infer_mtslstm_returns_shadow_summary(self, run_python_module_mock) -> None:
        run_python_module_mock.return_value = subprocess.CompletedProcess(
            args=['python', '-m', 'backend.daily_inference'],
            returncode=0,
            stdout='inference ok\n',
            stderr='',
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            artifact_dir = artifact_root / '20260425T010000Z'
            artifact_dir.mkdir()
            (artifact_dir / 'inference_manifest.json').write_text(
                '{"regions_written":3,"completed_at":"2026-04-25T01:23:45+00:00"}',
                encoding='utf-8',
            )
            (artifact_dir / 'training_metrics.json').write_text(
                '{"lstm_head_meta":{"dataset_snapshot_id":"real_event_join_v1:2026-04-25T00:00:00+00:00","promotion_gate_passed":false}}',
                encoding='utf-8',
            )

            report = run_infer_mtslstm(
                {
                    'hazard_type': 'avalanche',
                    'request_type': 'infer_mtslstm',
                    'forecast_hours': 72,
                },
                artifact_root=artifact_root,
            )

        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['regions_written'], 3)
        self.assertTrue(report['shadow_mode_active'])
        self.assertEqual(report['dataset_snapshot_id'], 'real_event_join_v1:2026-04-25T00:00:00+00:00')


    @patch('backend.sar_unet_worker.has_supabase_credentials', return_value=False)
    def test_flip_to_training_eligible_is_noop_without_credentials(self, _mock) -> None:
        result = flip_to_training_eligible(['evt-1', 'evt-2'])
        self.assertEqual(result, 0)

    @patch('backend.sar_unet_worker.has_supabase_credentials', return_value=False)
    def test_flip_to_training_eligible_is_noop_for_empty_list(self, _mock) -> None:
        result = flip_to_training_eligible([])
        self.assertEqual(result, 0)

    @patch('backend.sar_unet_worker._load_mask_array')
    @patch('backend.sar_release_manifest.load_reference_bundle')
    def test_evaluate_scene_manifest_resolves_reference_set_key_from_supabase(
        self, load_bundle_mock, load_mask_mock
    ) -> None:
        """F2 fix: evaluate_scene_manifest auto-resolves reference_set_key when scenes[] is absent."""
        import numpy as np
        mask = np.ones((4, 4), dtype=np.float32)
        load_mask_mock.return_value = mask
        load_bundle_mock.return_value = (
            {
                'id': 'set-1',
                'set_key': 'snowslide-heldout-v1',
                'source_name': 'snowslide_slf',
                'source_version': '2026-04-25',
                'split_name': 'validation',
                'authoritative': True,
            },
            [{
                'id': 'item-1',
                'external_scene_id': 'S1A_001',
                'region_key': 'colorado_rockies',
                'scene_time': '2026-02-10T00:00:00+00:00',
                'bbox': [-106.6, 39.4, -106.4, 39.6],
                'stack_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz',
                'truth_mask_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif',
                'baseline_mask_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/baseline_mask.tif',
                'metadata': {'split': 'validation'},
            }],
        )

        result = evaluate_scene_manifest({
            'reference_set_key': 'snowslide-heldout-v1',
            'prediction_model_version': 'sar_unet_resnet34_shadow_v1',
        })

        # Should have resolved to a valid evaluation (not invalid_manifest)
        self.assertNotEqual(result.get('status'), 'invalid_manifest')
        self.assertIn('beats_baseline', result)
        load_bundle_mock.assert_called_once()

    def test_evaluate_scene_manifest_returns_invalid_manifest_when_reference_set_key_resolution_fails(
        self,
    ) -> None:
        """F2 fix: clean error response when reference_set_key cannot be resolved."""
        with patch('backend.sar_release_manifest.load_reference_bundle', side_effect=ValueError('no active set')):
            result = evaluate_scene_manifest({'reference_set_key': 'does-not-exist'})

        self.assertEqual(result['status'], 'invalid_manifest')
        self.assertIn('does-not-exist', result['reason'])
        self.assertFalse(result['beats_baseline'])


if __name__ == '__main__':
    unittest.main()
