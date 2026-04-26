from __future__ import annotations

import argparse
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import shapefile
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from backend.scripts.assemble_seed_archive import assemble_seed_archive


class AssembleSeedArchiveTests(unittest.TestCase):
    DEFAULT_POLYGON = [
        [-106.60, 39.40],
        [-106.60, 39.52],
        [-106.48, 39.52],
        [-106.48, 39.40],
        [-106.60, 39.40],
    ]

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
    def _shapefile_truth_members(
        *,
        stem: str,
        polygon: list[list[float]] | None = None,
    ) -> list[tuple[str, bytes]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shp_path = root / f'{stem}.shp'
            with shapefile.Writer(str(shp_path)) as writer:
                writer.field('id', 'C')
                writer.poly([polygon or AssembleSeedArchiveTests.DEFAULT_POLYGON])
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

    def test_assemble_seed_archive_unwraps_nested_truth_zip_and_pairs_vv_vh(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            truth_members = self._shapefile_truth_members(stem='DAvalMap_2018_perimeter')
            nested_truth = io.BytesIO()
            with zipfile.ZipFile(nested_truth, 'w') as archive:
                for member_name, payload in truth_members:
                    archive.writestr(member_name, payload)
                archive.writestr('DataDescription.txt', 'truth docs')
            with zipfile.ZipFile(truth_zip, 'w') as archive:
                archive.writestr('DataDescription_EvalSatMappingMethods.pdf', b'%PDF-1.4')
                archive.writestr('Davos_satelliteEvaluationData.zip', nested_truth.getvalue())

            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

            result = assemble_seed_archive(argparse.Namespace(
                truth_zip=truth_zip,
                sar_zip=sar_zip,
                output_dir=output_dir,
            ))

            scene_root = output_dir / 'validation' / 'davos' / 'davos_2018'
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['scene_count'], 1)
            self.assertTrue((scene_root / 'truth_mask.shp').exists())
            self.assertTrue((scene_root / 'truth_mask.dbf').exists())
            self.assertTrue((scene_root / 'truth_mask.shx').exists())
            self.assertTrue((scene_root / 'vv.tif').exists())
            self.assertTrue((scene_root / 'vh.tif').exists())

    def test_assemble_seed_archive_ignores_davos_auxiliary_layers_in_raw_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            davos_2018 = self._shapefile_truth_members(stem='DAvalMap_2018_perimeter')
            davos_2019 = self._shapefile_truth_members(
                stem='DAvalMap_2019_perimeter',
                polygon=[
                    [-106.58, 39.41],
                    [-106.58, 39.50],
                    [-106.46, 39.50],
                    [-106.46, 39.41],
                    [-106.58, 39.41],
                ],
            )
            coverage_2018 = self._shapefile_truth_members(
                stem='GroundTruthCoverage_2018',
                polygon=[
                    [-106.64, 39.36],
                    [-106.64, 39.56],
                    [-106.44, 39.56],
                    [-106.44, 39.36],
                    [-106.64, 39.36],
                ],
            )
            coverage_2019 = self._shapefile_truth_members(
                stem='GroundTruthCoverage_2019',
                polygon=[
                    [-106.66, 39.35],
                    [-106.66, 39.57],
                    [-106.42, 39.57],
                    [-106.42, 39.35],
                    [-106.66, 39.35],
                ],
            )
            nested_truth = io.BytesIO()
            with zipfile.ZipFile(nested_truth, 'w') as archive:
                for member_set in (davos_2018, davos_2019, coverage_2018, coverage_2019):
                    for member_name, payload in member_set:
                        archive.writestr(member_name, payload)
                archive.writestr('DataDescription.txt', 'truth docs')
            with zipfile.ZipFile(truth_zip, 'w') as archive:
                archive.writestr('DataDescription_EvalSatMappingMethods.pdf', b'%PDF-1.4')
                archive.writestr('Davos_satelliteEvaluationData.zip', nested_truth.getvalue())

            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))
                archive.writestr('S1_2019_vv.tif', self._geotiff_bytes(np.full((4, 4), 2.0, dtype=np.float32)))
                archive.writestr('S1_2019_vh.tif', self._geotiff_bytes(np.full((4, 4), -1.0, dtype=np.float32)))

            result = assemble_seed_archive(argparse.Namespace(
                truth_zip=truth_zip,
                sar_zip=sar_zip,
                output_dir=output_dir,
            ))

            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['scene_count'], 2)

            expected_davos = {
                '2018': dict(davos_2018),
                '2019': dict(davos_2019),
            }
            unexpected_coverage = {
                '2018': dict(coverage_2018),
                '2019': dict(coverage_2019),
            }
            for year in ('2018', '2019'):
                scene_root = output_dir / 'validation' / 'davos' / f'davos_{year}'
                self.assertEqual(
                    (scene_root / 'truth_mask.shp').read_bytes(),
                    expected_davos[year][f'DAvalMap_{year}_perimeter.shp'],
                )
                self.assertNotEqual(
                    (scene_root / 'truth_mask.shp').read_bytes(),
                    unexpected_coverage[year][f'GroundTruthCoverage_{year}.shp'],
                )

    def test_assemble_seed_archive_pairs_all_truth_years(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            with zipfile.ZipFile(truth_zip, 'w') as archive:
                for stem in ('DAvalMap_2018_perimeter', 'DAvalMap_2019_perimeter'):
                    for member_name, payload in self._shapefile_truth_members(stem=stem):
                        archive.writestr(member_name, payload)
            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))
                archive.writestr('S1_2019_vv.tif', self._geotiff_bytes(np.full((4, 4), 2.0, dtype=np.float32)))
                archive.writestr('S1_2019_vh.tif', self._geotiff_bytes(np.full((4, 4), -1.0, dtype=np.float32)))

            result = assemble_seed_archive(argparse.Namespace(
                truth_zip=truth_zip,
                sar_zip=sar_zip,
                output_dir=output_dir,
            ))

            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['scene_count'], 2)
            self.assertEqual(
                {(scene['scene_id'], scene['year']) for scene in result['scenes']},
                {('davos_2018', '2018'), ('davos_2019', '2019')},
            )
            for year in ('2018', '2019'):
                scene_root = output_dir / 'validation' / 'davos' / f'davos_{year}'
                self.assertTrue((scene_root / 'truth_mask.shp').exists())
                self.assertTrue((scene_root / 'vv.tif').exists())
                self.assertTrue((scene_root / 'vh.tif').exists())

    def test_assemble_seed_archive_rejects_missing_vh_raster(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            with zipfile.ZipFile(truth_zip, 'w') as archive:
                for member_name, payload in self._shapefile_truth_members(stem='DAvalMap_2018_perimeter'):
                    archive.writestr(member_name, payload)
            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))

            with self.assertRaisesRegex(ValueError, 'missing paired VV/VH GeoTIFFs'):
                assemble_seed_archive(argparse.Namespace(
                    truth_zip=truth_zip,
                    sar_zip=sar_zip,
                    output_dir=output_dir,
                ))

    def test_assemble_seed_archive_rejects_auxiliary_only_truth_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            with zipfile.ZipFile(truth_zip, 'w') as archive:
                for stem in ('GroundTruthCoverage_2018', 'GroundTruthCoverage_2019'):
                    for member_name, payload in self._shapefile_truth_members(stem=stem):
                        archive.writestr(member_name, payload)
            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

            with self.assertRaisesRegex(ValueError, 'truth archive does not contain any supported truth vectors'):
                assemble_seed_archive(argparse.Namespace(
                    truth_zip=truth_zip,
                    sar_zip=sar_zip,
                    output_dir=output_dir,
                ))

    def test_assemble_seed_archive_rejects_duplicate_band_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            with zipfile.ZipFile(truth_zip, 'w') as archive:
                for member_name, payload in self._shapefile_truth_members(stem='DAvalMap_2018_perimeter'):
                    archive.writestr(member_name, payload)
            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vv_db.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

            with self.assertRaisesRegex(ValueError, 'duplicate VV raster candidates'):
                assemble_seed_archive(argparse.Namespace(
                    truth_zip=truth_zip,
                    sar_zip=sar_zip,
                    output_dir=output_dir,
                ))

    def test_assemble_seed_archive_rejects_year_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            with zipfile.ZipFile(truth_zip, 'w') as archive:
                for member_name, payload in self._shapefile_truth_members(stem='DAvalMap_2018_perimeter'):
                    archive.writestr(member_name, payload)
            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2019_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2019_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

            with self.assertRaisesRegex(ValueError, 'missing truth-matched VV/VH rasters|unmatched VV/VH rasters'):
                assemble_seed_archive(argparse.Namespace(
                    truth_zip=truth_zip,
                    sar_zip=sar_zip,
                    output_dir=output_dir,
                ))

    def test_assemble_seed_archive_preserves_generic_truth_filename_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            truth_zip = tmp_path / 'truth.zip'
            sar_zip = tmp_path / 'sar.zip'
            output_dir = tmp_path / 'assembled'

            with zipfile.ZipFile(truth_zip, 'w') as archive:
                for member_name, payload in self._shapefile_truth_members(stem='truth_2018_mask'):
                    archive.writestr(f'colorado_rockies/{member_name}', payload)
            with zipfile.ZipFile(sar_zip, 'w') as archive:
                archive.writestr('S1_2018_vv.tif', self._geotiff_bytes(np.ones((4, 4), dtype=np.float32)))
                archive.writestr('S1_2018_vh.tif', self._geotiff_bytes(np.zeros((4, 4), dtype=np.float32)))

            result = assemble_seed_archive(argparse.Namespace(
                truth_zip=truth_zip,
                sar_zip=sar_zip,
                output_dir=output_dir,
            ))

            scene_root = output_dir / 'validation' / 'colorado_rockies' / 'colorado_rockies_2018'
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['scene_count'], 1)
            self.assertEqual(result['scenes'], [{'year': '2018', 'region_key': 'colorado_rockies', 'scene_id': 'colorado_rockies_2018'}])
            self.assertTrue((scene_root / 'truth_mask.shp').exists())
            self.assertTrue((scene_root / 'vv.tif').exists())
            self.assertTrue((scene_root / 'vh.tif').exists())


if __name__ == '__main__':
    unittest.main()
