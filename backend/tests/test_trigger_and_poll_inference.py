from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.trigger_and_poll_inference import (
    apply_inference_env,
    inference_passed,
    main,
    trigger_and_poll_inference,
)


class TriggerAndPollInferenceTests(unittest.TestCase):
    def test_apply_inference_env_requires_http_worker_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text('', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'MODAL_WORKER_URL'):
                apply_inference_env(env_path, transport='http')

    def test_apply_inference_env_sets_modal_tokens_for_modal_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_TOKEN_ID=token-id',
                    'MODAL_TOKEN_SECRET=token-secret',
                ]) + '\n',
                encoding='utf-8',
            )
            with patch.dict(os.environ, {}, clear=True):
                values = apply_inference_env(env_path, transport='modal')
                self.assertEqual(values['modal_worker_url'], '')
                self.assertEqual(os.environ.get('MODAL_TOKEN_ID'), 'token-id')
                self.assertEqual(os.environ.get('MODAL_TOKEN_SECRET'), 'token-secret')

    def test_inference_passed_requires_surrogate_model_version(self) -> None:
        self.assertFalse(
            inference_passed(
                {
                    'status': 'ok',
                    'regions_written': 1,
                    'total_cells_written': 20,
                    'cells_with_shap': 20,
                    'surrogate_model_version': '',
                }
            )
        )
        self.assertTrue(
            inference_passed(
                {
                    'status': 'ok',
                    'regions_written': 1,
                    'total_cells_written': 20,
                    'cells_with_shap': 20,
                    'surrogate_model_version': 'rf_surrogate_v1',
                }
            )
        )

    @patch('backend.scripts.trigger_and_poll_inference.poll_inference_job_http')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_http')
    def test_trigger_and_poll_inference_runs_http_transport(
        self,
        submit_inference_job_http_mock,
        poll_inference_job_http_mock,
    ) -> None:
        submit_inference_job_http_mock.return_value = {
            'status': 'accepted',
            'call_id': 'fc-http',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        poll_inference_job_http_mock.return_value = (
            200,
            {
                'status': 'ok',
                'regions_written': 2,
                'total_cells_written': 200,
                'cells_with_shap': 200,
                'surrogate_model_version': 'rf_surrogate_v1',
            },
        )

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
                result = trigger_and_poll_inference(
                    env_file=env_path,
                    artifact_dir='/artifacts/20260427T172132Z',
                    transport='http',
                    poll_interval_seconds=1,
                    timeout_seconds=10,
                )

        self.assertTrue(result['inference_passed'])
        submit_kwargs = submit_inference_job_http_mock.call_args.kwargs
        self.assertEqual(submit_kwargs['payload']['artifact_dir'], '/artifacts/20260427T172132Z')
        self.assertTrue(submit_kwargs['payload']['dry_run'])
        self.assertEqual(result['transport'], 'http')

    @patch('backend.scripts.trigger_and_poll_inference.poll_inference_job_modal')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_modal')
    def test_trigger_and_poll_inference_runs_modal_transport(
        self,
        submit_inference_job_modal_mock,
        poll_inference_job_modal_mock,
    ) -> None:
        submit_inference_job_modal_mock.return_value = {
            'status': 'accepted',
            'call_id': 'fc-modal',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        poll_inference_job_modal_mock.return_value = (
            200,
            {
                'status': 'ok',
                'regions_written': 2,
                'total_cells_written': 200,
                'cells_with_shap': 200,
                'surrogate_model_version': 'rf_surrogate_v1',
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_TOKEN_ID=token-id',
                    'MODAL_TOKEN_SECRET=token-secret',
                ]) + '\n',
                encoding='utf-8',
            )
            with patch.dict(os.environ, {}, clear=True), patch('sys.stdout', new_callable=io.StringIO):
                result = trigger_and_poll_inference(
                    env_file=env_path,
                    artifact_dir='/artifacts/20260427T172132Z',
                    transport='modal',
                    poll_interval_seconds=1,
                    timeout_seconds=10,
                )

        self.assertTrue(result['inference_passed'])
        submit_kwargs = submit_inference_job_modal_mock.call_args.kwargs
        self.assertEqual(submit_kwargs['payload']['artifact_dir'], '/artifacts/20260427T172132Z')
        self.assertEqual(result['transport'], 'modal')

    @patch('backend.scripts.trigger_and_poll_inference.poll_inference_job_http')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_http')
    def test_main_exits_nonzero_when_inference_does_not_meet_acceptance_gate(
        self,
        submit_inference_job_http_mock,
        poll_inference_job_http_mock,
    ) -> None:
        submit_inference_job_http_mock.return_value = {
            'status': 'accepted',
            'call_id': 'fc-http',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        poll_inference_job_http_mock.return_value = (
            200,
            {
                'status': 'ok',
                'regions_written': 1,
                'total_cells_written': 10,
                'cells_with_shap': 0,
                'surrogate_model_version': 'rf_surrogate_v1',
            },
        )

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
                exit_code = main([
                    '--env-file', str(env_path),
                    '--artifact-dir', '/artifacts/20260427T172132Z',
                    '--transport', 'http',
                    '--timeout-seconds', '10',
                ])

        self.assertEqual(exit_code, 1)


if __name__ == '__main__':
    unittest.main()
