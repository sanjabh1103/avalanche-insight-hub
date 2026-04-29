from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.common.storage_io import storage_download_bytes, storage_upload_bytes
from backend.common.supabase_io import SupabaseError


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        text: str = '',
        content: bytes = b'',
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class StorageIoTests(unittest.TestCase):
    @patch('backend.common.storage_io._headers', return_value={'apikey': 'test', 'Authorization': 'Bearer test'})
    @patch('backend.common.storage_io._base_url', return_value='https://example.supabase.co')
    @patch('backend.common.storage_io.time.sleep', return_value=None)
    @patch('backend.common.storage_io.requests.get')
    def test_storage_download_retries_transient_503_then_succeeds(
        self,
        requests_get_mock,
        _sleep_mock,
        _base_url_mock,
        _headers_mock,
    ) -> None:
        requests_get_mock.side_effect = [
            FakeResponse(503, text='Service Unavailable'),
            FakeResponse(200, content=b'patch-bytes'),
        ]

        payload = storage_download_bytes(bucket='sar-masks', object_path='heldout/test/patch.npz')

        self.assertEqual(payload, b'patch-bytes')
        self.assertEqual(requests_get_mock.call_count, 2)

    @patch('backend.common.storage_io._headers', return_value={'apikey': 'test', 'Authorization': 'Bearer test'})
    @patch('backend.common.storage_io._base_url', return_value='https://example.supabase.co')
    @patch('backend.common.storage_io.time.sleep', return_value=None)
    @patch('backend.common.storage_io.requests.post')
    def test_storage_upload_retries_retryable_responses_then_succeeds(
        self,
        requests_post_mock,
        _sleep_mock,
        _base_url_mock,
        _headers_mock,
    ) -> None:
        requests_post_mock.side_effect = [
            FakeResponse(429, text='rate limited', headers={'Retry-After': '0'}),
            FakeResponse(503, text='Service Unavailable'),
            FakeResponse(200),
        ]

        asset_ref = storage_upload_bytes(
            bucket='sar-masks',
            object_path='heldout/test/payload.bin',
            payload=b'data',
        )

        self.assertEqual(asset_ref, 'sar-masks/heldout/test/payload.bin')
        self.assertEqual(requests_post_mock.call_count, 3)

    @patch('backend.common.storage_io._headers', return_value={'apikey': 'test', 'Authorization': 'Bearer test'})
    @patch('backend.common.storage_io._base_url', return_value='https://example.supabase.co')
    @patch('backend.common.storage_io.time.sleep', return_value=None)
    @patch('backend.common.storage_io.requests.get')
    def test_storage_download_fails_fast_on_non_retryable_404(
        self,
        requests_get_mock,
        sleep_mock,
        _base_url_mock,
        _headers_mock,
    ) -> None:
        requests_get_mock.return_value = FakeResponse(404, text='not found')

        with self.assertRaisesRegex(SupabaseError, '404'):
            storage_download_bytes(bucket='sar-masks', object_path='heldout/test/missing.npz')

        requests_get_mock.assert_called_once()
        sleep_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
