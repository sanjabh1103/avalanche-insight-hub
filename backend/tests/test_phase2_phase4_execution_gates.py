from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_avalcd_first_gate_plan import build_avalcd_first_gate_plan
from backend.scripts.build_sar_candidate_authorization_request import build_candidate_authorization_request
from backend.scripts.build_snowslide_non_gpu_feasibility_audit import build_non_gpu_feasibility_audit


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _phase2_inputs(root: Path, *, passing_count: int = 0) -> dict[str, Path]:
    return {
        'acceptance_report': _write_json(root / 'acceptance.json', {
            'decision': 'blocked_research_grade',
            'metrics': {'precision': 0.59, 'recall': 0.49, 'f1': 0.54},
        }),
        'eval_only_recovery_report': _write_json(root / 'eval.json', {
            'decision': 'requires_fresh_final_holdout' if passing_count else 'blocked_research_grade',
            'passing_candidate_count': passing_count,
            'selected_candidate': {
                'threshold': 0.996,
                'postprocess_min_component_area_px': 64,
                'postprocess_opening_size_px': 0,
                'metrics': {
                    'precision': 0.73,
                    'recall': 0.42 if not passing_count else 0.51,
                    'f1': 0.54 if not passing_count else 0.61,
                    'false_positive_rate': 0.0017,
                },
            },
        }),
        'manual_label_review_outcome': _write_json(root / 'manual.json', {
            'decision': 'labels_valid_model_gap',
            'future_candidate_design_warranted': True,
        }),
        'candidate_design_report': _write_json(root / 'design.json', {
            'decision': 'bounded_candidate_design_recommended',
            'gpu_run_authorized': False,
        }),
    }


def _training_template(root: Path) -> Path:
    return _write_json(root / 'train_template.json', {
        'training_manifest_path': '/artifacts/european-shadow-sar/avalcd-shadow-v1/manifests/avalcd_shadow_train5_val2.json',
        'source_key': 'avalcd_zenodo_v1',
        'license_review_id': 'license-review-test',
        'model_family': 'swinunet_tiny_diff',
        'patch_size': 128,
        'stride': 64,
        'batch_size': 8,
    })


class Phase2Phase4ExecutionGateTests(unittest.TestCase):
    def test_phase2_audit_recommends_candidate_without_authorizing_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _phase2_inputs(root)
            report = build_non_gpu_feasibility_audit(output_root=root / 'out', **inputs)

        self.assertEqual(report['version'], 'non_gpu_feasibility_audit_v1')
        self.assertEqual(report['decision'], 'blocked_research_grade_candidate_needed')
        self.assertFalse(report['non_gpu_pass_found'])
        self.assertTrue(report['bounded_candidate_warranted'])
        self.assertFalse(report['gpu_run_authorized'])
        self.assertFalse(report['production_scoring_allowed'])

    def test_phase2_audit_stops_gpu_when_non_gpu_pass_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _phase2_inputs(root, passing_count=1)
            report = build_non_gpu_feasibility_audit(output_root=root / 'out', **inputs)

        self.assertEqual(report['decision'], 'non_gpu_pass_found')
        self.assertTrue(report['avalcd_recheck_required'])
        self.assertFalse(report['gpu_run_authorized'])

    def test_phase3_authorization_writes_v6_request_only_when_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _phase2_inputs(root)
            audit = build_non_gpu_feasibility_audit(output_root=root / 'phase2', **inputs)
            audit_path = _write_json(root / 'phase2.json', audit)
            report = build_candidate_authorization_request(
                non_gpu_feasibility_audit=audit_path,
                candidate_design_report=inputs['candidate_design_report'],
                template_training_request=_training_template(root),
                output_root=root / 'phase3',
                authorize_gpu=True,
            )

            request = json.loads((root / 'phase3' / 'train_sar_unet_request.json').read_text(encoding='utf-8'))

        self.assertEqual(report['status'], 'authorized_for_single_bounded_gpu_run')
        self.assertTrue(report['gpu_run_authorized'])
        self.assertEqual(request['candidate_model_version'], 'avalcd_swinunet_tiny_diff_research_gate_shadow_20260518_v6')
        self.assertEqual(request['materialized_dataset_root'], '/tmp/avalcd-shadow-train5-val2-v6')

    def test_phase3_blocks_when_non_gpu_candidate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _phase2_inputs(root, passing_count=1)
            audit = build_non_gpu_feasibility_audit(output_root=root / 'phase2', **inputs)
            audit_path = _write_json(root / 'phase2.json', audit)
            report = build_candidate_authorization_request(
                non_gpu_feasibility_audit=audit_path,
                candidate_design_report=inputs['candidate_design_report'],
                template_training_request=_training_template(root),
                output_root=root / 'phase3',
                authorize_gpu=True,
            )

        self.assertEqual(report['status'], 'blocked_non_gpu_candidate_available')
        self.assertFalse(report['gpu_run_authorized'])
        self.assertIsNone(report['train_request_path'])

    def test_phase4_reports_pending_until_candidate_checkpoint_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            auth = _write_json(root / 'auth.json', {
                'candidate_model_version': 'candidate-v6',
                'gpu_run_authorized': True,
            })
            template = _training_template(root)
            report = build_avalcd_first_gate_plan(
                candidate_authorization_request=auth,
                template_training_request=template,
                output_root=root / 'gate',
            )

        self.assertEqual(report['status'], 'blocked_pending_candidate_artifact')
        self.assertFalse(report['avalcd_first_gate_passed'])
        self.assertFalse(report['snow_slide_materialization_allowed'])
        self.assertFalse(report['production_scoring_allowed'])

    def test_phase4_builds_scene_blended_request_from_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            auth = _write_json(root / 'auth.json', {'candidate_model_version': 'candidate-v6'})
            template = _training_template(root)
            training = _write_json(root / 'training_result.json', {
                'status': 'ok',
                'candidate_model_version': 'candidate-v6',
                'model_checkpoint_path': '/artifacts/20260518T120000Z/sar_model.pt',
            })
            report = build_avalcd_first_gate_plan(
                candidate_authorization_request=auth,
                template_training_request=template,
                training_result=training,
                output_root=root / 'gate',
            )
            request = json.loads((root / 'gate' / 'evaluate_sar_checkpoint_request.json').read_text(encoding='utf-8'))

        self.assertEqual(report['status'], 'ready_for_scene_blended_evaluation')
        self.assertEqual(request['evaluation_mode'], 'scene_blended')
        self.assertEqual(request['checkpoint_path'], '/artifacts/20260518T120000Z/sar_model.pt')

    def test_phase4_passes_only_scene_blended_floor_met_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            auth = _write_json(root / 'auth.json', {'candidate_model_version': 'candidate-v6'})
            template = _training_template(root)
            training = _write_json(root / 'training_result.json', {
                'model_checkpoint_path': '/artifacts/20260518T120000Z/sar_model.pt',
            })
            evaluation = _write_json(root / 'evaluation.json', {
                'status': 'ok',
                'evaluation_mode': 'scene_blended',
                'metrics': {'precision': 0.61, 'recall': 0.51, 'f1': 0.56, 'false_positive_rate': 0.001},
                'quality_gate': {'passed': True},
            })
            report = build_avalcd_first_gate_plan(
                candidate_authorization_request=auth,
                template_training_request=template,
                training_result=training,
                evaluation_report=evaluation,
                output_root=root / 'gate',
            )

        self.assertEqual(report['status'], 'passed_avalcd_first_gate')
        self.assertTrue(report['avalcd_first_gate_passed'])
        self.assertTrue(report['snow_slide_materialization_allowed'])
        self.assertFalse(report['production_scoring_allowed'])


if __name__ == '__main__':
    unittest.main()
