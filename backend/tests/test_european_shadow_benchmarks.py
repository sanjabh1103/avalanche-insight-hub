from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.common.european_shadow_benchmarks import build_european_shadow_benchmark_report
from backend.common.european_shadow_ingest import stage_european_source
from backend.scripts.run_european_shadow_benchmarks import main as benchmark_main


class EuropeanShadowBenchmarkTests(unittest.TestCase):
    def test_benchmark_report_keeps_production_blocked_and_reports_activity_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'norway.csv'
            raw_path.write_text(
                'detection_id,event_time,region_key,detection_probability,temporal_uncertainty_hours,false_positive_review_status\n'
                'det-1,2024-03-01T12:00:00Z,scandinavia_norway,0.82,24,pending\n'
                'det-2,2024-03-20T12:00:00Z,scandinavia_norway,0.91,12,confirmed\n',
                encoding='utf-8',
            )
            manifest = stage_european_source(
                source_key='norway_sar_activity_monitoring',
                raw_path=raw_path,
                license_review_id='license-review-norway',
                output_root=root / 'out',
                snapshot_id='snapshot-norway',
            )

            report = build_european_shadow_benchmark_report(staging_manifests=[manifest])
            source_report = report['source_reports'][0]

            self.assertFalse(report['production_scoring_allowed'])
            self.assertFalse(report['promotion_gate_report']['allowed'])
            self.assertIn('sar_detection_activity', report['summary_by_lane'])
            self.assertEqual(source_report['activity_rate_benchmark']['counts_by_month'], {'2024-03': 2})
            self.assertEqual(
                source_report['activity_rate_benchmark']['false_positive_review_status_counts'],
                {'confirmed': 1, 'pending': 1},
            )

    def test_sar_and_danger_reports_are_pending_predictions_without_model_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            avalcd_raw = root / 'avalcd.json'
            danger_raw = root / 'danger.json'
            avalcd_raw.write_text(json.dumps({
                'scenes': [{
                    'scene_id': 'tromso-scene-1',
                    'region_key': 'scandinavia_norway',
                    'stack_ref': str(root / 'stack.json'),
                    'truth_mask_ref': str(root / 'mask.tif'),
                }],
            }), encoding='utf-8')
            danger_raw.write_text(json.dumps({
                'bulletins': [{
                    'id': 'bulletin-1',
                    'activeAt': '2024-02-01T00:00:00+01:00',
                    'region_key': 'swiss_alps',
                    'danger_level': 3,
                }],
            }), encoding='utf-8')
            avalcd_manifest = stage_european_source(
                source_key='avalcd_zenodo_v1',
                raw_path=avalcd_raw,
                license_review_id='license-review-avalcd',
                output_root=root / 'out',
                snapshot_id='snapshot-pending',
            )
            danger_manifest = stage_european_source(
                source_key='slf_bulletin_caaml',
                raw_path=danger_raw,
                license_review_id='license-review-caaml',
                output_root=root / 'out',
                snapshot_id='snapshot-pending',
            )

            report = build_european_shadow_benchmark_report(
                staging_manifests=[avalcd_manifest, danger_manifest],
                snapshot_id='benchmark-pending',
            )
            statuses = {item['source_key']: item['benchmark_status']['status'] for item in report['source_reports']}

            self.assertEqual(statuses['avalcd_zenodo_v1'], 'pending_predictions')
            self.assertEqual(statuses['slf_bulletin_caaml'], 'pending_predictions')
            self.assertTrue(any('prediction benchmarks' in blocker for blocker in report['promotion_gate_report']['blockers']))

    def test_accident_and_bulletin_audits_block_occurrence_label_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            accident_raw = root / 'accidents.csv'
            bulletin_raw = root / 'eaws.json'
            accident_raw.write_text('event_id,date,region_key,dead_count\nacc-1,2022-01-01,swiss_alps,1\n', encoding='utf-8')
            bulletin_raw.write_text(json.dumps({
                'items': [{
                    'id': 'ctx-1',
                    'activeAt': '2022-01-01T00:00:00Z',
                    'region_key': 'french_alps',
                    'danger_level': 4,
                }],
            }), encoding='utf-8')
            accident_manifest = stage_european_source(
                source_key='slf_accident_datasets',
                raw_path=accident_raw,
                license_review_id='license-review-accidents',
                output_root=root / 'out',
                snapshot_id='snapshot-audit',
            )
            bulletin_manifest = stage_european_source(
                source_key='eaws_bulletin_context',
                raw_path=bulletin_raw,
                license_review_id='license-review-eaws',
                output_root=root / 'out',
                snapshot_id='snapshot-audit',
            )

            report = build_european_shadow_benchmark_report(staging_manifests=[accident_manifest, bulletin_manifest])
            audits = {
                source_report['source_key']: {audit['audit']: audit['status'] for audit in source_report['bias_audits']}
                for source_report in report['source_reports']
            }

            self.assertEqual(audits['slf_accident_datasets']['accident_only_bias'], 'blocked_for_frequency_training')
            self.assertEqual(audits['eaws_bulletin_context']['forecast_not_observation'], 'blocked_for_occurrence_labels')

    def test_cli_benchmark_writes_output_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / 'epa.csv'
            output_path = root / 'benchmark.json'
            raw_path.write_text('event_id,date,region_key,site_id\nepa-1,2020-01-01,french_alps,path-1\n', encoding='utf-8')
            manifest = stage_european_source(
                source_key='french_epa_historical',
                raw_path=raw_path,
                license_review_id='license-review-epa',
                output_root=root / 'out',
                snapshot_id='snapshot-cli',
            )
            manifest_path = Path(manifest['records_jsonl']).parent / 'staged_manifest.json'

            exit_code = benchmark_main([
                '--manifest', str(manifest_path),
                '--snapshot-id', 'benchmark-cli',
                '--output', str(output_path),
            ])

            self.assertEqual(exit_code, 0)
            report = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(report['snapshot_id'], 'benchmark-cli')
            self.assertFalse(report['production_scoring_allowed'])
            self.assertEqual(report['source_reports'][0]['observability_bias_audit']['site_count'], 1)


if __name__ == '__main__':
    unittest.main()
