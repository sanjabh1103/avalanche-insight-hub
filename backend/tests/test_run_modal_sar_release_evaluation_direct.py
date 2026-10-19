from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.scripts.run_modal_sar_release_evaluation_direct import load_evaluation_request, main


class RunModalSarReleaseEvaluationDirectTests(unittest.TestCase):
    def test_load_evaluation_request_requires_reference_set_or_scenes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / 'request.json'
            request_path.write_text(json.dumps({'prediction_model_version': 'sar-v1'}), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'requires reference_set_key'):
                load_evaluation_request(request_path)

    def test_main_invokes_modal_evaluation_directly_and_forces_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'reference_set_key': 'snowslide-heldout-v1',
                'prediction_model_version': 'avalcd-v3',
                'dry_run': False,
            }), encoding='utf-8')
            remote_function = Mock()
            remote_function.remote.return_value = {
                'status': 'ok',
                'beats_baseline': False,
                'decision': 'reject',
            }
            function_namespace = SimpleNamespace(from_name=Mock(return_value=remote_function))
            fake_modal = SimpleNamespace(Function=function_namespace)

            with patch(
                'backend.scripts.run_modal_sar_release_evaluation_direct._load_modal_module',
                return_value=fake_modal,
            ), patch.dict(os.environ, {}, clear=True):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--output', str(output_path),
                    '--app-name', 'custom-app',
                    '--function-name', 'custom-evaluate',
                ])
                modal_profile = os.environ['MODAL_PROFILE']

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload['status'], 'ok')
            self.assertTrue(payload['dry_run'])
            self.assertEqual(modal_profile, 'sanjabh1103_limit30')
            function_namespace.from_name.assert_called_once_with('custom-app', 'custom-evaluate')
            request_payload = remote_function.remote.call_args.args[0]
            self.assertTrue(request_payload['dry_run'])
            self.assertEqual(request_payload['reference_set_key'], 'snowslide-heldout-v1')

    def test_main_writes_structured_failure_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'reference_set_key': 'snowslide-heldout-v1',
                'prediction_model_version': 'avalcd-v3',
            }), encoding='utf-8')

            with patch(
                'backend.scripts.run_modal_sar_release_evaluation_direct.run_modal_sar_release_evaluation_direct',
                side_effect=RuntimeError('no active set'),
            ):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--output', str(output_path),
                ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload['status'], 'blocked_remote_evaluation')
            self.assertEqual(payload['request_type'], 'evaluate_release_direct')
            self.assertEqual(payload['reference_set_key'], 'snowslide-heldout-v1')
            self.assertTrue(payload['dry_run'])
            self.assertIn('no active set', payload['error'])


if __name__ == '__main__':
    unittest.main()
