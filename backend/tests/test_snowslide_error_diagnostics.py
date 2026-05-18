from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.scripts.build_snowslide_error_diagnostics import (
    build_diagnostics,
    classify_recommendation,
)


def _write_mask(path: Path, value: np.ndarray) -> str:
    np.save(path, np.asarray(value, dtype=np.float32))
    return str(path)


def _write_result(root: Path, scene_id: str) -> None:
    scene_dir = root / scene_id
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / 'sar_segment_result.json').write_text(
        json.dumps({
            'status': 'ok',
            'mask_asset_refs': [f'sar-masks/heldout/{scene_id}/prediction_mask.tif'],
            'persisted_events': 0,
            'artifact_rows_persisted': 0,
        }),
        encoding='utf-8',
    )


class SnowSlideErrorDiagnosticsTests(unittest.TestCase):
    def test_build_diagnostics_ranks_scene_fp_fn_and_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scenes = []
            materialization_dir = root / 'mat'
            fixture_rows = [
                (
                    'scene-fp-heavy',
                    np.array([[0.99, 0.99, 0.00], [0.99, 0.00, 0.00], [0.00, 0.00, 0.00]]),
                    np.zeros((3, 3)),
                ),
                (
                    'scene-fn-heavy',
                    np.zeros((3, 3)),
                    np.array([[1, 1, 0], [1, 0, 0], [0, 0, 0]]),
                ),
                (
                    'scene-mixed',
                    np.array([[0.99, 0.00], [0.99, 0.00]]),
                    np.array([[1, 1], [0, 0]]),
                ),
            ]
            for scene_id, prediction, truth in fixture_rows:
                scenes.append({
                    'scene_id': scene_id,
                    'region_key': 'test',
                    'prediction_mask': _write_mask(root / f'{scene_id}-prediction.npy', prediction),
                    'truth_mask': _write_mask(root / f'{scene_id}-truth.npy', truth),
                    'baseline_mask': _write_mask(root / f'{scene_id}-baseline.npy', np.zeros_like(truth)),
                })
                _write_result(materialization_dir, scene_id)

            request_path = root / 'request.json'
            acceptance_path = root / 'acceptance.json'
            output_root = root / 'out'
            request_path.write_text(
                json.dumps({
                    'dry_run': True,
                    'prediction_threshold': 0.5,
                    'postprocess_min_component_area_px': 0,
                    'postprocess_opening_size_px': 0,
                    'scenes': scenes,
                }),
                encoding='utf-8',
            )
            acceptance_path.write_text(
                json.dumps({
                    'decision': 'blocked_research_grade',
                    'production_scoring_allowed': False,
                    'metrics': {'precision': 0.5, 'recall': 0.5, 'f1': 0.5},
                }),
                encoding='utf-8',
            )

            report = build_diagnostics(
                request_path=request_path,
                acceptance_report_path=acceptance_path,
                materialization_result_dir=materialization_dir,
                output_root=output_root,
            )

            self.assertEqual(report['decision'], 'blocked_shadow_only')
            self.assertFalse(report['production_scoring_allowed'])
            self.assertEqual(report['scene_rankings']['false_positive_burden'][0]['scene_id'], 'scene-fp-heavy')
            self.assertEqual(report['scene_rankings']['false_negative_burden'][0]['scene_id'], 'scene-fn-heavy')
            fp_scene = next(row for row in report['per_scene'] if row['scene_id'] == 'scene-fp-heavy')
            fn_scene = next(row for row in report['per_scene'] if row['scene_id'] == 'scene-fn-heavy')
            self.assertEqual(fp_scene['top_false_positive_components'][0]['pixel_count'], 3)
            self.assertEqual(fn_scene['top_false_negative_components'][0]['pixel_count'], 3)
            self.assertTrue((output_root / 'sar_error_diagnostics.json').exists())
            self.assertTrue((output_root / 'sar_error_diagnostics.md').exists())
            self.assertTrue((output_root / 'next_candidate_decision.json').exists())

    def test_recommendation_prefers_threshold_postprocess_when_metrics_are_close(self) -> None:
        recommendation = classify_recommendation(
            aggregate_metrics={
                'precision': 0.61,
                'recall': 0.49,
                'f1': 0.55,
                'false_positive_rate': 0.001,
            },
            per_scene=[
                {'scene_id': 'a', 'fp_share': 0.25, 'fn_share': 0.25, 'fp': 25, 'fn': 25},
                {'scene_id': 'b', 'fp_share': 0.25, 'fn_share': 0.25, 'fp': 25, 'fn': 25},
                {'scene_id': 'c', 'fp_share': 0.25, 'fn_share': 0.25, 'fp': 25, 'fn': 25},
                {'scene_id': 'd', 'fp_share': 0.25, 'fn_share': 0.25, 'fp': 25, 'fn': 25},
            ],
        )

        self.assertEqual(recommendation['recommendation'], 'threshold_postprocess_only_retry')
        self.assertFalse(recommendation['future_gpu_training_allowed'])

    def test_recommendation_prefers_targeted_review_when_errors_are_concentrated(self) -> None:
        recommendation = classify_recommendation(
            aggregate_metrics={
                'precision': 0.40,
                'recall': 0.40,
                'f1': 0.40,
                'false_positive_rate': 0.001,
            },
            per_scene=[
                {'scene_id': 'a', 'fp_share': 0.50, 'fn_share': 0.10, 'fp': 50, 'fn': 10},
                {'scene_id': 'b', 'fp_share': 0.20, 'fn_share': 0.10, 'fp': 20, 'fn': 10},
                {'scene_id': 'c', 'fp_share': 0.30, 'fn_share': 0.80, 'fp': 30, 'fn': 80},
            ],
        )

        self.assertEqual(recommendation['recommendation'], 'targeted_scene_label_data_review_no_training')
        self.assertFalse(recommendation['future_gpu_training_allowed'])

    def test_missing_prediction_or_truth_mask_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            acceptance_path = root / 'acceptance.json'
            request_path.write_text(
                json.dumps({
                    'scenes': [{
                        'scene_id': 'scene-missing-truth',
                        'prediction_mask': _write_mask(root / 'prediction.npy', np.ones((2, 2))),
                    }],
                }),
                encoding='utf-8',
            )
            acceptance_path.write_text(json.dumps({'decision': 'blocked_research_grade'}), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'missing prediction_mask or truth_mask'):
                build_diagnostics(
                    request_path=request_path,
                    acceptance_report_path=acceptance_path,
                    materialization_result_dir=root / 'mat',
                    output_root=root / 'out',
                )

    def test_diagnostic_fields_keep_production_and_gpu_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pred = np.array([[0.99, 0.0], [0.0, 0.0]])
            truth = np.array([[1, 1], [0, 0]])
            request_path = root / 'request.json'
            acceptance_path = root / 'acceptance.json'
            materialization_dir = root / 'mat'
            _write_result(materialization_dir, 'scene-1')
            request_path.write_text(
                json.dumps({
                    'prediction_threshold': 0.5,
                    'scenes': [{
                        'scene_id': 'scene-1',
                        'prediction_mask': _write_mask(root / 'prediction.npy', pred),
                        'truth_mask': _write_mask(root / 'truth.npy', truth),
                        'baseline_mask': _write_mask(root / 'baseline.npy', np.zeros_like(truth)),
                    }],
                }),
                encoding='utf-8',
            )
            acceptance_path.write_text(json.dumps({'decision': 'blocked_research_grade'}), encoding='utf-8')

            report = build_diagnostics(
                request_path=request_path,
                acceptance_report_path=acceptance_path,
                materialization_result_dir=materialization_dir,
                output_root=root / 'out',
            )
            decision = json.loads((root / 'out' / 'next_candidate_decision.json').read_text(encoding='utf-8'))

        self.assertFalse(report['production_scoring_allowed'])
        self.assertFalse(report['promotion_allowed'])
        self.assertFalse(report['gpu_training_launched'])
        self.assertFalse(report['modal_gpu_call_launched'])
        self.assertFalse(decision['next_gpu_run_authorized'])
        self.assertFalse(decision['future_gpu_training_allowed'])


if __name__ == '__main__':
    unittest.main()
