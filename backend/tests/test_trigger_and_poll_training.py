from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.scripts.trigger_and_poll_training import (
    apply_rollout_env,
    build_training_payload,
    main,
    trigger_and_poll_training,
)


class TriggerAndPollTrainingTests(unittest.TestCase):
    def test_apply_rollout_env_requires_worker_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text('', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'MODAL_WORKER_URL'):
                apply_rollout_env(env_path)

    def test_build_training_payload_forces_shadow_only_request(self) -> None:
        payload = build_training_payload(dataset_snapshot_id='snapshot-1', epochs=3)

        self.assertEqual(payload['request_type'], 'train_mtslstm')
        self.assertEqual(payload['dataset_snapshot_id'], 'snapshot-1')
        self.assertEqual(payload['epochs'], 3)
        self.assertTrue(payload['shadow_mode'])
        self.assertFalse(payload['allow_publish'])
        self.assertFalse(payload['sar_release_gate_passed'])

    @patch('backend.scripts.trigger_and_poll_training.time.sleep')
    @patch('backend.scripts.trigger_and_poll_training.requests.get')
    @patch('backend.scripts.trigger_and_poll_training.requests.post')
    def test_trigger_and_poll_training_waits_for_pending_job_then_returns_completion(
        self,
        requests_post_mock,
        requests_get_mock,
        _sleep_mock,
    ) -> None:
        submit_response = Mock()
        submit_response.status_code = 200
        submit_response.json.return_value = {
            'status': 'accepted',
            'call_id': 'fc-123',
            'request_type': 'train_mtslstm',
            'runtime_provider': 'modal',
        }
        pending_response = Mock()
        pending_response.status_code = 202
        pending_response.json.return_value = {
            'status': 'pending',
            'call_id': 'fc-123',
            'request_type': 'train_mtslstm',
            'runtime_provider': 'modal',
        }
        complete_response = Mock()
        complete_response.status_code = 200
        complete_response.json.return_value = {
            'status': 'ok',
            'dataset_snapshot_id': 'latest',
            'shadow_quality_gate_passed': False,
        }

        requests_post_mock.return_value = submit_response
        requests_get_mock.side_effect = [pending_response, pending_response, complete_response]

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_WORKER_URL=https://worker.modal.run',
                    'MODAL_WORKER_TOKEN=secret-token',
                ]) + '\n',
                encoding='utf-8',
            )
            with patch('sys.stdout', new_callable=io.StringIO):
                result = trigger_and_poll_training(
                    env_file=env_path,
                    poll_interval_seconds=1,
                    timeout_seconds=10,
                )

        self.assertEqual(result['status'], 'ok')
        requests_post_mock.assert_called_once()
        _, post_kwargs = requests_post_mock.call_args
        self.assertEqual(post_kwargs['headers']['Authorization'], 'Bearer secret-token')
        self.assertTrue(post_kwargs['json']['shadow_mode'])
        self.assertFalse(post_kwargs['json']['allow_publish'])
        self.assertEqual(requests_get_mock.call_count, 3)

    @patch('backend.scripts.trigger_and_poll_training.time.sleep')
    @patch('backend.scripts.trigger_and_poll_training.requests.get')
    @patch('backend.scripts.trigger_and_poll_training.requests.post')
    def test_main_exits_nonzero_for_terminal_non_ok_result(
        self,
        requests_post_mock,
        requests_get_mock,
        _sleep_mock,
    ) -> None:
        submit_response = Mock()
        submit_response.status_code = 200
        submit_response.json.return_value = {
            'status': 'accepted',
            'call_id': 'fc-123',
            'request_type': 'train_mtslstm',
            'runtime_provider': 'modal',
        }
        failed_response = Mock()
        failed_response.status_code = 200
        failed_response.json.return_value = {
            'status': 'failed',
            'reason': 'shape_mismatch',
        }

        requests_post_mock.return_value = submit_response
        requests_get_mock.return_value = failed_response

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_WORKER_URL=https://worker.modal.run',
                    'MODAL_WORKER_TOKEN=secret-token',
                ]) + '\n',
                encoding='utf-8',
            )
            with patch('sys.stdout', new_callable=io.StringIO), patch('sys.stderr', new_callable=io.StringIO):
                exit_code = main(['--env-file', str(env_path), '--timeout-seconds', '10'])

        self.assertEqual(exit_code, 1)

    @patch('backend.scripts.trigger_and_poll_training.requests.post')
    def test_main_exits_nonzero_when_submission_fails(self, requests_post_mock) -> None:
        submit_response = Mock()
        submit_response.status_code = 401
        submit_response.json.return_value = {
            'status': 'unauthorized',
            'reason': 'missing token',
        }
        requests_post_mock.return_value = submit_response

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_WORKER_URL=https://worker.modal.run',
                    'MODAL_WORKER_TOKEN=secret-token',
                ]) + '\n',
                encoding='utf-8',
            )
            with patch('sys.stdout', new_callable=io.StringIO), patch('sys.stderr', new_callable=io.StringIO) as stderr:
                exit_code = main(['--env-file', str(env_path)])

        self.assertEqual(exit_code, 1)
        self.assertIn('submission failed', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
