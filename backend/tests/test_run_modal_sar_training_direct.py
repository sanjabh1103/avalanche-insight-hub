from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.scripts.run_modal_sar_training_direct import load_training_request, main


class RunModalSarTrainingDirectTests(unittest.TestCase):
    def test_load_training_request_requires_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / 'request.json'
            request_path.write_text(json.dumps({'model_family': 'swinunet_tiny_diff'}), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'requires training_manifest_path'):
                load_training_request(request_path)

    def test_main_invokes_modal_function_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
                'source_key': 'avalcd_zenodo_v1',
                'candidate_model_version': 'avalcd-shadow-unit',
                'license_review_id': 'license-review-unit',
            }), encoding='utf-8')
            remote_function = Mock()
            remote_function.remote.return_value = {
                'status': 'ok',
                'artifact_dir': '/artifacts/unit',
                'model_version': 'avalcd-shadow-unit',
            }
            function_namespace = SimpleNamespace(from_name=Mock(return_value=remote_function))
            fake_modal = SimpleNamespace(Function=function_namespace)

            with patch(
                'backend.scripts.run_modal_sar_training_direct._load_modal_module',
                return_value=fake_modal,
            ), patch.dict(os.environ, {}, clear=True):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--output', str(output_path),
                    '--app-name', 'custom-app',
                    '--function-name', 'custom-function',
                ])
                modal_profile = os.environ['MODAL_PROFILE']

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload['status'], 'ok')
            self.assertEqual(payload['artifact_dir'], '/artifacts/unit')
            self.assertEqual(modal_profile, 'sanjabh1103_limit30')
            function_namespace.from_name.assert_called_once_with('custom-app', 'custom-function')
            remote_function.remote.assert_called_once()
            request_payload = remote_function.remote.call_args.args[0]
            self.assertEqual(request_payload['training_manifest_path'], '/artifacts/european-shadow-sar/manifest.json')

    def test_main_writes_structured_failure_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
                'source_key': 'avalcd_zenodo_v1',
                'candidate_model_version': 'avalcd-shadow-unit',
                'license_review_id': 'license-review-unit',
                'validation_scene_ids': ['livigno_20250318'],
            }), encoding='utf-8')

            with patch(
                'backend.scripts.run_modal_sar_training_direct.run_modal_sar_training_direct',
                side_effect=RuntimeError('workspace billing cycle spend limit reached'),
            ):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--output', str(output_path),
                ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload['status'], 'blocked_remote_training')
            self.assertEqual(payload['request_type'], 'train_sar_unet_direct')
            self.assertEqual(payload['version'], 'european_sar_prediction_artifact_v1')
            self.assertEqual(payload['source_key'], 'avalcd_zenodo_v1')
            self.assertEqual(payload['model_version'], 'avalcd-shadow-unit')
            self.assertEqual(payload['license_review_id'], 'license-review-unit')
            self.assertEqual(payload['evaluated_scene_ids'], ['livigno_20250318'])
            self.assertEqual(payload['modal_profile'], 'sanjabh1103_limit30')
            self.assertEqual(payload['app_name'], 'avalanche-modal-worker')
            self.assertEqual(payload['function_name'], 'train_sar_unet_remote')
            self.assertIn('spend limit', payload['error'])

    def test_main_async_records_function_call_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
                'source_key': 'avalcd_zenodo_v1',
                'candidate_model_version': 'avalcd-shadow-async',
                'license_review_id': 'license-review-unit',
            }), encoding='utf-8')

            function_call = SimpleNamespace(
                object_id='fc-unit-123',
                get=Mock(return_value={'status': 'ok', 'artifact_dir': '/artifacts/unit'}),
            )
            remote_function = Mock()
            remote_function.spawn.return_value = function_call
            fake_modal = SimpleNamespace(Function=SimpleNamespace(from_name=Mock(return_value=remote_function)))

            with patch(
                'backend.scripts.run_modal_sar_training_direct._load_modal_module',
                return_value=fake_modal,
            ), patch.dict(os.environ, {}, clear=True):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--output', str(output_path),
                    '--async',
                    '--max-wait-seconds', '12',
                ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload['status'], 'ok')
            self.assertEqual(payload['function_call_id'], 'fc-unit-123')
            self.assertEqual(payload['request_type'], 'train_sar_unet_direct_async')
            remote_function.spawn.assert_called_once()
            function_call.get.assert_called_once_with(timeout=12)

    def test_main_async_timeout_cancels_and_writes_structured_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
                'source_key': 'avalcd_zenodo_v1',
                'candidate_model_version': 'avalcd-shadow-timeout',
                'license_review_id': 'license-review-unit',
                'validation_scene_ids': ['livigno_20250318'],
            }), encoding='utf-8')

            function_call = SimpleNamespace(
                object_id='fc-unit-timeout',
                get=Mock(side_effect=TimeoutError('still running')),
                cancel=Mock(),
            )
            remote_function = Mock()
            remote_function.spawn.return_value = function_call
            fake_modal = SimpleNamespace(Function=SimpleNamespace(from_name=Mock(return_value=remote_function)))

            with patch(
                'backend.scripts.run_modal_sar_training_direct._load_modal_module',
                return_value=fake_modal,
            ):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--output', str(output_path),
                    '--async',
                    '--max-wait-seconds', '1',
                    '--cancel-on-timeout',
                ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload['status'], 'blocked_remote_training_timeout')
            self.assertEqual(payload['request_type'], 'train_sar_unet_direct_async')
            self.assertEqual(payload['function_call_id'], 'fc-unit-timeout')
            self.assertEqual(payload['candidate_model_version'], 'avalcd-shadow-timeout')
            self.assertEqual(payload['evaluated_scene_ids'], ['livigno_20250318'])
            self.assertTrue(payload['cancelled'])
            function_call.cancel.assert_called_once_with(terminate_containers=True)


if __name__ == '__main__':
    unittest.main()
