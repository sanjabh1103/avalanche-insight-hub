from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.scripts.run_modal_sar_checkpoint_evaluation_direct import (
    load_checkpoint_evaluation_request,
    main,
    run_modal_sar_checkpoint_evaluation_direct,
)


class RunModalSarCheckpointEvaluationDirectTests(unittest.TestCase):
    def test_load_checkpoint_evaluation_request_requires_manifest_and_checkpoint(self) -> None:
        with TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / 'request.json'
            request_path.write_text(json.dumps({'training_manifest_path': '/artifacts/manifest.json'}), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'checkpoint_path'):
                load_checkpoint_evaluation_request(request_path)

    def test_run_direct_invokes_named_modal_function(self) -> None:
        remote_function = Mock()
        remote_function.remote.return_value = {'status': 'ok', 'quality_gate': {'passed': True}}
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(from_name=Mock(return_value=remote_function)),
        )

        with patch(
            'backend.scripts.run_modal_sar_checkpoint_evaluation_direct._load_modal_module',
            return_value=fake_modal,
        ), patch.dict(os.environ, {}, clear=True):
            result = run_modal_sar_checkpoint_evaluation_direct(
                modal_profile='sanjabh1103_limit30',
                request_payload={
                    'training_manifest_path': '/artifacts/manifest.json',
                    'checkpoint_path': '/artifacts/run/sar_model.pt',
                },
            )
            self.assertEqual(os.environ['MODAL_PROFILE'], 'sanjabh1103_limit30')

        self.assertEqual(result['status'], 'ok')
        fake_modal.Function.from_name.assert_called_once_with('avalanche-modal-worker', 'evaluate_sar_checkpoint_remote')
        remote_function.remote.assert_called_once()

    def test_main_writes_structured_failure_artifact(self) -> None:
        with TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / 'bad_request.json'
            output_path = Path(tmpdir) / 'result.json'
            request_path.write_text(json.dumps({'checkpoint_path': '/artifacts/run/sar_model.pt'}), encoding='utf-8')

            exit_code = main([
                '--modal-profile', 'sanjabh1103_limit30',
                '--request', str(request_path),
                '--output', str(output_path),
            ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload['status'], 'blocked_remote_checkpoint_evaluation')
        self.assertIn('training_manifest_path', payload['reason'])


if __name__ == '__main__':
    unittest.main()
