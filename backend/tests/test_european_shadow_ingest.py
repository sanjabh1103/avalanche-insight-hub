from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.common.european_shadow_ingest import (
    compute_raw_checksum_manifest,
    load_staged_records,
    stage_european_source,
)
from backend.scripts.stage_european_shadow_data import main as stage_main


class EuropeanShadowIngestTests(unittest.TestCase):
    def test_stage_spot6_geojson_writes_manifest_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'spot6.geojson'
            raw_path.write_text(json.dumps({
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {'id': 'outline-1', 'area_m2': 1250},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [[
                                [8.0, 46.0], [8.1, 46.0], [8.1, 46.1], [8.0, 46.1], [8.0, 46.0],
                            ]],
                        },
                    },
                ],
            }), encoding='utf-8')

            manifest = stage_european_source(
                source_key='swiss_spot6_2018',
                raw_path=raw_path,
                license_review_id='license-review-spot6',
                output_root=root / 'out',
                snapshot_id='snapshot-spot6',
            )
            records = load_staged_records(manifest)

            self.assertEqual(manifest['version'], 'european_shadow_staging_manifest_v1')
            self.assertEqual(manifest['record_count'], 1)
            self.assertFalse(manifest['production_scoring_allowed'])
            self.assertEqual(records[0]['event_time'], '2018-01-24T00:00:00Z')
            self.assertEqual(records[0]['asset_refs']['geometry_ref'], f'{raw_path.resolve()}#feature-1')
            self.assertEqual(records[0]['metadata']['extreme_event_split'], 'swiss_spot6_2018')
            self.assertEqual(records[0]['metadata']['bbox'], [8.0, 46.0, 8.1, 46.1])
            self.assertTrue(Path(manifest['raw_checksum_manifest_path']).exists())
            self.assertTrue(Path(manifest['records_jsonl']).exists())

    def test_missing_license_review_is_rejected_for_shadow_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'epa.csv'
            raw_path.write_text('id,date,site_id\n1,2020-01-02,site-a\n', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'license_review_id'):
                stage_european_source(
                    source_key='french_epa_historical',
                    raw_path=raw_path,
                    license_review_id='',
                    output_root=root / 'out',
                    snapshot_id='snapshot-epa',
                )

    def test_stage_accidents_as_benchmark_not_training_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'accidents.csv'
            raw_path.write_text(
                'event_id,date,caught_count,dead_count,date_accuracy,location_accuracy_m\n'
                'acc-1,2021-02-03,2,1,day,100\n',
                encoding='utf-8',
            )

            manifest = stage_european_source(
                source_key='slf_accident_datasets',
                raw_path=raw_path,
                license_review_id='license-review-slf-accidents',
                output_root=root / 'out',
                snapshot_id='snapshot-accidents',
            )
            records = load_staged_records(manifest)

            self.assertEqual(manifest['requested_role'], 'benchmark')
            self.assertFalse(records[0]['training_eligible'])
            self.assertFalse(records[0]['production_eligible'])
            self.assertEqual(records[0]['metadata']['label_semantics'], 'accident_event_not_occurrence_frequency')
            self.assertEqual(records[0]['metadata']['caught_count'], '2')

    def test_stage_avalcd_records_can_emit_sar_training_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'avalcd.json'
            raw_path.write_text(json.dumps({
                'scenes': [
                    {
                        'scene_id': 'livigno-scene-1',
                        'region_key': 'italian_alps',
                        'stack_ref': str(root / 'stack_manifest.json'),
                        'truth_mask_ref': str(root / 'truth_mask.tif'),
                    },
                ],
            }), encoding='utf-8')

            manifest = stage_european_source(
                source_key='avalcd_zenodo_v1',
                raw_path=raw_path,
                license_review_id='license-review-avalcd',
                output_root=root / 'out',
                snapshot_id='snapshot-avalcd',
                sar_split='val',
            )
            records = load_staged_records(manifest)
            sar_manifest = json.loads(Path(manifest['sar_training_manifest_path']).read_text(encoding='utf-8'))

            self.assertEqual(records[0]['region_key'], 'italian_alps')
            self.assertTrue(records[0]['training_eligible'])
            self.assertEqual(manifest['sar_training_manifest_scene_count'], 1)
            self.assertEqual(sar_manifest['version'], 'sar_training_manifest_v1')
            self.assertEqual(sar_manifest['scenes'][0]['split'], 'val')

    def test_cli_stage_writes_requested_output_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'norway.csv'
            output_copy = root / 'copy.json'
            raw_path.write_text(
                'detection_id,event_time,region_key,detection_probability,temporal_uncertainty_hours,false_positive_review_status\n'
                'det-1,2024-03-01T12:00:00Z,scandinavia_norway,0.82,24,pending\n',
                encoding='utf-8',
            )

            exit_code = stage_main([
                '--source-key', 'norway_sar_activity_monitoring',
                '--raw-path', str(raw_path),
                '--license-review', 'license-review-norway',
                '--snapshot-id', 'snapshot-norway',
                '--output-root', str(root / 'out'),
                '--output', str(output_copy),
            ])

            self.assertEqual(exit_code, 0)
            copied = json.loads(output_copy.read_text(encoding='utf-8'))
            records = load_staged_records(copied)
            self.assertEqual(copied['record_count'], 1)
            self.assertFalse(records[0]['training_eligible'])
            self.assertEqual(records[0]['metadata']['false_positive_review_status'], 'pending')

    def test_checksum_manifest_for_directory_tracks_each_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'a.csv').write_text('id\n1\n', encoding='utf-8')
            (root / 'nested').mkdir()
            (root / 'nested' / 'b.json').write_text('{}\n', encoding='utf-8')

            manifest = compute_raw_checksum_manifest(root)

            self.assertEqual(manifest['path_type'], 'directory')
            self.assertEqual(manifest['file_count'], 2)
            self.assertEqual(
                sorted(file_entry['relative_path'] for file_entry in manifest['files']),
                ['a.csv', 'nested/b.json'],
            )


if __name__ == '__main__':
    unittest.main()
