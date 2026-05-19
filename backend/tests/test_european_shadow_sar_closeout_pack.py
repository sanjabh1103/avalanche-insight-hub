from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_european_shadow_sar_closeout_pack import (
    build_closeout_pack,
    validate_v2_closeout_pack,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _avalcd_report(*, production_allowed: bool = False, passed: bool = True) -> dict:
    return {
        'version': 'european_shadow_benchmark_report_v1',
        'production_scoring_allowed': production_allowed,
        'source_reports': [{
            'source_key': 'avalcd_zenodo_v1',
            'sar_prediction_metrics': {
                'evaluation_mode': 'scene_blended',
                'quality_gate': {
                    'passed': passed,
                    'precision_floor_met': passed,
                    'recall_floor_met': passed,
                },
                'metrics': {
                    'precision': 0.6093,
                    'recall': 0.5942,
                    'f1': 0.6016,
                    'false_positive_rate': 0.0015,
                    'threshold': 0.998,
                    'postprocess_min_component_area_px': 32,
                    'postprocess_opening_size_px': 0,
                },
            },
        }],
    }


def _snowslide_acceptance(*, decision: str = 'blocked_research_grade') -> dict:
    return {
        'version': 'snowslide_acceptance_report_v1',
        'decision': decision,
        'accepted_research_grade': decision == 'accepted_research_grade',
        'production_scoring_allowed': False,
        'metrics': {
            'precision': 0.6137,
            'recall': 0.5584,
            'f1': 0.5847,
            'false_positive_rate': 0.00184,
            'beats_baseline': True,
        },
        'blockers': [
            {'gate': 'precision_floor', 'actual': 0.6137, 'required': 0.70},
            {'gate': 'f1_floor', 'actual': 0.5847, 'required': 0.60},
        ] if decision == 'blocked_research_grade' else [],
    }


def _sweep() -> dict:
    return {
        'version': 'snowslide_threshold_sweep_v1',
        'decision': 'blocked_research_grade',
        'passing_candidate_count': 0,
        'bounded_candidate_warranted': True,
    }


def _manual_packet(*, decision: str = 'manual_scene_label_review_required') -> dict:
    return {
        'version': 'snowslide_manual_label_review_packet_v1',
        'decision': decision,
        'recommended_next_step': 'complete_manual_label_review_decisions',
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'next_gpu_run_authorized': False,
        'component_review_items': [{'action_id': f'a-{index}'} for index in range(30)],
    }


def _diagnostics() -> dict:
    return {
        'version': 'snowslide_sar_error_diagnostics_v1',
        'production_scoring_allowed': False,
        'per_scene': [
            {
                'scene_id': 'tromso_20241220',
                'precision': 0.848,
                'recall': 0.686,
                'f1': 0.758,
                'false_positive_rate': 0.0017,
            },
            {
                'scene_id': 'pish_20230221',
                'precision': 0.393,
                'recall': 0.569,
                'f1': 0.465,
                'false_positive_rate': 0.0056,
            },
        ],
    }


def _inputs(root: Path, *, production_allowed: bool = False, snow_decision: str = 'blocked_research_grade', avalcd_passed: bool = True) -> dict[str, Path]:
    return {
        'avalcd_benchmark_path': _write_json(root / 'avalcd.json', _avalcd_report(
            production_allowed=production_allowed,
            passed=avalcd_passed,
        )),
        'snowslide_acceptance_path': _write_json(root / 'snow.json', _snowslide_acceptance(
            decision=snow_decision,
        )),
        'snowslide_sweep_path': _write_json(root / 'sweep.json', _sweep()),
        'manual_review_packet_path': _write_json(root / 'manual.json', _manual_packet()),
        'snowslide_diagnostics_path': _write_json(root / 'diagnostics.json', _diagnostics()),
        'output_root': root / 'out',
    }


def _authorized_kwargs() -> dict:
    return {
        'allow_shadow_only_presentation': True,
        'authorized_by': 'Dr Review Lead',
        'authorization_reason': 'Shadow-only client briefing with no SAR production claim',
        'authorization_evidence_ref': 'internal-review-note-2026-05-19',
        'manual_review_owner': 'Dr SAR Reviewer',
        'manual_review_target_date': '2026-05-26',
    }


class EuropeanShadowSarCloseoutPackTests(unittest.TestCase):
    def test_default_v8_blocked_status_is_not_client_presentation_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_closeout_pack(**_inputs(Path(tmpdir)))

        self.assertEqual(report['decision'], 'blocked_sar_production_pending_manual_review')
        self.assertFalse(report['client_presentation_ready'])
        self.assertFalse(report['sar_production_ready'])
        self.assertFalse(report['production_scoring_allowed'])
        self.assertFalse(report['phase7_ready'])
        self.assertFalse(report['next_gpu_run_authorized'])
        self.assertEqual(report['manual_review']['component_review_item_count'], 30)
        gates = [blocker['gate'] for blocker in report['blockers']]
        self.assertIn('snowslide_research_grade', gates)
        self.assertIn('manual_component_review', gates)
        presentation_gates = [blocker['gate'] for blocker in report['presentation_blockers']]
        self.assertIn('shadow_only_presentation_authorization', presentation_gates)
        self.assertIn('manual_review_owner', presentation_gates)

    def test_explicit_shadow_only_authorization_allows_client_presentation_not_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_closeout_pack(**_inputs(Path(tmpdir)), **_authorized_kwargs())

        self.assertEqual(report['version'], 'european_shadow_sar_closeout_pack_v2')
        self.assertTrue(report['client_presentation_ready'])
        self.assertFalse(report['sar_production_ready'])
        self.assertFalse(report['promotion_allowed'])
        self.assertTrue(report['presentation_authorization']['authorized'])
        self.assertIsNotNone(report['presentation_authorization']['presentation_authorization_id'])
        self.assertEqual(report['manual_review']['owner_status'], 'assigned')
        self.assertEqual(report['per_scene_snowslide_results'][0]['scene_id'], 'tromso_20241220')

    def test_tbd_authorization_fields_do_not_count_as_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_closeout_pack(
                **_inputs(Path(tmpdir)),
                allow_shadow_only_presentation=True,
                authorized_by='TBD before presentation',
                authorization_reason='Shadow-only client briefing',
                manual_review_owner='TBD',
                manual_review_target_date='TBD',
            )

        self.assertFalse(report['client_presentation_ready'])
        self.assertFalse(report['presentation_authorization']['authorized'])
        self.assertEqual(report['manual_review']['owner_status'], 'unassigned')

    def test_production_scoring_true_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_closeout_pack(**_inputs(Path(tmpdir), production_allowed=True))

        self.assertEqual(report['decision'], 'blocked_production_guard_violation')
        self.assertFalse(report['sar_production_ready'])
        gates = [blocker['gate'] for blocker in report['blockers']]
        self.assertIn('production_scoring_guard', gates)

    def test_missing_required_input_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _inputs(root)
            inputs['snowslide_acceptance_path'] = root / 'missing.json'

            with self.assertRaises(FileNotFoundError):
                build_closeout_pack(**inputs)

    def test_output_json_and_markdown_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = build_closeout_pack(**_inputs(root))

            self.assertEqual(report['version'], 'european_shadow_sar_closeout_pack_v2')
            self.assertTrue((root / 'out' / 'european_shadow_sar_closeout_pack.json').exists())
            self.assertTrue((root / 'out' / 'european_shadow_sar_closeout_pack.md').exists())

    def test_v1_schema_is_deprecated_and_rejected_by_v2_validator(self) -> None:
        with self.assertRaisesRegex(ValueError, 'deprecated'):
            validate_v2_closeout_pack({'version': 'european_shadow_sar_closeout_pack_v1'})

    def test_existing_v1_outputs_are_renamed_before_v2_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out = root / 'out'
            _write_json(out / 'european_shadow_sar_closeout_pack.json', {
                'version': 'european_shadow_sar_closeout_pack_v1',
            })
            (out / 'european_shadow_sar_closeout_pack.md').write_text('old', encoding='utf-8')

            build_closeout_pack(**_inputs(root))

            self.assertTrue((out / 'european_shadow_sar_closeout_pack.deprecated_v1.json').exists())
            self.assertTrue((out / 'european_shadow_sar_closeout_pack.deprecated_v1.md').exists())
            payload = json.loads((out / 'european_shadow_sar_closeout_pack.json').read_text(encoding='utf-8'))
            validate_v2_closeout_pack(payload)


if __name__ == '__main__':
    unittest.main()
