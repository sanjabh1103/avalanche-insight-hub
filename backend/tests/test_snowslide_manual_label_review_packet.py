from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_snowslide_manual_label_review_packet import build_manual_label_review_packet
from backend.scripts.resolve_snowslide_manual_label_review import resolve_manual_label_review


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _component_actions(path: Path) -> Path:
    rows = [
        {
            'scene_id': 'nuuk_20160413',
            'review_priority_rank': 2,
            'scene_review_decision': 'recall_first_label_or_threshold_review',
            'scene_review_buckets': 'scene_systematic_recall_gap;no_training_until_reviewed',
            'component_type': 'false_negative',
            'component_rank': 1,
            'component_review_bucket': 'large_false_negative_label_or_threshold_review',
            'blocking_bucket': 'no_training_until_reviewed',
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
            'scene_review_decision': 'mixed_precision_recall_review',
            'scene_review_buckets': 'scene_systematic_precision_gap;scene_systematic_recall_gap;no_training_until_reviewed',
            'component_type': 'false_positive',
            'component_rank': 1,
            'component_review_bucket': 'large_false_positive_label_or_terrain_review',
            'blocking_bucket': 'no_training_until_reviewed',
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
            'scene_review_decision': 'precision_first_label_or_terrain_review',
            'scene_review_buckets': 'scene_systematic_precision_gap;no_training_until_reviewed',
            'component_type': 'false_positive',
            'component_rank': 1,
            'component_review_bucket': 'large_false_positive_label_or_terrain_review',
            'blocking_bucket': 'no_training_until_reviewed',
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


def _summary() -> dict:
    return {
        'decision': 'manual_scene_label_review_required',
        'production_scoring_allowed': False,
        'next_gpu_run_authorized': False,
        'scene_review_decisions': [
            {
                'scene_id': 'nuuk_20210411',
                'review_priority_rank': 1,
                'scene_review_decision': 'mixed_precision_recall_review',
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
                'scene_review_decision': 'recall_first_label_or_threshold_review',
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
                'scene_review_decision': 'precision_first_label_or_terrain_review',
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


def _write_packet_inputs(root: Path) -> dict[str, Path]:
    return {
        'component_review_actions': _component_actions(root / 'component_review_actions.csv'),
        'component_review_summary': _write_json(root / 'component_review_summary.json', _summary()),
        'scene_review_packet': _write_json(root / 'scene_review_packet.json', {
            'review_scenes': _summary()['scene_review_decisions'],
        }),
        'sar_error_diagnostics': _write_json(root / 'sar_error_diagnostics.json', {
            'dominant_blocker': 'both',
            'decision': 'blocked_shadow_only',
        }),
        'eval_only_recovery_report': _write_json(root / 'snowslide_eval_only_recovery_report.json', {
            'decision': 'blocked_research_grade',
            'passing_candidate_count': 0,
        }),
    }


def _build_packet(root: Path) -> dict:
    inputs = _write_packet_inputs(root)
    return build_manual_label_review_packet(
        component_review_actions=inputs['component_review_actions'],
        component_review_summary=inputs['component_review_summary'],
        scene_review_packet=inputs['scene_review_packet'],
        sar_error_diagnostics=inputs['sar_error_diagnostics'],
        eval_only_recovery_report=inputs['eval_only_recovery_report'],
        output_root=root / 'out',
    )


def _read_decisions(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_decisions(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class SnowSlideManualLabelReviewPacketTests(unittest.TestCase):
    def test_packet_preserves_review_geometry_and_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            packet = _build_packet(root)

            self.assertEqual(packet['decision'], 'manual_scene_label_review_required')
            self.assertFalse(packet['production_scoring_allowed'])
            self.assertFalse(packet['next_gpu_run_authorized'])
            self.assertFalse(packet['promotion_allowed'])
            item = next(row for row in packet['component_review_items'] if row['scene_id'] == 'nuuk_20160413')
            self.assertEqual(item['action_id'], 'nuuk_20160413__false_negative__001')
            self.assertEqual(item['pixel_bbox']['row_min'], 784)
            self.assertEqual(item['pixel_centroid']['col'], 4522.5)
            self.assertEqual(item['geo_bbox']['west'], 784863.0)
            self.assertIn('missed truth component', item['review_question'])
            self.assertTrue((root / 'out' / 'manual_label_review_packet.json').exists())
            self.assertTrue((root / 'out' / 'manual_label_review_decisions.csv').exists())
            worksheet = _read_decisions(root / 'out' / 'manual_label_review_decisions.csv')
            self.assertTrue(all(row['review_status'] == 'pending' for row in worksheet))

    def test_pending_worksheet_resolves_to_review_incomplete_without_authorizing_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _build_packet(root)
            outcome = resolve_manual_label_review(
                manual_label_review_decisions=root / 'out' / 'manual_label_review_decisions.csv',
                manual_label_review_packet=root / 'out' / 'manual_label_review_packet.json',
                output_root=root / 'out',
            )

            self.assertEqual(outcome['decision'], 'review_incomplete')
            self.assertEqual(outcome['pending_component_count'], 3)
            self.assertFalse(outcome['production_scoring_allowed'])
            self.assertFalse(outcome['next_gpu_run_authorized'])
            self.assertFalse(outcome['future_candidate_design_warranted'])

    def test_packet_builder_preserves_existing_completed_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _build_packet(root)
            worksheet = root / 'out' / 'manual_label_review_decisions.csv'
            rows = _read_decisions(worksheet)
            rows[0]['review_status'] = 'reviewed'
            rows[0]['component_decision'] = 'valid_model_miss'
            rows[0]['requires_label_edit'] = 'false'
            rows[0]['scene_decision'] = 'labels_valid_model_gap'
            rows[0]['reviewer_notes'] = 'completed review should survive packet regeneration'
            _write_decisions(worksheet, rows)

            _build_packet(root)

            regenerated = _read_decisions(worksheet)
            self.assertEqual(regenerated[0]['review_status'], 'reviewed')
            self.assertEqual(regenerated[0]['component_decision'], 'valid_model_miss')
            self.assertEqual(regenerated[0]['scene_decision'], 'labels_valid_model_gap')
            self.assertEqual(regenerated[0]['reviewer_notes'], 'completed review should survive packet regeneration')

    def test_invalid_component_decision_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _build_packet(root)
            worksheet = root / 'out' / 'manual_label_review_decisions.csv'
            rows = _read_decisions(worksheet)
            for row in rows:
                row['review_status'] = 'reviewed'
                row['component_decision'] = 'not_a_valid_decision'
                row['requires_label_edit'] = 'false'
                row['scene_decision'] = 'labels_valid_model_gap'
                row['reviewer_notes'] = 'reviewed'
            _write_decisions(worksheet, rows)

            with self.assertRaisesRegex(ValueError, 'component_decision must be one of'):
                resolve_manual_label_review(
                    manual_label_review_decisions=worksheet,
                    manual_label_review_packet=root / 'out' / 'manual_label_review_packet.json',
                    output_root=root / 'out',
                )

    def test_label_remediation_decisions_create_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _build_packet(root)
            worksheet = root / 'out' / 'manual_label_review_decisions.csv'
            rows = _read_decisions(worksheet)
            for index, row in enumerate(rows):
                row['review_status'] = 'reviewed'
                row['component_decision'] = 'truth_missing_or_underlabeled' if index == 0 else 'prediction_false_alarm'
                row['requires_label_edit'] = 'true' if index == 0 else 'false'
                row['scene_decision'] = 'label_remediation_required' if index == 0 else 'labels_valid_model_gap'
                row['reviewer_notes'] = 'reviewed with source-label evidence'
            _write_decisions(worksheet, rows)

            outcome = resolve_manual_label_review(
                manual_label_review_decisions=worksheet,
                manual_label_review_packet=root / 'out' / 'manual_label_review_packet.json',
                output_root=root / 'out',
            )

            self.assertEqual(outcome['decision'], 'label_remediation_required')
            self.assertEqual(outcome['label_remediation_component_count'], 1)
            self.assertFalse(outcome['next_gpu_run_authorized'])
            self.assertTrue((root / 'out' / 'snowslide_label_remediation_manifest.csv').exists())

    def test_labels_valid_model_gap_can_warrant_design_but_not_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _build_packet(root)
            worksheet = root / 'out' / 'manual_label_review_decisions.csv'
            rows = _read_decisions(worksheet)
            for row in rows:
                row['review_status'] = 'reviewed'
                row['component_decision'] = 'valid_model_miss' if row['component_type'] == 'false_negative' else 'prediction_false_alarm'
                row['requires_label_edit'] = 'false'
                row['scene_decision'] = 'labels_valid_model_gap'
                row['reviewer_notes'] = 'label reviewed and accepted as model-side evidence'
            _write_decisions(worksheet, rows)

            outcome = resolve_manual_label_review(
                manual_label_review_decisions=worksheet,
                manual_label_review_packet=root / 'out' / 'manual_label_review_packet.json',
                output_root=root / 'out',
            )

            self.assertEqual(outcome['decision'], 'labels_valid_model_gap')
            self.assertTrue(outcome['future_candidate_design_warranted'])
            self.assertFalse(outcome['next_gpu_run_authorized'])
            self.assertFalse(outcome['promotion_allowed'])


if __name__ == '__main__':
    unittest.main()
