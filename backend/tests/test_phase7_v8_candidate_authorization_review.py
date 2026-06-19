from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_phase7_v8_candidate_authorization_review import (
    build_phase7_v8_candidate_authorization_review,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _inputs(root: Path, *, passing_candidate_count: int = 0) -> dict[str, Path]:
    return {
        'phase7_report_path': _write_json(root / 'phase7.json', {
            'decision': 'one_bounded_v8_candidate_warranted',
            'production_scoring_allowed': False,
            'next_gpu_run_authorized': False,
        }),
        'candidate_design_path': _write_json(root / 'design.json', {
            'decision': 'bounded_v8_candidate_design_recommended',
            'candidate_model_version': 'avalcd_swinunet_tiny_diff_calibrated_transfer_shadow_20260518_v8_design_only',
            'initial_checkpoint_path': '/artifacts/20260518T124829Z/sar_model.pt',
            'production_scoring_allowed': False,
            'proposed_training_request_overrides': {
                'epochs': 4,
                'patience': 2,
                'batch_size': 8,
                'learning_rate': 0.000005,
                'loss': 'focal_tversky',
                'negative_ratio': 6,
                'focal_tversky_alpha': 0.35,
                'focal_tversky_beta': 0.65,
                'focal_tversky_gamma': 1.33,
                'f_beta': 0.75,
                'threshold_grid': [0.90, 0.95, 0.97, 0.98, 0.985, 0.99, 0.995, 0.998],
                'postprocess_min_component_area_px': 128,
                'postprocess_opening_size_px': 0,
                'materialized_dataset_root': '/tmp/avalcd-shadow-train5-val2-v8',
            },
        }),
        'acceptance_report_path': _write_json(root / 'acceptance.json', {
            'decision': 'blocked_research_grade',
            'accepted_research_grade': False,
            'production_scoring_allowed': False,
            'metrics': {
                'precision': 0.6609,
                'recall': 0.5097,
                'f1': 0.5755,
                'false_positive_rate': 0.00137,
            },
        }),
        'sweep_report_path': _write_json(root / 'sweep.json', {
            'decision': 'blocked_research_grade',
            'passing_candidate_count': passing_candidate_count,
            'candidates': [{
                'threshold': 0.985,
                'postprocess_min_component_area_px': 128,
                'postprocess_opening_size_px': 0,
                'metrics': {
                    'precision': 0.6443,
                    'recall': 0.5450,
                    'f1': 0.5905,
                    'false_positive_rate': 0.00158,
                },
            }],
        }),
        'integrity_audit_path': _write_json(root / 'integrity.json', {
            'decision': 'integrity_passed_recovery_needed',
            'failure_classification': 'metrics_failure_after_valid_materialization',
            'quantized_threshold_mismatch': False,
            'selected_threshold_positive_pixels': 279181,
            'production_scoring_allowed': False,
            'next_gpu_run_authorized': False,
        }),
        'template_training_request_path': _write_json(root / 'template.json', {
            'training_manifest_path': '/artifacts/european-shadow-sar/avalcd-shadow-v1/manifests/avalcd_shadow_train5_val2.json',
            'source_key': 'avalcd_zenodo_v1',
            'license_review_id': 'license-review-avalcd-zenodo-cc-by-nc-2026-05-16',
            'model_family': 'swinunet_tiny_diff',
            'patch_size': 128,
            'stride': 64,
            'batch_size': 8,
            'loss': 'focal_tversky',
            'train_scene_ids': ['livigno_20240403'],
            'validation_scene_ids': ['livigno_20250318'],
        }),
    }


def _build(root: Path, **kwargs) -> dict:
    return build_phase7_v8_candidate_authorization_review(
        **_inputs(root, passing_candidate_count=kwargs.pop('passing_candidate_count', 0)),
        output_root=root / 'out',
        **kwargs,
    )


class Phase7V8CandidateAuthorizationReviewTests(unittest.TestCase):
    def test_default_review_waits_for_explicit_gpu_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root)

            self.assertEqual(report['status'], 'awaiting_explicit_operator_approval')
            self.assertFalse(report['gpu_run_authorized'])
            self.assertIsNone(report['train_request_path'])
            self.assertTrue((root / 'out' / 'candidate_authorization_review.json').exists())
            self.assertFalse((root / 'out' / 'train_sar_unet_request.json').exists())
            self.assertFalse(report['production_scoring_allowed'])

    def test_authorized_review_writes_single_bounded_training_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root, authorize_gpu=True)
            request = json.loads((root / 'out' / 'train_sar_unet_request.json').read_text(encoding='utf-8'))

        self.assertEqual(report['status'], 'authorized_for_single_bounded_gpu_run')
        self.assertTrue(report['gpu_run_authorized'])
        self.assertEqual(report['max_gpu_runs'], 1)
        self.assertEqual(request['candidate_model_version'], 'avalcd_swinunet_tiny_diff_calibrated_transfer_shadow_20260518_v8')
        self.assertEqual(request['initial_checkpoint_path'], '/artifacts/20260518T124829Z/sar_model.pt')
        self.assertEqual(request['epochs'], 4)
        self.assertEqual(request['patience'], 2)
        self.assertEqual(request['batch_size'], 8)
        self.assertEqual(request['learning_rate'], 0.000005)
        self.assertEqual(request['negative_ratio'], 6)
        self.assertEqual(request['threshold_grid'], [0.90, 0.95, 0.97, 0.98, 0.985, 0.99, 0.995, 0.998])
        self.assertEqual(request['postprocess_min_component_area_px'], 128)
        self.assertEqual(request['materialized_dataset_root'], '/tmp/avalcd-shadow-train5-val2-v8')
        self.assertFalse(request['production_scoring_allowed'])

    def test_passing_non_gpu_candidate_blocks_gpu_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = _build(root, authorize_gpu=True, passing_candidate_count=1)

        self.assertEqual(report['status'], 'blocked_non_gpu_candidate_available')
        self.assertFalse(report['gpu_run_authorized'])
        self.assertIsNone(report['train_request_path'])

    def test_failed_integrity_blocks_gpu_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _inputs(root)
            integrity = json.loads(inputs['integrity_audit_path'].read_text(encoding='utf-8'))
            integrity['decision'] = 'blocked_quantized_threshold_mismatch'
            integrity['quantized_threshold_mismatch'] = True
            inputs['integrity_audit_path'].write_text(json.dumps(integrity), encoding='utf-8')

            report = build_phase7_v8_candidate_authorization_review(
                **inputs,
                output_root=root / 'out',
                authorize_gpu=True,
            )

        self.assertEqual(report['status'], 'blocked_float32_integrity_not_passed')
        self.assertFalse(report['gpu_run_authorized'])

    def test_production_scoring_flag_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _inputs(root)
            acceptance = json.loads(inputs['acceptance_report_path'].read_text(encoding='utf-8'))
            acceptance['production_scoring_allowed'] = True
            inputs['acceptance_report_path'].write_text(json.dumps(acceptance), encoding='utf-8')

            report = build_phase7_v8_candidate_authorization_review(
                **inputs,
                output_root=root / 'out',
                authorize_gpu=True,
            )

        self.assertEqual(report['status'], 'blocked_production_scoring_flag')
        self.assertFalse(report['gpu_run_authorized'])


if __name__ == '__main__':
    unittest.main()
