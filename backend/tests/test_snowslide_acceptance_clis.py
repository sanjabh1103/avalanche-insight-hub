from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.common.sar_acceptance_policy import SNOWSLIDE_EXPECTED_SCENE_IDS
from backend.scripts.build_snowslide_acceptance_report import build_report
from backend.scripts.run_snowslide_threshold_sweep import run_sweep


def _avalcd_report() -> dict:
    return {
        'production_scoring_allowed': False,
        'promotion_gate_report': {'decision': 'blocked_shadow_only'},
        'source_reports': [{
            'source_key': 'avalcd_zenodo_v1',
            'sar_prediction_metrics': {
                'evaluation_mode': 'scene_blended',
                'quality_gate': {
                    'passed': True,
                    'precision_floor_met': True,
                    'recall_floor_met': True,
                },
                'metrics': {
                    'threshold': 0.992,
                    'postprocess_min_component_area_px': 64,
                    'postprocess_opening_size_px': 0,
                },
            },
        }],
    }


class SnowSlideAcceptanceCliTests(unittest.TestCase):
    def test_build_report_classifies_current_like_metrics_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snow = {
                'status': 'ok',
                'dry_run': True,
                'beats_baseline': True,
                'precision': 0.5858659500305989,
                'recall': 0.4327486989198283,
                'f1': 0.4977990997447543,
                'false_positive_rate': 0.0016052570549306621,
                'scene_count': len(SNOWSLIDE_EXPECTED_SCENE_IDS),
                'region_coverage': list(SNOWSLIDE_EXPECTED_SCENE_IDS),
                'prediction_threshold': 0.992,
                'postprocess_min_component_area_px': 64,
                'postprocess_opening_size_px': 0,
            }
            snow_path = root / 'snow.json'
            avalcd_path = root / 'avalcd.json'
            snow_path.write_text(json.dumps(snow), encoding='utf-8')
            avalcd_path.write_text(json.dumps(_avalcd_report()), encoding='utf-8')
            mat_root = root / 'mat'
            for scene_id in SNOWSLIDE_EXPECTED_SCENE_IDS:
                scene_dir = mat_root / scene_id
                scene_dir.mkdir(parents=True)
                (scene_dir / 'sar_segment_result.json').write_text(
                    json.dumps({
                        'status': 'ok',
                        'mask_asset_refs': [f'sar-masks/heldout/{scene_id}/prediction_mask.tif'],
                        'persisted_events': 0,
                        'artifact_rows_persisted': 0,
                    }),
                    encoding='utf-8',
                )

            report = build_report(
                snow_report_path=snow_path,
                avalcd_benchmark_report_path=avalcd_path,
                materialization_result_dir=mat_root,
            )

        self.assertEqual(report['decision'], 'blocked_research_grade')
        blockers = {item['gate'] for item in report['blockers']}
        self.assertIn('precision_floor', blockers)
        self.assertIn('recall_floor', blockers)
        self.assertIn('f1_floor', blockers)

    def test_threshold_sweep_selects_passing_candidate_as_fresh_holdout_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prediction = np.array([[0.99, 0.99], [0.99, 0.10]], dtype=np.float32)
            truth = np.array([[1, 1], [1, 0]], dtype=np.float32)
            baseline = np.zeros((2, 2), dtype=np.float32)
            pred_path = root / 'prediction.npy'
            truth_path = root / 'truth.npy'
            baseline_path = root / 'baseline.npy'
            np.save(pred_path, prediction)
            np.save(truth_path, truth)
            np.save(baseline_path, baseline)
            request_path = root / 'request.json'
            output_path = root / 'sweep.json'
            request_path.write_text(
                json.dumps({
                    'dry_run': True,
                    'baseline_margin': 0.05,
                    'prediction_model_version': 'test-model',
                    'scenes': [{
                        'scene_id': 'scene-1',
                        'region_key': 'test-region',
                        'prediction_mask': str(pred_path),
                        'truth_mask': str(truth_path),
                        'baseline_mask': str(baseline_path),
                    }],
                }),
                encoding='utf-8',
            )

            report = run_sweep(
                request_path=request_path,
                output_path=output_path,
                threshold_grid=[0.985],
                component_areas=[0],
                opening_sizes=[0],
            )

        self.assertEqual(report['decision'], 'requires_fresh_final_holdout')
        self.assertFalse(report['bounded_candidate_warranted'])
        self.assertTrue(report['avalcd_recheck_required'])
        self.assertEqual(report['passing_candidate_count'], 1)


if __name__ == '__main__':
    unittest.main()
