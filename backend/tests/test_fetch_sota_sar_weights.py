from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.scripts.fetch_sota_sar_weights import (
    fetch_sota_sar_weights,
    validate_model_url,
)


class FetchSotaSarWeightsTests(unittest.TestCase):
    def test_validate_model_url_rejects_non_https(self) -> None:
        with self.assertRaisesRegex(ValueError, 'direct https URL'):
            validate_model_url('http://example.com/model.pt')

    @patch('backend.scripts.fetch_sota_sar_weights.requests.get')
    def test_fetch_weights_rejects_html_payload(self, requests_get_mock) -> None:
        response = Mock()
        response.ok = True
        response.content = b'<!DOCTYPE html><html><body>expired</body></html>'
        response.headers = {'Content-Type': 'text/html'}
        requests_get_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            env_path.write_text('SAR_UNET_MODEL_VERSION=sar_unet_resnet34_shadow_v1\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'does not look like a model checkpoint'):
                fetch_sota_sar_weights(
                    model_url='https://example.com/model.pt',
                    output=Path(tmpdir) / 'weights' / 'model.pt',
                    env_file=env_path,
                )

    @patch('backend.scripts.fetch_sota_sar_weights.requests.get')
    def test_fetch_weights_updates_only_model_path_by_default(self, requests_get_mock) -> None:
        response = Mock()
        response.ok = True
        response.content = b'PKL\x00shadow-model'
        response.headers = {'Content-Type': 'application/octet-stream'}
        requests_get_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = root / '.env'
            env_path.write_text(
                '\n'.join([
                    'SAR_UNET_MODEL_FAMILY=resnet34_unet',
                    'SAR_UNET_MODEL_VERSION=sar_unet_resnet34_shadow_v1',
                    'SAR_UNET_PROMOTED=false',
                ]) + '\n',
                encoding='utf-8',
            )
            output_path = root / 'weights' / 'swin.pt'

            result = fetch_sota_sar_weights(
                model_url='https://example.com/model.pt',
                output=output_path,
                env_file=env_path,
            )

            self.assertEqual(result['status'], 'ok')
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b'PKL\x00shadow-model')
            env_text = env_path.read_text(encoding='utf-8')
            self.assertIn('SAR_UNET_MODEL_PATH="weights/swin.pt"', env_text)
            self.assertIn('SAR_UNET_MODEL_FAMILY=resnet34_unet', env_text)
            self.assertIn('SAR_UNET_MODEL_VERSION=sar_unet_resnet34_shadow_v1', env_text)

    @patch('backend.scripts.fetch_sota_sar_weights.requests.get')
    def test_fetch_weights_updates_family_and_version_when_requested(self, requests_get_mock) -> None:
        response = Mock()
        response.ok = True
        response.content = b'PT\x00swin-shadow'
        response.headers = {'Content-Type': 'application/octet-stream'}
        requests_get_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = root / '.env'
            env_path.write_text('SAR_UNET_PROMOTED=false\n', encoding='utf-8')

            fetch_sota_sar_weights(
                model_url='https://example.com/swin.pt',
                output=root / 'weights' / 'swin.pt',
                env_file=env_path,
                model_family='swinunet_tiny_diff',
                model_version='swin_transformer_v2_tiny_shadow_v1',
            )

            env_text = env_path.read_text(encoding='utf-8')
            self.assertIn('SAR_UNET_MODEL_PATH="weights/swin.pt"', env_text)
            self.assertIn('SAR_UNET_MODEL_FAMILY="swinunet_tiny_diff"', env_text)
            self.assertIn('SAR_UNET_MODEL_VERSION="swin_transformer_v2_tiny_shadow_v1"', env_text)

    @patch('backend.scripts.fetch_sota_sar_weights.requests.get')
    def test_fetch_weights_uses_env_model_path_override(self, requests_get_mock) -> None:
        response = Mock()
        response.ok = True
        response.content = b'PT\x00swin-shadow'
        response.headers = {'Content-Type': 'application/octet-stream'}
        requests_get_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = root / '.env'
            env_path.write_text('SAR_UNET_PROMOTED=false\n', encoding='utf-8')

            fetch_sota_sar_weights(
                model_url='https://example.com/swin.pt',
                output=root / 'weights' / 'swin.pt',
                env_file=env_path,
                env_model_path='/artifacts/models/swin_transformer_v2_tiny.pt',
            )

            env_text = env_path.read_text(encoding='utf-8')
            self.assertIn('SAR_UNET_MODEL_PATH="/artifacts/models/swin_transformer_v2_tiny.pt"', env_text)


if __name__ == '__main__':
    unittest.main()
