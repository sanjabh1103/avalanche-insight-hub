from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.scripts.seed_snowslide_truth import seed_snowslide_truth


class SeedSnowSlideTruthTests(unittest.TestCase):
    @staticmethod
    def _write_archive(path: Path, *, include_validation: bool = True) -> None:
        with zipfile.ZipFile(path, 'w') as archive:
            if include_validation:
                archive.writestr(
                    'validation/colorado_rockies/S1A_001/truth_mask.tif',
                    b'geotiff-bytes',
                )
                stack_payload = io.BytesIO()
                np.savez(stack_payload, stack=np.ones((2, 4, 4), dtype=np.float32))
                archive.writestr(
                    'validation/colorado_rockies/S1A_001/stack.npz',
                    stack_payload.getvalue(),
                )
            archive.writestr('metadata/readme.txt', 'not a registry')

    @staticmethod
    def _build_archive_bytes(*, include_validation: bool = True) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            if include_validation:
                archive.writestr(
                    'validation/colorado_rockies/S1A_001/truth_mask.tif',
                    b'geotiff-bytes',
                )
                stack_payload = io.BytesIO()
                np.savez(stack_payload, stack=np.ones((2, 4, 4), dtype=np.float32))
                archive.writestr(
                    'validation/colorado_rockies/S1A_001/stack.npz',
                    stack_payload.getvalue(),
                )
            archive.writestr('metadata/readme.txt', 'not a registry')
        return payload.getvalue()

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json', return_value='sar-masks/heldout/snowslide/2026-04-25/reference_sets/snowslide-v1/registry.json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    def test_seed_snowslide_truth_uploads_truth_and_stack_and_registers_rows(
        self,
        rest_upsert_mock,
        storage_upload_bytes_mock,
        storage_upsert_json_mock,
    ) -> None:
        rest_upsert_mock.side_effect = [
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
            [{'id': 'item-1'}],
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(archive_path)
            args = argparse.Namespace(
                source_url=None,
                source_zip=archive_path,
                registry_member=None,
                header=[],
                timeout=300,
                set_key='snowslide-v1',
                source_version='2026-04-25',
                bucket='sar-masks',
                hazard_type='avalanche',
                notes='seed run',
            )

            result = seed_snowslide_truth(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)
        self.assertEqual(storage_upload_bytes_mock.call_count, 2)
        item_upsert = rest_upsert_mock.call_args_list[1]
        self.assertEqual(item_upsert.kwargs['on_conflict'], 'reference_set_id,external_scene_id')
        inserted_row = item_upsert.args[1][0]
        self.assertEqual(inserted_row['truth_mask_asset_ref'], 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif')
        self.assertEqual(inserted_row['stack_asset_ref'], 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz')

    def test_seed_snowslide_truth_rejects_archives_without_validation_or_test_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(archive_path, include_validation=False)
            args = argparse.Namespace(
                source_url=None,
                source_zip=archive_path,
                registry_member=None,
                header=[],
                timeout=300,
                set_key='snowslide-v1',
                source_version='2026-04-25',
                bucket='sar-masks',
                hazard_type='avalanche',
                notes='seed run',
            )

            with self.assertRaisesRegex(ValueError, 'validation/test split'):
                seed_snowslide_truth(args)

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json', return_value='sar-masks/heldout/snowslide/2026-04-25/reference_sets/snowslide-v1/registry.json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    @patch('pathlib.Path.read_bytes', side_effect=AssertionError('source_zip should not call read_bytes'))
    def test_seed_snowslide_truth_uses_file_backed_zip_for_source_zip(
        self,
        _read_bytes_mock,
        rest_upsert_mock,
        storage_upload_bytes_mock,
        _storage_upsert_json_mock,
    ) -> None:
        rest_upsert_mock.side_effect = [
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
            [{'id': 'item-1'}],
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(archive_path)
            args = argparse.Namespace(
                source_url=None,
                source_zip=archive_path,
                registry_member=None,
                header=[],
                timeout=300,
                set_key='snowslide-v1',
                source_version='2026-04-25',
                bucket='sar-masks',
                hazard_type='avalanche',
                notes='seed run',
            )

            result = seed_snowslide_truth(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(storage_upload_bytes_mock.call_count, 2)

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json', return_value='sar-masks/heldout/snowslide/2026-04-25/reference_sets/snowslide-v1/registry.json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    @patch('backend.scripts.seed_snowslide_truth.requests.get')
    def test_seed_snowslide_truth_streams_source_url_to_tempfile(
        self,
        requests_get_mock,
        rest_upsert_mock,
        storage_upload_bytes_mock,
        _storage_upsert_json_mock,
    ) -> None:
        class _StreamingResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload
                self.closed = False

            @property
            def content(self) -> bytes:
                raise AssertionError('source_url path should not access response.content')

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int = 1) -> list[bytes]:
                return [
                    self._payload[index:index + chunk_size]
                    for index in range(0, len(self._payload), chunk_size)
                ]

            def close(self) -> None:
                self.closed = True

        response = _StreamingResponse(self._build_archive_bytes())
        requests_get_mock.return_value = response
        rest_upsert_mock.side_effect = [
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
            [{'id': 'item-1'}],
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
        ]
        args = argparse.Namespace(
            source_url='https://www.envidat.ch/data/snowslide.zip',
            source_zip=None,
            registry_member=None,
            header=[],
            timeout=300,
            set_key='snowslide-v1',
            source_version='2026-04-25',
            bucket='sar-masks',
            hazard_type='avalanche',
            notes='seed run',
        )

        result = seed_snowslide_truth(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(storage_upload_bytes_mock.call_count, 2)
        requests_get_mock.assert_called_once_with(
            'https://www.envidat.ch/data/snowslide.zip',
            headers={},
            timeout=300,
            stream=True,
        )
        self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
