from __future__ import annotations

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import shapefile
from rasterio.warp import transform

from backend.scripts.build_everest_sar_snapshot import build_snapshot


class EverestSarSnapshotTests(unittest.TestCase):
    def _archive(self) -> bytes:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shp_path = root / 'ASC_20180101-20180113'
            writer = shapefile.Writer(str(shp_path), shapeType=shapefile.POLYGON)
            writer.field('id', 'N')
            x_values, y_values = transform('EPSG:4326', 'EPSG:32645', [86.7], [27.9])
            x, y = float(x_values[0]), float(y_values[0])
            writer.poly([[
                [x - 100, y - 100], [x + 100, y - 100],
                [x + 100, y + 100], [x - 100, y + 100],
                [x - 100, y - 100],
            ]])
            writer.record(1)
            writer.close()
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_STORED) as archive:
                for suffix in ('.shp', '.shx', '.dbf'):
                    archive.write(
                        str(shp_path) + suffix,
                        'Everest/Automated_outlines_dates_ManualUpd/ASC_20180101-20180113' + suffix,
                    )
            return payload.getvalue()

    def test_interval_bounds_are_preserved_without_fabricated_event_time(self) -> None:
        rows, manifest = build_snapshot(
            self._archive(),
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )

        self.assertEqual(len(rows), 1)
        self.assertNotIn('event_time', rows[0])
        self.assertEqual(rows[0]['event_time_start'], '2018-01-01T00:00:00Z')
        self.assertEqual(rows[0]['event_time_end'], '2018-01-13T00:00:00Z')
        self.assertEqual(rows[0]['timestamp_precision'], 'bounded_12_day_detection_interval')
        self.assertEqual(rows[0]['origin_source_family'], 'everest_sentinel1_satellite_detection')
        self.assertEqual(rows[0]['region_key'], 'himalayas_nepal')
        self.assertAlmostEqual(rows[0]['lat'], 27.9, places=3)
        self.assertAlmostEqual(rows[0]['lng'], 86.7, places=3)
        self.assertFalse(manifest['training_eligible'])
        self.assertEqual(manifest['positive_season_ids'], ['2017-2018'])
        self.assertEqual(manifest['exact_timestamp_record_count'], 0)
        self.assertEqual(manifest['source_overlap_report'], 'source_overlap_report.json')

    def test_output_is_stable_for_same_archive(self) -> None:
        archive = self._archive()
        first_rows, first_manifest = build_snapshot(
            archive,
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )
        second_rows, second_manifest = build_snapshot(
            archive,
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )

        self.assertEqual(first_rows, second_rows)
        self.assertEqual(first_manifest['event_rows_sha256'], second_manifest['event_rows_sha256'])
        self.assertEqual(first_manifest['source_archive_sha256'], second_manifest['source_archive_sha256'])


if __name__ == '__main__':
    unittest.main()
