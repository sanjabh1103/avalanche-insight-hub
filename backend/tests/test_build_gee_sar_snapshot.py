from __future__ import annotations

import unittest

from backend.scripts.build_gee_sar_snapshot import build_snapshot


class GeeSarSnapshotTests(unittest.TestCase):
    def test_missing_scene_provenance_blocks_core_training(self) -> None:
        rows, manifest = build_snapshot({
            'himalayas_nepal': [{
                'id': 'db-1',
                'location': 'SRID=4326;POINT(86.0 28.0)',
                'timestamp': '2024-01-10T12:00:00Z',
                'source': 'gee_sar',
                'source_scene_ids': [],
                'features': {'region_key': 'himalayas_nepal', 'scene_count': 2},
            }],
            'pir_panjal_nw_himalaya': [],
        })

        self.assertEqual(len(rows), 1)
        self.assertEqual(manifest['source_scene_id_count'], 0)
        self.assertEqual(manifest['review_status'], 'blocked_missing_source_scene_provenance')
        self.assertFalse(manifest['training_eligible'])
        self.assertEqual(manifest['positive_seasons_by_region']['himalayas_nepal'], ['2023-2024'])

    def test_scene_ids_are_preserved_and_hash_is_stable(self) -> None:
        source = {
            'id': 'db-1',
            'location': 'POINT(86.0 28.0)',
            'timestamp': '2024-01-10T12:00:00Z',
            'source': 'gee_sar',
            'source_scene_ids': ['S1B_TEST'],
            'features': {
                'region_key': 'himalayas_nepal',
                'source_provenance_review_status': 'approved_core',
            },
        }
        first_rows, first_manifest = build_snapshot({'himalayas_nepal': [source]})
        second_rows, second_manifest = build_snapshot({'himalayas_nepal': [source]})

        self.assertEqual(first_rows, second_rows)
        self.assertEqual(first_manifest['event_rows_sha256'], second_manifest['event_rows_sha256'])
        self.assertEqual(first_rows[0]['source_scene_ids'], ['S1B_TEST'])
        self.assertEqual(first_rows[0]['source_provenance_review_status'], 'approved_core')
        self.assertEqual(first_manifest['approved_core_provenance_count'], 1)
        self.assertEqual(first_manifest['review_status'], 'pending_independence_review')

    def test_postgis_ewkb_point_is_decoded(self) -> None:
        rows, manifest = build_snapshot({
            'himalayas_nepal': [{
                'id': 'db-ewkb',
                'location': '0101000020E610000000000000008055400000000000003C40',
                'timestamp': '2024-01-10T12:00:00Z',
                'source': 'gee_sar',
                'source_scene_ids': ['S1_EWKB'],
                'features': {'region_key': 'himalayas_nepal'},
            }],
        })

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['lng'], 86.0)
        self.assertAlmostEqual(rows[0]['lat'], 28.0)
        self.assertEqual(manifest['source_scene_id_count'], 1)


if __name__ == '__main__':
    unittest.main()
