from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_snowslide_component_review_summary import build_component_review_summary


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _write_component_csv(path: Path) -> Path:
    rows = [
        {
            'scene_id': 'nuuk_20160413',
            'review_priority_rank': 2,
            'component_type': 'false_negative',
            'component_rank': 1,
            'pixel_count': 2700,
            'row_min': 784,
            'row_max_exclusive': 922,
            'col_min': 4493,
            'col_max_exclusive': 4558,
            'centroid_row': 857.1,
            'centroid_col': 4522.5,
            'geo_west': 784863.0,
            'geo_south': 7126750.0,
            'geo_east': 785202.0,
            'geo_north': 7127470.0,
        },
        {
            'scene_id': 'nuuk_20210411',
            'review_priority_rank': 1,
            'component_type': 'false_positive',
            'component_rank': 1,
            'pixel_count': 732,
            'row_min': 1872,
            'row_max_exclusive': 1906,
            'col_min': 2177,
            'col_max_exclusive': 2216,
            'centroid_row': 1888.9,
            'centroid_col': 2197.9,
            'geo_west': 770710.0,
            'geo_south': 7123406.0,
            'geo_east': 770913.0,
            'geo_north': 7123583.0,
        },
        {
            'scene_id': 'pish_20230221',
            'review_priority_rank': 3,
            'component_type': 'false_positive',
            'component_rank': 1,
            'pixel_count': 470,
            'row_min': 414,
            'row_max_exclusive': 447,
            'col_min': 156,
            'col_max_exclusive': 180,
            'centroid_row': 428.7,
            'centroid_col': 168.3,
            'geo_west': 713095.0,
            'geo_south': 4146918.0,
            'geo_east': 713304.0,
            'geo_north': 4147206.0,
        },
    ]
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _scene_packet() -> dict:
    return {
        'review_scenes': [
            {
                'scene_id': 'nuuk_20210411',
                'review_priority_rank': 1,
                'metrics': {
                    'precision': 0.64,
                    'recall': 0.534,
                    'f1': 0.582,
                    'false_positive_rate': 0.0017,
                    'fp_share': 0.292,
                    'fn_share': 0.295,
                },
            },
            {
                'scene_id': 'nuuk_20160413',
                'review_priority_rank': 2,
                'metrics': {
                    'precision': 0.636,
                    'recall': 0.321,
                    'f1': 0.427,
                    'false_positive_rate': 0.0011,
                    'fp_share': 0.142,
                    'fn_share': 0.341,
                },
            },
            {
                'scene_id': 'pish_20230221',
                'review_priority_rank': 3,
                'metrics': {
                    'precision': 0.357,
                    'recall': 0.572,
                    'f1': 0.440,
                    'false_positive_rate': 0.0065,
                    'fp_share': 0.277,
                    'fn_share': 0.075,
                },
            },
        ],
    }


class SnowSlideComponentReviewSummaryTests(unittest.TestCase):
    def test_build_summary_classifies_scenes_and_preserves_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = build_component_review_summary(
                component_review_table=_write_component_csv(root / 'components.csv'),
                scene_review_packet=_write_json(root / 'scene_review_packet.json', _scene_packet()),
                sar_error_diagnostics=_write_json(root / 'sar_error_diagnostics.json', {'dominant_blocker': 'both'}),
                eval_only_recovery_report=_write_json(root / 'recovery.json', {
                    'decision': 'blocked_research_grade',
                    'passing_candidate_count': 0,
                }),
                output_root=root / 'out',
            )

            decisions = {row['scene_id']: row for row in summary['scene_review_decisions']}
            self.assertEqual(decisions['nuuk_20160413']['scene_review_decision'], 'recall_first_label_or_threshold_review')
            self.assertEqual(decisions['nuuk_20210411']['scene_review_decision'], 'mixed_precision_recall_review')
            self.assertEqual(decisions['pish_20230221']['scene_review_decision'], 'precision_first_label_or_terrain_review')
            action = next(row for row in summary['component_review_actions'] if row['scene_id'] == 'nuuk_20160413')
            self.assertEqual(action['component_review_bucket'], 'large_false_negative_label_or_threshold_review')
            self.assertEqual(action['pixel_bbox']['row_min'], 784)
            self.assertEqual(action['pixel_centroid']['col'], 4522.5)
            self.assertEqual(action['geo_bbox']['west'], 784863.0)
            self.assertTrue((root / 'out' / 'component_review_summary.json').exists())
            self.assertTrue((root / 'out' / 'component_review_summary.md').exists())
            self.assertTrue((root / 'out' / 'component_review_actions.csv').exists())

    def test_summary_never_authorizes_gpu_or_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = build_component_review_summary(
                component_review_table=_write_component_csv(root / 'components.csv'),
                scene_review_packet=_write_json(root / 'scene_review_packet.json', _scene_packet()),
                sar_error_diagnostics=_write_json(root / 'sar_error_diagnostics.json', {'dominant_blocker': 'both'}),
                eval_only_recovery_report=_write_json(root / 'recovery.json', {
                    'decision': 'blocked_research_grade',
                    'passing_candidate_count': 0,
                }),
                output_root=root / 'out',
            )

        self.assertEqual(summary['recommended_next_step'], 'manual_scene_label_review')
        self.assertFalse(summary['production_scoring_allowed'])
        self.assertFalse(summary['next_gpu_run_authorized'])
        self.assertFalse(summary['promotion_allowed'])
        self.assertTrue(all(action['blocking_bucket'] == 'no_training_until_reviewed' for action in summary['component_review_actions']))

    def test_missing_input_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaisesRegex(FileNotFoundError, 'required diagnostic input not found'):
                build_component_review_summary(
                    component_review_table=root / 'missing.csv',
                    scene_review_packet=_write_json(root / 'scene_review_packet.json', _scene_packet()),
                    sar_error_diagnostics=_write_json(root / 'sar_error_diagnostics.json', {'dominant_blocker': 'both'}),
                    eval_only_recovery_report=_write_json(root / 'recovery.json', {
                        'decision': 'blocked_research_grade',
                        'passing_candidate_count': 0,
                    }),
                    output_root=root / 'out',
                )


if __name__ == '__main__':
    unittest.main()
