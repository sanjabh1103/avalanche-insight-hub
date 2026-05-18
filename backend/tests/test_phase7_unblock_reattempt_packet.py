from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_phase7_unblock_reattempt_packet import (
    build_phase7_unblock_reattempt_packet,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _inputs(root: Path, *, passing_candidate_count: int = 0) -> dict[str, Path]:
    return {
        'v7_integrity_path': _write_json(root / 'integrity.json', {
            'decision': 'blocked_threshold_calibration_failure',
            'selected_threshold_positive_pixels': 0,
            'lowest_threshold_positive_pixels': 416668,
        }),
        'v7_sweep_path': _write_json(root / 'sweep.json', {
            'passing_candidate_count': passing_candidate_count,
            'selected_candidate': {
                'threshold': 0.98,
                'postprocess_min_component_area_px': 128,
                'postprocess_opening_size_px': 0,
                'metrics': {
                    'precision': 0.6332,
                    'recall': 0.5531,
                    'f1': 0.5904,
                    'false_positive_rate': 0.001681,
                },
                'policy': 'snowslide_research_grade_v1',
            },
        }),
        'v7_acceptance_path': _write_json(root / 'acceptance.json', {
            'decision': 'blocked_research_grade',
            'decision_rule': {
                'threshold': 0.9980000257492065,
                'postprocess_min_component_area_px': 96,
            },
        }),
        'v7_avalcd_benchmark_path': _write_json(root / 'avalcd.json', {
            'source_reports': [{
                'source_key': 'avalcd_zenodo_v1',
                'sar_prediction_metrics': {
                    'evaluation_mode': 'scene_blended',
                    'metrics': {
                        'precision': 0.6687,
                        'recall': 0.5678,
                        'f1': 0.6141,
                        'false_positive_rate': 0.001111,
                        'threshold': 0.9980000257492065,
                        'postprocess_min_component_area_px': 96,
                        'postprocess_opening_size_px': 0,
                    },
                },
            }],
        }),
        'v7_dry_run_path': _write_json(root / 'dry_run.json', {
            'precision': 0.0,
            'recall': 0.0,
            'f1': 0.0,
            'false_positive_rate': 0.0,
            'threshold': 0.9980000257492065,
            'postprocess_min_component_area_px': 96,
            'postprocess_opening_size_px': 0,
        }),
    }


def _build(root: Path, **kwargs) -> dict:
    return build_phase7_unblock_reattempt_packet(
        **_inputs(root, passing_candidate_count=kwargs.pop('passing_candidate_count', 0)),
        output_root=root / 'out',
        **kwargs,
    )


class Phase7UnblockReattemptPacketTests(unittest.TestCase):
    def test_no_reviewed_sota_checkpoint_builds_v8_design_without_gpu_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root)
            self.assertTrue((root / 'out' / 'claude_47_adversarial_review_prompt.md').exists())

        self.assertEqual(report['decision'], 'one_bounded_v8_candidate_warranted')
        self.assertEqual(report['sota_checkpoint_review']['status'], 'sota_checkpoint_unavailable')
        self.assertEqual(report['candidate_design_report_v8']['decision'], 'bounded_v8_candidate_design_recommended')
        self.assertFalse(report['next_gpu_run_authorized'])
        self.assertFalse(report['production_scoring_allowed'])
        self.assertFalse(report['promotion_allowed'])

    def test_reviewed_direct_sota_checkpoint_takes_priority_over_v8_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(
                root,
                sota_checkpoint_url='https://example.org/reviewed-checkpoints/avalcd-model.pt',
                sota_license_note='Reviewed research-only checkpoint license note.',
                sota_model_family='swinunet_tiny_diff',
                sota_source_label='reviewed_public_checkpoint',
            )

        self.assertEqual(report['decision'], 'sota_checkpoint_evaluation_first')
        self.assertEqual(report['sota_checkpoint_review']['status'], 'sota_checkpoint_candidate_ready')
        self.assertFalse(report['next_gpu_run_authorized'])
        self.assertFalse(report['production_scoring_allowed'])

    def test_invalid_sota_checkpoint_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(
                root,
                sota_checkpoint_url='http://example.org/model.pt',
                sota_license_note='',
                sota_model_family='sam_vit_h',
            )

        self.assertEqual(report['sota_checkpoint_review']['status'], 'blocked_invalid_sota_checkpoint_input')
        self.assertIn('checkpoint URL must be direct HTTPS', report['sota_checkpoint_review']['blockers'])
        self.assertIn('license note is required before checkpoint evaluation', report['sota_checkpoint_review']['blockers'])
        self.assertFalse(report['next_gpu_run_authorized'])

    def test_passing_non_gpu_candidate_blocks_new_gpu_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root, passing_candidate_count=1)

        self.assertEqual(report['decision'], 'calibration_bug_fix_first')
        self.assertEqual(report['candidate_design_report_v8']['decision'], 'no_gpu_candidate_design_until_evidence_improves')
        self.assertFalse(report['next_gpu_run_authorized'])


if __name__ == '__main__':
    unittest.main()
