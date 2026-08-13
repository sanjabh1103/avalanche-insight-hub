from __future__ import annotations

import unittest

from backend.common.audit_metadata import (
    build_decision_provenance,
    build_feature_completeness_row,
    build_latest_benchmark_summary,
    build_source_health_summary,
)


class AuditMetadataTests(unittest.TestCase):
    def test_build_source_health_summary_reports_partial_support(self) -> None:
        summary = build_source_health_summary(
            rows=[
                {
                    'status': 'ready',
                    'availability_reason': None,
                    'sar_coverage_state': 'full_coverage',
                    'snowpack_proxy': {'estimated_shear_strength': 4.2},
                },
                {
                    'status': 'unavailable_terrain',
                    'availability_reason': 'unavailable_terrain',
                    'snowpack_proxy': None,
                },
            ],
            weather_inputs=[{'snowfall_24h_cm': 12.0}],
            sar_evidence={'mask_asset_refs': ['mask-a'], 'sar_event_geometries': []},
            region_status='partial',
            generated_at='2026-05-03T00:00:00+00:00',
            evidence_summary={'positive_count': 0, 'manual_positive_count': 0, 'autonomous_positive_count': 0},
        )

        self.assertEqual(summary['summary_version'], 'source_health_v1')
        self.assertEqual(summary['support_status'], 'complete')
        self.assertTrue(summary['weather_available'])
        self.assertTrue(summary['snowpack_proxy_available'])
        self.assertIn('recent_activity_context', summary['missing_features'])

    def test_build_feature_completeness_row_supports_forecast_run_and_grid(self) -> None:
        row = build_feature_completeness_row(
            source_health={
                'overall_completeness': 0.75,
                'weather_available': True,
                'weather_source': 'open_meteo_forecast_downscaled_v1',
                'weather_freshness_hours': 3.2,
                'recent_activity_available': False,
                'terrain_available': True,
                'missing_features': ['recent_activity_context'],
            },
            forecast_grid_id='fg-1',
            forecast_run_id='fr-1',
        )

        self.assertEqual(row['forecast_grid_id'], 'fg-1')
        self.assertEqual(row['forecast_run_id'], 'fr-1')
        self.assertTrue(row['weather_available'])
        self.assertEqual(row['missing_features'], ['recent_activity_context'])

    def test_build_decision_provenance_marks_heuristic_origin(self) -> None:
        provenance = build_decision_provenance(
            threshold_profile='heuristic-risk-bands-v1',
            calibration_profile_version='calib-v1',
            calibration_method='isotonic',
            frequency_threshold_profile='local_grid_share_heuristic_v2',
            derived_from={'aggregation': 'highest_regional_level_by_cumulative_frequency', 'frequency_basis': 'cumulative_ge_threshold'},
            explainability_mode='tree_shap',
            selected_feature_count=12,
        )

        self.assertEqual(provenance['threshold_profile_origin'], 'heuristic_seeded')
        self.assertEqual(provenance['dominant_mapping'], 'heuristic_thresholds_and_frequency')
        self.assertEqual(provenance['selected_feature_count'], 12)

    def test_build_latest_benchmark_summary_aggregates_phase_seconds(self) -> None:
        summary = build_latest_benchmark_summary(
            benchmark_kind='training',
            phase_breakdown_seconds={'dataset_load_seconds': 1.2, 'fit_model_seconds': 4.3},
            input_context={'seed': 7},
            status='ok',
            artifact_ref='training_stage_metrics.json',
        )

        self.assertEqual(summary['benchmark_kind'], 'training')
        self.assertEqual(summary['total_seconds'], 5.5)
        self.assertEqual(summary['phase_breakdown_seconds']['fit_model_seconds'], 4.3)


if __name__ == '__main__':
    unittest.main()
