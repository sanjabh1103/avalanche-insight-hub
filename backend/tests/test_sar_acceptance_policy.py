from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.common.sar_acceptance_policy import (
    SNOWSLIDE_EXPECTED_SCENE_IDS,
    assert_sar_acceptance_for_promotion,
    evaluate_snowslide_research_grade,
    summarize_materialization_results,
)


def _snow_report(**overrides):
    payload = {
        'status': 'ok',
        'dry_run': True,
        'beats_baseline': True,
        'precision': 0.70,
        'recall': 0.50,
        'f1': 0.60,
        'false_positive_rate': 0.002,
        'scene_count': len(SNOWSLIDE_EXPECTED_SCENE_IDS),
        'region_coverage': list(SNOWSLIDE_EXPECTED_SCENE_IDS),
        'prediction_threshold': 0.992,
        'postprocess_min_component_area_px': 64,
        'postprocess_opening_size_px': 0,
    }
    payload.update(overrides)
    return payload


def _avalcd_report(**quality_overrides):
    quality = {
        'passed': True,
        'precision_floor_met': True,
        'recall_floor_met': True,
    }
    quality.update(quality_overrides)
    return {
        'production_scoring_allowed': False,
        'promotion_gate_report': {'decision': 'blocked_shadow_only'},
        'source_reports': [{
            'source_key': 'avalcd_zenodo_v1',
            'sar_prediction_metrics': {
                'evaluation_mode': 'scene_blended',
                'quality_gate': quality,
                'metrics': {
                    'threshold': 0.992,
                    'postprocess_min_component_area_px': 64,
                    'postprocess_opening_size_px': 0,
                },
            },
        }],
    }


def _materialization_summary(**overrides):
    payload = {
        'status': 'ok',
        'result_file_count': len(SNOWSLIDE_EXPECTED_SCENE_IDS),
        'ok_result_count': len(SNOWSLIDE_EXPECTED_SCENE_IDS),
        'covered_scene_ids': list(SNOWSLIDE_EXPECTED_SCENE_IDS),
        'missing_scene_ids': [],
        'mask_asset_ref_count': len(SNOWSLIDE_EXPECTED_SCENE_IDS),
        'persisted_events': 0,
        'artifact_rows_persisted': 0,
    }
    payload.update(overrides)
    return payload


class SarAcceptancePolicyTests(unittest.TestCase):
    def test_current_v3_area64_metrics_fail_research_grade_policy(self) -> None:
        report = evaluate_snowslide_research_grade(
            _snow_report(
                precision=0.5858659500305989,
                recall=0.4327486989198283,
                f1=0.4977990997447543,
                false_positive_rate=0.0016052570549306621,
            ),
            avalcd_benchmark_report=_avalcd_report(),
            materialization_summary=_materialization_summary(),
        )

        self.assertEqual(report['decision'], 'blocked_research_grade')
        self.assertFalse(report['accepted_research_grade'])
        self.assertTrue(report['bounded_candidate_warranted'])
        blockers = {item['gate'] for item in report['blockers']}
        self.assertIn('precision_floor', blockers)
        self.assertIn('recall_floor', blockers)
        self.assertIn('f1_floor', blockers)
        self.assertNotIn('false_positive_rate_ceiling', blockers)

    def test_synthetic_research_grade_report_passes(self) -> None:
        report = evaluate_snowslide_research_grade(
            _snow_report(),
            avalcd_benchmark_report=_avalcd_report(),
            materialization_summary=_materialization_summary(),
        )

        self.assertEqual(report['decision'], 'accepted_research_grade')
        self.assertTrue(report['accepted_research_grade'])
        assert_sar_acceptance_for_promotion(report)

    def test_missing_scenes_non_dry_run_and_baseline_failure_block(self) -> None:
        report = evaluate_snowslide_research_grade(
            _snow_report(
                dry_run=False,
                beats_baseline=False,
                scene_count=6,
                region_coverage=list(SNOWSLIDE_EXPECTED_SCENE_IDS[:-1]),
            ),
            avalcd_benchmark_report=_avalcd_report(),
            materialization_summary=_materialization_summary(),
        )

        blockers = {item['gate'] for item in report['blockers']}
        self.assertIn('dry_run', blockers)
        self.assertIn('beats_baseline', blockers)
        self.assertIn('scene_count', blockers)
        self.assertIn('scene_coverage', blockers)

    def test_qualification_set_tuning_requires_fresh_final_holdout_even_when_metrics_pass(self) -> None:
        report = evaluate_snowslide_research_grade(
            _snow_report(),
            avalcd_benchmark_report=_avalcd_report(),
            materialization_summary=_materialization_summary(),
            qualification_set_used_for_model_selection=True,
        )

        self.assertEqual(report['decision'], 'requires_fresh_final_holdout')
        self.assertFalse(report['accepted_research_grade'])
        self.assertTrue(report['requires_fresh_final_holdout'])
        with self.assertRaisesRegex(ValueError, 'fresh final'):
            assert_sar_acceptance_for_promotion(report)

    def test_final_acceptance_requires_avalcd_and_materialization_provenance(self) -> None:
        report = evaluate_snowslide_research_grade(_snow_report())

        blockers = {item['gate'] for item in report['blockers']}
        self.assertIn('avalcd_provenance', blockers)
        self.assertIn('materialization_summary', blockers)

    def test_summarize_materialization_results_requires_every_expected_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            scene_dir = Path(tmpdir) / SNOWSLIDE_EXPECTED_SCENE_IDS[0]
            scene_dir.mkdir(parents=True)
            (scene_dir / 'sar_segment_result.json').write_text(
                (
                    '{"status":"ok","mask_asset_refs":["sar-masks/heldout/'
                    f'{SNOWSLIDE_EXPECTED_SCENE_IDS[0]}/prediction_mask.tif"],'
                    '"persisted_events":0,"artifact_rows_persisted":0}'
                ),
                encoding='utf-8',
            )

            summary = summarize_materialization_results(Path(tmpdir))

        self.assertEqual(summary['status'], 'incomplete')
        self.assertIn(SNOWSLIDE_EXPECTED_SCENE_IDS[1], summary['missing_scene_ids'])


if __name__ == '__main__':
    unittest.main()
