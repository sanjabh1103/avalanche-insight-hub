from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_snowslide_candidate_design_report import build_candidate_design_report


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _base_inputs(root: Path, *, manual_decision: str = 'labels_valid_model_gap', eval_passing_count: int = 0) -> dict[str, Path]:
    return {
        'manual_label_review_outcome': _write_json(root / 'manual.json', {
            'decision': manual_decision,
            'future_candidate_design_warranted': manual_decision == 'labels_valid_model_gap',
            'component_decision_counts': {
                'valid_model_miss': 15,
                'prediction_false_alarm': 15,
            },
        }),
        'next_candidate_decision': _write_json(root / 'next.json', {
            'recommendation': 'targeted_scene_label_data_review_no_training',
        }),
        'acceptance_report': _write_json(root / 'acceptance.json', {
            'decision': 'blocked_research_grade',
            'metrics': {
                'precision': 0.5988,
                'recall': 0.4929,
                'f1': 0.5407,
                'false_positive_rate': 0.001733,
                'beats_baseline': True,
            },
            'blockers': [
                {'gate': 'precision_floor'},
                {'gate': 'recall_floor'},
                {'gate': 'f1_floor'},
            ],
        }),
        'eval_only_recovery_report': _write_json(root / 'eval.json', {
            'decision': 'blocked_research_grade',
            'passing_candidate_count': eval_passing_count,
        }),
        'avalcd_benchmark_report': _write_json(root / 'avalcd.json', {
            'source_reports': [
                {
                    'source_key': 'avalcd_zenodo_v1',
                    'sar_prediction_metrics': {
                        'evaluation_mode': 'scene_blended',
                        'quality_gate': {
                            'passed': True,
                            'precision_floor_met': True,
                            'recall_floor_met': True,
                        },
                        'metrics': {
                            'precision': 0.6087,
                            'recall': 0.5288,
                            'f1': 0.5659,
                            'false_positive_rate': 0.00134,
                            'threshold': 0.996,
                            'postprocess_min_component_area_px': 0,
                        },
                    },
                },
            ],
        }),
    }


def _build(root: Path, **kwargs) -> dict:
    inputs = _base_inputs(root, **kwargs)
    return build_candidate_design_report(
        manual_label_review_outcome=inputs['manual_label_review_outcome'],
        next_candidate_decision=inputs['next_candidate_decision'],
        acceptance_report=inputs['acceptance_report'],
        eval_only_recovery_report=inputs['eval_only_recovery_report'],
        avalcd_benchmark_report=inputs['avalcd_benchmark_report'],
        output_root=root / 'out',
    )


class SnowSlideCandidateDesignReportTests(unittest.TestCase):
    def test_model_gap_recommends_bounded_design_without_authorizing_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root)

            self.assertEqual(report['version'], 'candidate_design_report_v1')
            self.assertEqual(report['decision'], 'bounded_candidate_design_recommended')
            self.assertFalse(report['gpu_run_authorized'])
            self.assertFalse(report['production_scoring_allowed'])
            self.assertFalse(report['promotion_allowed'])
            self.assertIsNotNone(report['candidate_design'])
            self.assertFalse(report['candidate_design']['gpu_run_authorized'])
            self.assertTrue((root / 'out' / 'candidate_design_report.json').exists())
            self.assertTrue((root / 'out' / 'candidate_design_report.md').exists())

    def test_incomplete_manual_review_blocks_candidate_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root, manual_decision='review_incomplete')

            self.assertEqual(report['decision'], 'blocked_pending_manual_review')
            self.assertIsNone(report['candidate_design'])
            self.assertFalse(report['gpu_run_authorized'])

    def test_eval_only_passing_candidate_wins_before_training_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root, eval_passing_count=1)

            self.assertEqual(report['decision'], 'eval_only_change_recommended')
            self.assertIsNone(report['candidate_design'])
            self.assertFalse(report['gpu_run_authorized'])


if __name__ == '__main__':
    unittest.main()
