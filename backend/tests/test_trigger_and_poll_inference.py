from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.trigger_and_poll_inference import (
    DEFAULT_REATTACH_TIMEOUT_SECONDS,
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

    def test_inference_passed_allows_zero_shap_in_lifeboat_mode(self) -> None:
        self.assertTrue(
            inference_passed(
                {
                    'status': 'ok',
                    'regions_written': 1,
                    'total_cells_written': 20,
                    'cells_with_shap': 0,
                    'lifeboat_mode': True,
                    'surrogate_model_version': 'rf_surrogate_v1',
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

    @patch('backend.scripts.trigger_and_poll_inference._poll_until_terminal')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_http')
    def test_trigger_and_poll_inference_reattaches_without_submission(
        self,
        submit_inference_job_http_mock,
        poll_until_terminal_mock,
    ) -> None:
        poll_until_terminal_mock.return_value = {
            'status': 'ok',
            'regions_written': 1,
            'total_cells_written': 20,
            'cells_with_shap': 20,
            'surrogate_model_version': 'rf_surrogate_v1',
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_WORKER_URL=https://worker.modal.run',
                    'MODAL_WORKER_TOKEN=secret-token',
                ]) + '\n',
                encoding='utf-8',
            )
            result = trigger_and_poll_inference(
                env_file=env_path,
                call_id='fc-existing',
                transport='http',
                poll_interval_seconds=1,
            )

        self.assertTrue(result['inference_passed'])
        submit_inference_job_http_mock.assert_not_called()
        self.assertEqual(poll_until_terminal_mock.call_args.kwargs['call_id'], 'fc-existing')
        self.assertEqual(
            poll_until_terminal_mock.call_args.kwargs['timeout_seconds'],
            DEFAULT_REATTACH_TIMEOUT_SECONDS,
        )

    @patch('backend.scripts.trigger_and_poll_inference._poll_until_terminal')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_http')
    def test_trigger_and_poll_inference_forwards_region_keys(
        self,
        submit_inference_job_http_mock,
        poll_until_terminal_mock,
    ) -> None:
        submit_inference_job_http_mock.return_value = {
            'status': 'accepted',
            'call_id': 'fc-http',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        poll_until_terminal_mock.return_value = {
            'status': 'ok',
            'regions_written': 1,
            'total_cells_written': 20,
            'cells_with_shap': 20,
            'surrogate_model_version': 'rf_surrogate_v1',
        }

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
                trigger_and_poll_inference(
                    env_file=env_path,
                    artifact_dir='/artifacts/20260427T172132Z',
                    transport='http',
                    region_keys=['japanese_alps', 'cascades_wa'],
                )

        submit_kwargs = submit_inference_job_http_mock.call_args.kwargs
        self.assertEqual(
            submit_kwargs['payload']['region_keys'],
            ['japanese_alps', 'cascades_wa'],
        )

    @patch('backend.scripts.trigger_and_poll_inference._poll_until_terminal')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_http')
    def test_trigger_and_poll_inference_forwards_lifeboat_payload(
        self,
        submit_inference_job_http_mock,
        poll_until_terminal_mock,
    ) -> None:
        submit_inference_job_http_mock.return_value = {
            'status': 'accepted',
            'call_id': 'fc-http',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        poll_until_terminal_mock.return_value = {
            'status': 'ok',
            'regions_written': 1,
            'total_cells_written': 20,
            'cells_with_shap': 0,
            'lifeboat_mode': True,
            'surrogate_model_version': 'rf_surrogate_v1',
        }

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
                    region_keys=['japanese_alps'],
                    lifeboat_mode=True,
                    emit_stage_metrics=True,
                )

        self.assertTrue(result['inference_passed'])
        payload = submit_inference_job_http_mock.call_args.kwargs['payload']
        self.assertTrue(payload['lifeboat_mode'])
        self.assertEqual(payload['lifeboat_profile'], 'proof72')
        self.assertTrue(payload['emit_stage_metrics'])
        self.assertEqual(payload['region_keys'], ['japanese_alps'])

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

    @patch('backend.scripts.trigger_and_poll_inference._poll_until_terminal')
    @patch('backend.scripts.trigger_and_poll_inference.submit_inference_job_http')
    def test_main_supports_call_id_reattach_mode(
        self,
        submit_inference_job_http_mock,
        poll_until_terminal_mock,
    ) -> None:
        poll_until_terminal_mock.return_value = {
            'status': 'ok',
            'regions_written': 1,
            'total_cells_written': 20,
            'cells_with_shap': 20,
            'surrogate_model_version': 'rf_surrogate_v1',
        }

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
                    '--call-id', 'fc-existing',
                    '--transport', 'http',
                ])

        self.assertEqual(exit_code, 0)
        submit_inference_job_http_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
