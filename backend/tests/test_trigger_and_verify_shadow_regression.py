from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.scripts.trigger_and_verify_shadow_regression import (
    build_inference_payload,
    main,
    shadow_regression_passed,
    trigger_and_verify_shadow_regression,
)


class TriggerAndVerifyShadowRegressionTests(unittest.TestCase):
    def test_build_inference_payload_forces_shadow_only_dry_run(self) -> None:
        payload = build_inference_payload(forecast_hours=96, grid_size=24)

        self.assertEqual(payload['request_type'], 'infer_mtslstm')
        self.assertEqual(payload['forecast_hours'], 96)
        self.assertEqual(payload['grid_size'], 24)
        self.assertTrue(payload['shadow_mode'])
        self.assertTrue(payload['dry_run'])
        self.assertFalse(payload['allow_publish'])

    def test_shadow_regression_passed_requires_cells_with_shap(self) -> None:
        self.assertFalse(
            shadow_regression_passed(
                {'status': 'ok'},
                {'status': 'ok', 'regions_written': 1, 'total_cells_written': 20, 'cells_with_shap': 0},
            )
        )
        self.assertTrue(
            shadow_regression_passed(
                {'status': 'ok'},
                {'status': 'ok', 'regions_written': 1, 'total_cells_written': 20, 'cells_with_shap': 20},
            )
        )

    @patch('backend.scripts.trigger_and_verify_shadow_regression.time.sleep')
    @patch('backend.scripts.trigger_and_verify_shadow_regression.requests.get')
    @patch('backend.scripts.trigger_and_verify_shadow_regression.requests.post')
    def test_trigger_and_verify_shadow_regression_runs_train_then_infer(
        self,
        requests_post_mock,
        requests_get_mock,
        _sleep_mock,
    ) -> None:
        train_submit_response = Mock()
        train_submit_response.status_code = 200
        train_submit_response.json.return_value = {
            'status': 'accepted',
            'call_id': 'fc-train',
            'request_type': 'train_mtslstm',
            'runtime_provider': 'modal',
        }
        infer_submit_response = Mock()
        infer_submit_response.status_code = 200
        infer_submit_response.json.return_value = {
            'status': 'accepted',
            'call_id': 'fc-infer',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        train_pending_response = Mock()
        train_pending_response.status_code = 202
        train_pending_response.json.return_value = {
            'status': 'pending',
            'call_id': 'fc-train',
            'request_type': 'train_mtslstm',
            'runtime_provider': 'modal',
        }
        train_complete_response = Mock()
        train_complete_response.status_code = 200
        train_complete_response.json.return_value = {'status': 'ok', 'dataset_snapshot_id': 'latest'}
        infer_pending_response = Mock()
        infer_pending_response.status_code = 202
        infer_pending_response.json.return_value = {
            'status': 'pending',
            'call_id': 'fc-infer',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        infer_complete_response = Mock()
        infer_complete_response.status_code = 200
        infer_complete_response.json.return_value = {
            'status': 'ok',
            'regions_written': 2,
            'total_cells_written': 800,
            'cells_with_shap': 800,
            'surrogate_model_version': 'rf_surrogate_v1',
        }

        requests_post_mock.side_effect = [train_submit_response, infer_submit_response]
        requests_get_mock.side_effect = [
            train_pending_response,
            train_complete_response,
            infer_pending_response,
            infer_complete_response,
        ]

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
                result = trigger_and_verify_shadow_regression(
                    env_file=env_path,
                    poll_interval_seconds=1,
                    timeout_seconds=10,
                )

        self.assertTrue(result['shadow_regression_passed'])
        self.assertEqual(result['training']['status'], 'ok')
        self.assertEqual(result['inference']['cells_with_shap'], 800)
        self.assertEqual(requests_post_mock.call_count, 2)
        infer_payload = requests_post_mock.call_args_list[1].kwargs['json']
        self.assertTrue(infer_payload['shadow_mode'])
        self.assertTrue(infer_payload['dry_run'])
        self.assertFalse(infer_payload['allow_publish'])

    @patch('backend.scripts.trigger_and_verify_shadow_regression.requests.get')
    @patch('backend.scripts.trigger_and_verify_shadow_regression.requests.post')
    def test_main_exits_nonzero_when_infer_result_lacks_shap(
        self,
        requests_post_mock,
        requests_get_mock,
    ) -> None:
        train_submit_response = Mock()
        train_submit_response.status_code = 200
        train_submit_response.json.return_value = {
            'status': 'accepted',
            'call_id': 'fc-train',
            'request_type': 'train_mtslstm',
            'runtime_provider': 'modal',
        }
        infer_submit_response = Mock()
        infer_submit_response.status_code = 200
        infer_submit_response.json.return_value = {
            'status': 'accepted',
            'call_id': 'fc-infer',
            'request_type': 'infer_mtslstm',
            'runtime_provider': 'modal',
        }
        train_complete_response = Mock()
        train_complete_response.status_code = 200
        train_complete_response.json.return_value = {'status': 'ok'}
        infer_complete_response = Mock()
        infer_complete_response.status_code = 200
        infer_complete_response.json.return_value = {
            'status': 'ok',
            'regions_written': 1,
            'total_cells_written': 400,
            'cells_with_shap': 0,
        }

        requests_post_mock.side_effect = [train_submit_response, infer_submit_response]
        requests_get_mock.side_effect = [train_complete_response, infer_complete_response]

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


if __name__ == '__main__':
    unittest.main()
