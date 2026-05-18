from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.common.sar_acceptance_policy import SNOWSLIDE_EXPECTED_SCENE_IDS
from backend.scripts.build_snowslide_v6_integrity_audit import build_snowslide_v6_integrity_audit


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _write_mask(path: Path, values: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, values.astype(np.float32))
    return str(path)


def _materialization_result(root: Path, scene_id: str, prediction_ref: str) -> None:
    _write_json(root / scene_id / 'sar_segment_result.json', {
        'status': 'ok',
        'mask_asset_refs': [prediction_ref],
        'persisted_events': 0,
        'artifact_rows_persisted': 0,
    })


def _audit_inputs(root: Path, *, prediction_value: float = 0.2, threshold: float = 0.9980000257492065, bad_shape: bool = False, production_allowed: bool = False) -> dict[str, Path]:
    scenes = []
    materialization_root = root / 'materialization'
    for index, scene_id in enumerate(SNOWSLIDE_EXPECTED_SCENE_IDS):
        prediction = np.full((4, 4), prediction_value, dtype=np.float32)
        truth = np.zeros((5, 5), dtype=np.float32) if bad_shape and index == 0 else np.zeros((4, 4), dtype=np.float32)
        truth[:2, :2] = 1.0
        prediction_ref = _write_mask(root / 'masks' / scene_id / 'prediction.npy', prediction)
        truth_ref = _write_mask(root / 'masks' / scene_id / 'truth.npy', truth)
        _materialization_result(materialization_root, scene_id, prediction_ref)
        scenes.append({
            'scene_id': scene_id,
            'prediction_mask': prediction_ref,
            'truth_mask': truth_ref,
            'baseline_mask': truth_ref,
        })
    return {
        'request_path': _write_json(root / 'request.json', {
            'reference_set_key': 'snowslide-heldout-v1',
            'prediction_model_version': 'candidate-v6',
            'prediction_threshold': threshold,
            'truth_threshold': 0.5,
            'baseline_f1_floor': 0.1,
            'scenes': scenes,
        }),
        'acceptance_report_path': _write_json(root / 'acceptance.json', {
            'decision': 'blocked_research_grade',
            'production_scoring_allowed': production_allowed,
            'metrics': {'precision': 0.0, 'recall': 0.0, 'f1': 0.0},
        }),
        'materialization_result_dir': materialization_root,
    }


class SnowSlideV6IntegrityAuditTests(unittest.TestCase):
    def test_low_probability_predictions_classify_threshold_calibration_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = build_snowslide_v6_integrity_audit(
                **_audit_inputs(root, prediction_value=0.6),
                output_root=root / 'out',
                thresholds=[0.5, 0.9980000257492065],
            )

        self.assertEqual(report['decision'], 'blocked_threshold_calibration_failure')
        self.assertEqual(report['failure_classification'], 'high_threshold_calibration_failure')
        self.assertEqual(report['selected_threshold_positive_pixels'], 0)
        self.assertGreater(report['lowest_threshold_positive_pixels'], 0)
        self.assertFalse(report['production_scoring_allowed'])
        self.assertFalse(report['next_gpu_run_authorized'])

    def test_blank_prediction_masks_are_pipeline_integrity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = build_snowslide_v6_integrity_audit(
                **_audit_inputs(root, prediction_value=0.0),
                output_root=root / 'out',
                thresholds=[0.5, 0.9980000257492065],
            )

        self.assertEqual(report['decision'], 'blocked_pipeline_integrity_failure')
        gates = [finding['gate'] for finding in report['findings']]
        self.assertIn('blank_prediction_masks', gates)

    def test_shape_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = build_snowslide_v6_integrity_audit(
                **_audit_inputs(root, prediction_value=0.6, bad_shape=True),
                output_root=root / 'out',
                thresholds=[0.5, 0.9980000257492065],
            )

        self.assertEqual(report['decision'], 'blocked_pipeline_integrity_failure')
        self.assertIn('mask_shape_alignment', [finding['gate'] for finding in report['findings']])

    def test_missing_scene_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = _audit_inputs(root, prediction_value=0.6)
            request = json.loads(inputs['request_path'].read_text(encoding='utf-8'))
            request['scenes'] = request['scenes'][:-1]
            inputs['request_path'].write_text(json.dumps(request), encoding='utf-8')
            report = build_snowslide_v6_integrity_audit(
                **inputs,
                output_root=root / 'out',
                thresholds=[0.5, 0.9980000257492065],
            )

        self.assertEqual(report['decision'], 'blocked_pipeline_integrity_failure')
        self.assertIn('scene_coverage', [finding['gate'] for finding in report['findings']])


if __name__ == '__main__':
    unittest.main()
