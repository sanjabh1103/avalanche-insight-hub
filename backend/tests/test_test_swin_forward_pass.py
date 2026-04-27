from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.scripts.test_swin_forward_pass import (
    apply_rollout_env,
    build_forward_pass_payload,
    run_forward_pass_smoke_test,
)


class TestSwinForwardPassTests(unittest.TestCase):
    def test_apply_rollout_env_requires_worker_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text('', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'MODAL_WORKER_URL'):
                apply_rollout_env(env_path)

    def test_build_forward_pass_payload_uses_dry_run_bitemporal_scene(self) -> None:
        payload = build_forward_pass_payload()

        self.assertTrue(payload['dry_run'])
        self.assertTrue(payload['shadow_mode'])
        self.assertEqual(payload['model_family'], 'swinunet_tiny_diff')
        self.assertEqual(payload['prediction_model_version'], 'swin_transformer_v2_tiny_shadow_v1')
        self.assertEqual(len(payload['scenes']), 1)
        self.assertEqual(len(payload['scenes'][0]['pre_channels']), 2)
        self.assertEqual(len(payload['scenes'][0]['pre_channels'][0]), 128)
        self.assertEqual(len(payload['scenes'][0]['post_channels'][1][0]), 128)

    @patch('backend.scripts.test_swin_forward_pass.requests.post')
    def test_run_forward_pass_smoke_test_posts_expected_request(self, requests_post_mock) -> None:
        response = Mock()
        response.ok = True
        response.json.return_value = {'status': 'ok', 'scene_count': 1}
        requests_post_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text(
                '\n'.join([
                    'MODAL_WORKER_URL=https://worker.modal.run',
                    'MODAL_WORKER_TOKEN=secret-token',
                ]) + '\n',
                encoding='utf-8',
            )

            result = run_forward_pass_smoke_test(env_file=env_path)

        self.assertEqual(result['status'], 'ok')
        requests_post_mock.assert_called_once()
        _, kwargs = requests_post_mock.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret-token')
        self.assertTrue(kwargs['json']['dry_run'])
        self.assertEqual(kwargs['json']['model_family'], 'swinunet_tiny_diff')


if __name__ == '__main__':
    unittest.main()
