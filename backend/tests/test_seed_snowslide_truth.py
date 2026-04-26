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
import shapefile
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from backend.scripts.assemble_seed_archive import assemble_seed_archive
from backend.scripts.seed_snowslide_truth import (
    main,
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
        include_metadata_readme: bool = True,
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
                    f'{root}/{scene.get("truth_member_name", "truth_mask.tif")}',
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
                for member_name, member_payload in scene.get('extra_members', []):
                    archive.writestr(f'{root}/{member_name}', member_payload)
            if include_metadata_readme:
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
                    f'{root}/{scene.get("truth_member_name", "truth_mask.tif")}',
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
                for member_name, member_payload in scene.get('extra_members', []):
                    archive.writestr(f'{root}/{member_name}', member_payload)
            archive.writestr('metadata/readme.txt', 'not a registry')
        return payload.getvalue()

    @staticmethod
    def _geotiff_bytes(
        array: np.ndarray,
        *,
        bbox: tuple[float, float, float, float] = (-106.6, 39.4, -106.4, 39.6),
    ) -> bytes:
        data = np.asarray(array, dtype=np.float32)
        if data.ndim == 2:
            data = data[np.newaxis, ...]
        _, height, width = data.shape
        transform = from_bounds(*bbox, width=width, height=height)
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver='GTiff',
                width=width,
                height=height,
                count=int(data.shape[0]),
                dtype='float32',
                crs='EPSG:4326',
                transform=transform,
            ) as dataset:
                dataset.write(data)
            return memory_file.read()

    @staticmethod
    def _geojson_truth_payload() -> bytes:
        return json.dumps({
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'properties': {'id': 'truth-1'},
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [-106.60, 39.40],
                        [-106.60, 39.52],
                        [-106.48, 39.52],
                        [-106.48, 39.40],
                        [-106.60, 39.40],
                    ]],
                },
            }],
        }).encode('utf-8')

    @staticmethod
    def _misaligned_sar_bbox() -> tuple[float, float, float, float]:
        return (-120.0, 35.0, -119.8, 35.2)

    @classmethod
    def _misaligned_vector_scene(cls) -> dict[str, object]:
        return {
            'split': 'validation',
            'region_key': 'davos',
            'scene_id': 'S1A_001',
            'truth_member_name': 'truth_mask.geojson',
            'truth_payload': cls._geojson_truth_payload(),
            'stack_array': None,
            'extra_members': [
                ('stack.tif', cls._geotiff_bytes(
                    np.stack([
                        np.ones((4, 4), dtype=np.float32),
                        np.zeros((4, 4), dtype=np.float32),
                    ], axis=0),
                    bbox=cls._misaligned_sar_bbox(),
                )),
            ],
        }

    @staticmethod
    def _shapefile_truth_members(*, stem: str = 'truth_mask') -> list[tuple[str, bytes]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shp_path = root / f'{stem}.shp'
            with shapefile.Writer(str(shp_path)) as writer:
                writer.field('id', 'C')
                writer.poly([[
                    [-106.60, 39.40],
                    [-106.60, 39.52],
                    [-106.48, 39.52],
                    [-106.48, 39.40],
                    [-106.60, 39.40],
                ]])
                writer.record('truth-1')
            (root / f'{stem}.prj').write_text(
                'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
                'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
                encoding='utf-8',
            )
            members: list[tuple[str, bytes]] = []
            for suffix in ('.shp', '.shx', '.dbf', '.prj'):
                members.append((f'{stem}{suffix}', (root / f'{stem}{suffix}').read_bytes()))
            return members

    @staticmethod
    def _build_args(
        *,
        source_zip: Path | None = None,
        source_url: str | None = None,
        source_dir: Path | None = None,
        source_version: str = '2026-04-25',
        set_key: str = 'snowslide-v1',
    ) -> argparse.Namespace:
        return argparse.Namespace(
            source_url=source_url,
            source_zip=source_zip,
            source_dir=source_dir,
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

    def _write_assembled_source_dir(self, root: Path) -> None:
        scene_root = root / 'validation' / 'davos' / 'davos_2018'
        scene_root.mkdir(parents=True, exist_ok=True)
        for member_name, payload in self._shapefile_truth_members(stem='truth_mask'):
            (scene_root / member_name).write_bytes(payload)
        (scene_root / 'vv.tif').write_bytes(self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
        (scene_root / 'vh.tif').write_bytes(self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

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

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    def test_validate_only_accepts_geojson_truth_with_geotiff_sar_stack(
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
                    'region_key': 'davos',
                    'scene_id': 'S1A_001',
                    'truth_member_name': 'truth_mask.geojson',
                    'truth_payload': self._geojson_truth_payload(),
                    'stack_array': None,
                    'extra_members': [
                        ('stack.tif', self._geotiff_bytes(np.stack([
                            np.ones((4, 4), dtype=np.float32),
                            np.zeros((4, 4), dtype=np.float32),
                        ], axis=0))),
                    ],
                }],
            )
            args = self._build_args(source_zip=archive_path)

            result = validate_snowslide_archive(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)
        rest_upsert_mock.assert_not_called()
        storage_upload_bytes_mock.assert_not_called()
        storage_upsert_json_mock.assert_not_called()

    def test_validate_only_unwraps_nested_dataset_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'outer.zip'
            inner_bytes = self._build_archive_bytes(
                scenes=[{
                    'split': 'validation',
                    'region_key': 'davos',
                    'scene_id': 'S1A_001',
                    'truth_member_name': 'truth_mask.geojson',
                    'truth_payload': self._geojson_truth_payload(),
                    'stack_array': None,
                    'extra_members': [
                        ('stack.tif', self._geotiff_bytes(np.stack([
                            np.ones((4, 4), dtype=np.float32),
                            np.zeros((4, 4), dtype=np.float32),
                        ], axis=0))),
                    ],
                }],
            )
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('DataDescription_EvalSatMappingMethods.pdf', b'%PDF-1.4')
                archive.writestr('Davos_satelliteEvaluationData.zip', inner_bytes)

            result = validate_snowslide_archive(self._build_args(source_zip=archive_path))

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)

    def test_validate_only_accepts_assembled_source_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'assembled_seed_dir'
            self._write_assembled_source_dir(source_dir)

            result = validate_snowslide_archive(self._build_args(source_dir=source_dir))

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)
        self.assertEqual(result['splits'], ['validation'])

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json', return_value='sar-masks/heldout/snowslide/2026-04-25/reference_sets/snowslide-v1/registry.json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    def test_seed_snowslide_truth_accepts_assembled_source_dir(
        self,
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
            source_dir = Path(tmpdir) / 'assembled_seed_dir'
            self._write_assembled_source_dir(source_dir)

            result = seed_snowslide_truth(self._build_args(source_dir=source_dir))

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)
        self.assertEqual(storage_upload_bytes_mock.call_count, 2)

    def test_validate_only_accepts_directory_assembled_from_truth_and_sar_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_archive = tmp_path / 'truth.zip'
            sar_archive = tmp_path / 'sar.zip'
            assembled_dir = tmp_path / 'assembled_seed_dir'

            truth_members = self._shapefile_truth_members(stem='DAvalMap_2018_perimeter')
            inner_truth_payload = io.BytesIO()
            with zipfile.ZipFile(inner_truth_payload, 'w') as inner_archive:
                for member_name, payload in truth_members:
                    inner_archive.writestr(member_name, payload)
                inner_archive.writestr('S1_2018_perimeter.shp', truth_members[0][1])
            with zipfile.ZipFile(truth_archive, 'w') as outer_archive:
                outer_archive.writestr('DataDescription_EvalSatMappingMethods.pdf', b'%PDF-1.4')
                outer_archive.writestr('Davos_satelliteEvaluationData.zip', inner_truth_payload.getvalue())
            with zipfile.ZipFile(sar_archive, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

            assemble_seed_archive(argparse.Namespace(
                truth_zip=truth_archive,
                sar_zip=sar_archive,
                output_dir=assembled_dir,
            ))
            result = validate_snowslide_archive(self._build_args(source_dir=assembled_dir))

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 1)

    @patch('backend.scripts.seed_snowslide_truth.storage_upsert_json', return_value='sar-masks/heldout/snowslide/2026-04-25/reference_sets/snowslide-v1/registry.json')
    @patch('backend.scripts.seed_snowslide_truth.storage_upload_bytes')
    @patch('backend.scripts.seed_snowslide_truth.rest_upsert')
    def test_seed_snowslide_truth_rasterizes_shapefile_truth_against_geotiff_vv_vh(
        self,
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
            self._write_archive(
                archive_path,
                scenes=[{
                    'split': 'validation',
                    'region_key': 'davos',
                    'scene_id': 'S1A_001',
                    'truth_member_name': 'truth_mask.shp',
                    'truth_payload': self._shapefile_truth_members()[0][1],
                    'stack_array': None,
                    'extra_members': self._shapefile_truth_members()[1:] + [
                        ('vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32))),
                        ('vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32))),
                    ],
                }],
            )
            args = self._build_args(source_zip=archive_path)

            result = seed_snowslide_truth(args)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(storage_upload_bytes_mock.call_count, 2)
        truth_upload = storage_upload_bytes_mock.call_args_list[0].kwargs
        self.assertEqual(truth_upload['content_type'], 'image/tiff')
        self.assertGreater(len(truth_upload['payload']), 0)

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

    def test_validate_only_rejects_vector_truth_without_geotiff_sar_grid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[{
                    'split': 'validation',
                    'region_key': 'davos',
                    'scene_id': 'S1A_001',
                    'truth_member_name': 'truth_mask.geojson',
                    'truth_payload': self._geojson_truth_payload(),
                    'stack_array': np.ones((2, 4, 4), dtype=np.float32),
                }],
            )
            args = self._build_args(source_zip=archive_path)

            with self.assertRaisesRegex(ValueError, 'vector truth requires a georeferenced SAR raster grid|not a GeoTIFF'):
                validate_snowslide_archive(args)

    def test_validate_only_returns_invalid_archive_for_non_intersecting_vector_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(
                archive_path,
                scenes=[self._misaligned_vector_scene()],
                include_metadata_readme=False,
            )

            with patch('sys.stdout', new_callable=io.StringIO) as stdout:
                exit_code = main([
                    '--source-zip',
                    str(archive_path),
                    '--set-key',
                    'snowslide-v1',
                    '--source-version',
                    '2026-04-25',
                    '--validate-only',
                ])

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['status'], 'invalid_archive')
        self.assertTrue(payload['reason'].startswith('invalid_footprint_intersection:'))

    def test_seed_snowslide_truth_rejects_non_intersecting_vector_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'snowslide.zip'
            self._write_archive(archive_path, scenes=[self._misaligned_vector_scene()])

            with self.assertRaises(ValueError) as exc:
                seed_snowslide_truth(self._build_args(source_zip=archive_path))

        self.assertTrue(str(exc.exception).startswith('invalid_footprint_intersection:'))

    def test_validate_only_rejects_exact_envidat_vector_record_without_sar_rasters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / 'outer.zip'
            davos_members = self._shapefile_truth_members(stem='DAvalMap_2018_perimeter')
            inner_payload = io.BytesIO()
            with zipfile.ZipFile(inner_payload, 'w') as inner_archive:
                for member_name, payload in davos_members:
                    inner_archive.writestr(member_name, payload)
            with zipfile.ZipFile(archive_path, 'w') as outer_archive:
                outer_archive.writestr('DataDescription_EvalSatMappingMethods.pdf', b'%PDF-1.4')
                outer_archive.writestr('Davos_satelliteEvaluationData.zip', inner_payload.getvalue())

            with self.assertRaisesRegex(ValueError, 'missing paired GeoTIFF VV/VH members|georeferenced SAR raster grid'):
                validate_snowslide_archive(self._build_args(source_zip=archive_path))


if __name__ == '__main__':
    unittest.main()
