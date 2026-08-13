from __future__ import annotations

import csv
import io
import json
import unittest

from backend.scripts.build_hiaval_snapshot import build_snapshot


def _payload() -> bytes:
    fields = [
        'Location', 'Year', 'Month', 'Day', 'Latitude', 'Longitude',
        'Country', 'Region_HiMAP', 'Type', 'Impact', 'Fatalities',
        'Injured', 'Livestock', 'Leisure', 'Remarks', 'Reference',
    ]
    rows = [
        ['Nepal-1', '2020', '11', '3', '28.0', '86.0', 'Nepal', '1', 'snow avalanche', 'Y', '', '', '', '', '', 'ref-1'],
        ['Nepal-2', '2021', '11', '3', '28.1', '86.1', 'Nepal', '1', 'snow avalanche', 'Y', '', '', '', '', '', 'ref-2'],
        ['Pir-1', '2022', '12', '3', '34.0', '74.5', 'India', '1', 'slab avalanche', 'Y', '', '', '', '', '', 'ref-3'],
        ['No-date', '2023', 'NA', '3', '28.0', '86.0', 'Nepal', '1', 'snow avalanche', 'Y', '', '', '', '', '', 'ref-4'],
        ['Glacier', '2024', '12', '3', '28.0', '86.0', 'Nepal', '1', 'glacier detachment', 'Y', '', '', '', '', '', 'ref-5'],
    ]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(fields)
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


class HiAVALSnapshotTests(unittest.TestCase):
    def test_snapshot_is_targeted_dated_and_season_aware(self) -> None:
        rows, manifest = build_snapshot(
            _payload(),
            target_regions={
                'himalayas_nepal': (27.0, 85.0, 29.0, 87.5),
                'pir_panjal_nw_himalaya': (33.0, 73.5, 35.0, 75.5),
            },
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(manifest['included_record_count'], 3)
        self.assertEqual(manifest['label_time_contract'], 'interval_censored_core_v1')
        self.assertFalse(manifest['interval_training_ready'])
        self.assertEqual(manifest['excluded_record_counts']['partial_date'], 1)
        self.assertEqual(manifest['excluded_record_counts']['excluded_glacier_detachment'], 1)
        self.assertEqual(manifest['positive_season_count'], 3)
        self.assertEqual(manifest['positive_seasons_by_region']['himalayas_nepal'], ['2020-2021', '2021-2022'])
        self.assertEqual(rows[0]['source_key'], 'hiaval_hma')
        self.assertEqual(rows[0]['timestamp_precision'], 'day')
        self.assertEqual(rows[0]['location_precision'], 'point_from_source_database')
        self.assertNotIn('event_time', rows[0])
        self.assertEqual(rows[0]['event_time_start'], '2020-11-03T00:00:00Z')
        self.assertEqual(rows[0]['event_time_end'], '2020-11-04T00:00:00Z')
        self.assertTrue(rows[0]['event_group_id'].startswith('hiaval:hiaval-'))
        self.assertEqual(rows[0]['origin_source_family'], 'hiaval_literature_database')

    def test_snapshot_hash_is_stable_for_same_payload(self) -> None:
        first_rows, first_manifest = build_snapshot(
            _payload(),
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )
        second_rows, second_manifest = build_snapshot(
            _payload(),
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )
        self.assertEqual(first_rows, second_rows)
        self.assertEqual(first_manifest['source_sha256'], second_manifest['source_sha256'])
        self.assertEqual(first_manifest['event_rows_sha256'], second_manifest['event_rows_sha256'])


if __name__ == '__main__':
    unittest.main()
