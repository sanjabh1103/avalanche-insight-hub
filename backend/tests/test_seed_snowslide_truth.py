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

from backend.scripts.seed_snowslide_truth import (
    seed_snowslide_truth,
    validate_snowslide_archive,
)


class SeedSnowSlideTruthTests(unittest.TestCase):
    @staticmethod
    def _write_archive(
        path: Path,
        *,
        scenes: list[dict[str, object]] | None = None,
        include_validation: bool = True,
    ) -> None:
        scene_specs = scenes
        if scene_specs is None and include_validation:
            scene_specs = [{
                'split': 'validation',
                'region_key': 'colorado_rockies',
                'scene_id': 'S1A_001',
                'truth_payload': b'geotiff-bytes',
                'stack_array': np.ones((2, 4, 4), dtype=np.float32),
            }]
        with zipfile.ZipFile(path, 'w') as archive:
            for scene in scene_specs or []:
                split = str(scene['split'])
                region_key = str(scene['region_key'])
                scene_id = str(scene['scene_id'])
                root = f'{split}/{region_key}/{scene_id}'
                archive.writestr(
                    f'{root}/truth_mask.tif',
                    scene.get('truth_payload', b'geotiff-bytes'),
                )

                stack_array = scene.get('stack_array')
                if isinstance(stack_array, np.ndarray):
                    stack_payload = io.BytesIO()
                    np.savez(stack_payload, stack=stack_array)
                    archive.writestr(f'{root}/stack.npz', stack_payload.getvalue())
                elif scene.get('stack_payload') is not None:
                    archive.writestr(f'{root}/stack.npz', scene['stack_payload'])
                elif scene.get('vv_array') is not None and scene.get('vh_array') is not None:
                    vv_payload = io.BytesIO()
                    vh_payload = io.BytesIO()
                    np.save(vv_payload, np.asarray(scene['vv_array'], dtype=np.float32))
                    np.save(vh_payload, np.asarray(scene['vh_array'], dtype=np.float32))
                    archive.writestr(f'{root}/vv.npy', vv_payload.getvalue())
                    archive.writestr(f'{root}/vh.npy', vh_payload.getvalue())

                for optical_name, optical_payload in scene.get('optical_members', []):
                    archive.writestr(f'{root}/{optical_name}', optical_payload)
            archive.writestr('metadata/readme.txt', 'not a registry')

    @staticmethod
    def _build_archive_bytes(
        *,
        scenes: list[dict[str, object]] | None = None,
        include_validation: bool = True,
    ) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            if scenes is None and include_validation:
                scenes = [{
                    'split': 'validation',
                    'region_key': 'colorado_rockies',
                    'scene_id': 'S1A_001',
                    'truth_payload': b'geotiff-bytes',
                    'stack_array': np.ones((2, 4, 4), dtype=np.float32),
                }]
            for scene in scenes or []:
                split = str(scene['split'])
                region_key = str(scene['region_key'])
                scene_id = str(scene['scene_id'])
                root = f'{split}/{region_key}/{scene_id}'
                archive.writestr(
                    f'{root}/truth_mask.tif',
                    scene.get('truth_payload', b'geotiff-bytes'),
                )
                stack_array = scene.get('stack_array')
                if isinstance(stack_array, np.ndarray):
                    stack_payload = io.BytesIO()
                    np.savez(stack_payload, stack=stack_array)
                    archive.writestr(f'{root}/stack.npz', stack_payload.getvalue())
                elif scene.get('vv_array') is not None and scene.get('vh_array') is not None:
                    vv_payload = io.BytesIO()
                    vh_payload = io.BytesIO()
                    np.save(vv_payload, np.asarray(scene['vv_array'], dtype=np.float32))
                    np.save(vh_payload, np.asarray(scene['vh_array'], dtype=np.float32))
                    archive.writestr(f'{root}/vv.npy', vv_payload.getvalue())
                    archive.writestr(f'{root}/vh.npy', vh_payload.getvalue())
                for optical_name, optical_payload in scene.get('optical_members', []):
                    archive.writestr(f'{root}/{optical_name}', optical_payload)
            archive.writestr('metadata/readme.txt', 'not a registry')
        return payload.getvalue()

    @staticmethod
    def _build_args(
        *,
        source_zip: Path | None = None,
        source_url: str | None = None,
        source_version: str = '2026-04-25',
        set_key: str = 'snowslide-v1',
    ) -> argparse.Namespace:
        return argparse.Namespace(
            source_url=source_url,
            source_zip=source_zip,
            registry_member=None,
            header=[],
            timeout=300,
            set_key=set_key,
            source_version=source_version,
            bucket='sar-masks',
            hazard_type='avalanche',
            notes='seed run',
            validate_only=False,
        )

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
            args = self._build_args(source_zip=archive_path)

            result = seed_snowslide_truth(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)
        self.assertEqual(result['splits'], ['validation'])
        self.assertEqual(storage_upload_bytes_mock.call_count, 2)
        item_upsert = rest_upsert_mock.call_args_list[1]
        self.assertEqual(item_upsert.kwargs['on_conflict'], 'reference_set_id,external_scene_id')
        inserted_row = item_upsert.args[1][0]
        self.assertEqual(inserted_row['truth_mask_asset_ref'], 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif')
        self.assertEqual(inserted_row['stack_asset_ref'], 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz')
        set_insert = rest_upsert_mock.call_args_list[0].args[1][0]
        set_update = rest_upsert_mock.call_args_list[2].args[1][0]
        self.assertEqual(set_insert['split_name'], 'validation')
        self.assertEqual(set_update['split_name'], 'validation')

    def test_seed_snowslide_truth_rejects_archives_without_validation_or_test_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(archive_path, include_validation=False)
            args = self._build_args(source_zip=archive_path)

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
            args = self._build_args(source_zip=archive_path)

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
        args = self._build_args(source_url='https://www.envidat.ch/data/snowslide.zip')

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

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json', return_value='sar-masks/heldout/snowslide/2026-04-25/reference_sets/snowslide-v1/registry.json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    def test_seed_snowslide_truth_preserves_archive_derived_multi_split_name(
        self,
        rest_upsert_mock,
        storage_upload_bytes_mock,
        _storage_upsert_json_mock,
    ) -> None:
        rest_upsert_mock.side_effect = [
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
            [{'id': 'item-1'}, {'id': 'item-2'}],
            [{'id': 'set-1', 'set_key': 'snowslide-v1', 'status': 'draft'}],
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[
                    {
                        'split': 'validation',
                        'region_key': 'colorado_rockies',
                        'scene_id': 'S1A_001',
                        'truth_payload': b'validation-truth',
                        'stack_array': np.ones((2, 4, 4), dtype=np.float32),
                    },
                    {
                        'split': 'test',
                        'region_key': 'wasatch',
                        'scene_id': 'S1A_002',
                        'truth_payload': b'test-truth',
                        'stack_array': np.ones((2, 4, 4), dtype=np.float32),
                    },
                ],
            )
            args = self._build_args(source_zip=archive_path)

            result = seed_snowslide_truth(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['splits'], ['test', 'validation'])
        self.assertEqual(rest_upsert_mock.call_args_list[0].args[1][0]['split_name'], 'test+validation')
        self.assertEqual(rest_upsert_mock.call_args_list[2].args[1][0]['split_name'], 'test+validation')
        self.assertEqual(storage_upload_bytes_mock.call_count, 4)

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    def test_validate_only_succeeds_without_mutating_remote_state(
        self,
        rest_upsert_mock,
        storage_upload_bytes_mock,
        storage_upsert_json_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[{
                    'split': 'validation',
                    'region_key': 'colorado_rockies',
                    'scene_id': 'S1A_001',
                    'truth_payload': b'geotiff-bytes',
                    'vv_array': np.ones((4, 4), dtype=np.float32),
                    'vh_array': np.zeros((4, 4), dtype=np.float32),
                }],
            )
            args = self._build_args(source_zip=archive_path)

            result = validate_snowslide_archive(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)
        self.assertEqual(result['splits'], ['validation'])
        self.assertEqual(result['split_name'], 'validation')
        rest_upsert_mock.assert_not_called()
        storage_upload_bytes_mock.assert_not_called()
        storage_upsert_json_mock.assert_not_called()

    def test_validate_only_rejects_optical_webcam_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[{
                    'split': 'validation',
                    'region_key': 'colorado_rockies',
                    'scene_id': 'S1A_001',
                    'truth_payload': b'geotiff-bytes',
                    'optical_members': [('frame001.jpg', b'jpeg-bytes')],
                }],
            )
            args = self._build_args(source_zip=archive_path)

            with self.assertRaisesRegex(ValueError, 'optical/webcam imagery|optical datasets are invalid'):
                validate_snowslide_archive(args)

    def test_validate_only_rejects_non_two_channel_stack_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[{
                    'split': 'validation',
                    'region_key': 'colorado_rockies',
                    'scene_id': 'S1A_001',
                    'truth_payload': b'geotiff-bytes',
                    'stack_array': np.ones((3, 4, 4), dtype=np.float32),
                }],
            )
            args = self._build_args(source_zip=archive_path)

            with self.assertRaisesRegex(ValueError, '2-channel stack'):
                validate_snowslide_archive(args)

    def test_validate_only_rejects_truth_only_archives_without_sar_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[{
                    'split': 'validation',
                    'region_key': 'colorado_rockies',
                    'scene_id': 'S1A_001',
                    'truth_payload': b'geotiff-bytes',
                }],
            )
            args = self._build_args(source_zip=archive_path)

            with self.assertRaisesRegex(ValueError, 'stack_member or both vv_member and vh_member'):
                validate_snowslide_archive(args)


if __name__ == '__main__':
    unittest.main()
