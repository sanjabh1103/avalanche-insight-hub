from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_phase0_7_cross_verification_report import (
    build_phase0_7_cross_verification_report,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _write_text(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding='utf-8')
    return path


def _inputs(root: Path, *, snow_decision: str = 'blocked_research_grade', fresh_status: str = 'blocked_pending_snowslide_research_grade', production_allowed: bool = False) -> dict[str, Path]:
    return {
        'phase2_audit_path': _write_json(root / 'phase2.json', {
            'version': 'non_gpu_feasibility_audit_v1',
            'decision': 'blocked_research_grade_candidate_needed',
            'production_scoring_allowed': False,
            'non_gpu_pass_found': False,
            'bounded_candidate_warranted': True,
        }),
        'candidate_design_path': _write_json(root / 'design.json', {
            'version': 'candidate_design_report_v1',
            'decision': 'bounded_candidate_design_recommended',
            'production_scoring_allowed': False,
            'promotion_allowed': False,
        }),
        'candidate_authorization_path': _write_json(root / 'authorization.json', {
            'version': 'candidate_authorization_request_v1',
            'status': 'authorized_for_single_bounded_gpu_run',
            'gpu_run_authorized': True,
            'production_scoring_allowed': False,
            'promotion_allowed': False,
        }),
        'avalcd_benchmark_path': _write_json(root / 'avalcd.json', {
            'version': 'european_shadow_benchmark_report_v1',
            'production_scoring_allowed': False,
            'promotion_gate_report': {'decision': 'blocked_shadow_only'},
            'source_reports': [{
                'source_key': 'avalcd_zenodo_v1',
                'sar_prediction_metrics': {
                    'evaluation_mode': 'scene_blended',
                    'quality_gate': {'passed': True, 'precision_floor_met': True, 'recall_floor_met': True},
                    'metrics': {
                        'threshold': 0.9980000257492065,
                        'precision': 0.649,
                        'recall': 0.535,
                        'f1': 0.586,
                        'false_positive_rate': 0.00114,
                    },
                },
            }],
        }),
        'snowslide_acceptance_path': _write_json(root / 'snow.json', {
            'version': 'snowslide_acceptance_report_v1',
            'decision': snow_decision,
            'accepted_research_grade': snow_decision == 'accepted_research_grade',
            'production_scoring_allowed': production_allowed,
            'metrics': {
                'precision': 0.0 if snow_decision == 'blocked_research_grade' else 0.72,
                'recall': 0.0 if snow_decision == 'blocked_research_grade' else 0.55,
                'f1': 0.0 if snow_decision == 'blocked_research_grade' else 0.62,
                'false_positive_rate': 0.0,
                'beats_baseline': snow_decision != 'blocked_research_grade',
            },
        }),
        'snowslide_diagnostics_path': _write_json(root / 'diagnostics.json', {
            'version': 'snowslide_sar_error_diagnostics_v1',
            'decision': 'blocked_shadow_only',
            'production_scoring_allowed': False,
            'aggregate_metrics': {
                'tp': 0 if snow_decision == 'blocked_research_grade' else 20,
                'fp': 0 if snow_decision == 'blocked_research_grade' else 3,
                'fn': 254404 if snow_decision == 'blocked_research_grade' else 10,
                'precision': 0.0 if snow_decision == 'blocked_research_grade' else 0.72,
                'recall': 0.0 if snow_decision == 'blocked_research_grade' else 0.55,
                'f1': 0.0 if snow_decision == 'blocked_research_grade' else 0.62,
                'false_positive_rate': 0.0,
            },
        }),
        'fresh_final_plan_path': _write_json(root / 'fresh.json', {
            'version': 'fresh_final_holdout_plan_v1',
            'status': fresh_status,
            'fresh_final_reference_set_key': 'fresh-final-v1' if fresh_status == 'ready_for_fresh_final_holdout_evaluation' else None,
            'production_scoring_allowed': False,
            'promotion_allowed': False,
            'phase7_promotion_ready': False,
        }),
    }


def _build(root: Path, **kwargs) -> dict:
    inputs = _inputs(root, **kwargs)
    return build_phase0_7_cross_verification_report(
        **inputs,
        output_root=root / 'out',
        cwd=root,
        git_status_text='## feature/european-data-shadow-pipeline...origin/feature/european-data-shadow-pipeline [ahead 4]',
        modal_container_list_file=_write_text(
            root / 'modal.txt',
            'Active Containers in environment: None\n',
        ),
    )


class Phase07CrossVerificationReportTests(unittest.TestCase):
    def test_current_phase5_failure_blocks_phase7_and_summarizes_transfer_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _build(Path(tmpdir))

        self.assertEqual(report['decision'], 'blocked_phase7_not_ready')
        self.assertFalse(report['phase7_ready'])
        self.assertFalse(report['production_scoring_allowed'])
        self.assertFalse(report['next_gpu_run_authorized'])
        self.assertEqual(report['v6_transfer_failure_addendum']['failure_mode'], 'cross_domain_calibration_generalization_failure')
        self.assertFalse(report['v6_transfer_failure_addendum']['snowslide_produced_positive_predictions'])

    def test_production_scoring_true_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _build(Path(tmpdir), snow_decision='accepted_research_grade', fresh_status='ready_for_fresh_final_holdout_evaluation', production_allowed=True)

        self.assertEqual(report['decision'], 'blocked_production_guard_violation')
        self.assertFalse(report['phase7_ready'])
        gates = [item['gate'] for item in report['phase7_readiness']['blockers']]
        self.assertIn('production_scoring_guard', gates)

    def test_accepted_snowslide_without_fresh_final_blocks_pending_fresh_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _build(Path(tmpdir), snow_decision='accepted_research_grade', fresh_status='blocked_pending_fresh_reference_set')

        self.assertEqual(report['decision'], 'blocked_pending_fresh_final')
        self.assertFalse(report['phase7_ready'])

    def test_accepted_snowslide_with_independent_final_set_is_review_ready_not_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _build(Path(tmpdir), snow_decision='accepted_research_grade', fresh_status='ready_for_fresh_final_holdout_evaluation')

        self.assertEqual(report['decision'], 'ready_for_phase7_review')
        self.assertTrue(report['phase7_ready'])
        self.assertFalse(report['promotion_allowed'])
        self.assertFalse(report['production_scoring_allowed'])

    def test_active_modal_container_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _inputs(root, snow_decision='accepted_research_grade', fresh_status='ready_for_fresh_final_holdout_evaluation')
            report = build_phase0_7_cross_verification_report(
                **inputs,
                output_root=root / 'out',
                cwd=root,
                git_status_text='## feature',
                modal_container_list_file=_write_text(root / 'modal.txt', '│ avalanche-modal-worker │ running │\n'),
            )

        self.assertEqual(report['decision'], 'blocked_modal_active')
        self.assertFalse(report['phase7_ready'])

    def test_missing_required_artifact_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _inputs(root)
            inputs['snowslide_acceptance_path'] = root / 'missing.json'

            with self.assertRaises(FileNotFoundError):
                build_phase0_7_cross_verification_report(
                    **inputs,
                    output_root=root / 'out',
                    cwd=root,
                    git_status_text='## feature',
                    modal_container_list_file=_write_text(root / 'modal.txt', 'Active Containers in environment: None\n'),
                )


if __name__ == '__main__':
    unittest.main()
