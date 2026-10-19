from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.reproduction.swiss_ravafcast.constants import RF1_RESOURCE_KEY, RF2_RESOURCE_KEY, USAGE_BOUNDARY
from backend.reproduction.swiss_ravafcast.aggregate import (
    RAVAFCAST_REFERENCE_REFINED_THRESHOLDS,
    build_elev_simple_aggregation,
    build_full_aggregation_readiness,
    compute_refined_discretization_thresholds,
    discretize_expected_danger,
    nearest_elevation_band,
)
from backend.reproduction.swiss_ravafcast.data_loader import inspect_swiss_frame, validate_swiss_frame
from backend.reproduction.swiss_ravafcast.evaluate import build_reproduction_summary, markdown_summary
from backend.reproduction.swiss_ravafcast.features import (
    FEATURE_SET_NAMES,
    select_feature_set,
    validate_no_banned_features,
)
from backend.reproduction.swiss_ravafcast.interpolate_gpxyz import (
    build_station_metadata_template_frame,
    build_station_metadata_payload,
    build_gpxyz_readiness_payload,
    evaluate_gpxyz_loocv,
    inspect_gpxyz_readiness,
    predict_gpxyz,
    write_station_metadata_template,
)
from backend.reproduction.swiss_ravafcast.manifest import (
    build_manifest_payload,
    build_resource,
    read_manifest,
    write_manifest,
)
from backend.reproduction.swiss_ravafcast.train_rf4 import SwissRF4Config, train_rf4_danger
from backend.reproduction.swiss_ravafcast.train_rf4 import build_rf4_feature_audit
from backend.scripts.download_swiss_ravafcast_data import select_resource_url


class SwissRavafcastReproductionTests(unittest.TestCase):
    def _sample_frame(self, target_column: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                'station_id': ['A', 'B', 'C'],
                'date': ['2020-01-01', '2020-01-02', '2020-01-03'],
                'lat': [46.8, 46.9, 47.0],
                'lon': [8.1, 8.2, 8.3],
                'elevation_m': [1800, 2200, 2500],
                'Pen_depth': [20.0, 30.0, 40.0],
                'ccl': [0.2, 0.3, 0.4],
                'Sn38': [1.2, 1.1, 1.0],
                'Sk38': [0.5, 0.6, 0.7],
                'SSI': [0.8, 0.7, 0.6],
                'wind_speed': [4.0, 5.0, 6.0],
                target_column: [1, 2, 3],
            }
        )

    def _rf4_training_frame(self) -> pd.DataFrame:
        rows = []
        for season_start in (2017, 2018, 2019, 2020):
            for idx, danger in enumerate((1, 2, 3, 4, 1, 2, 3, 4)):
                rows.append(
                    {
                        'station_id': f'S{idx}',
                        'date': f'{season_start + 1}-01-{idx + 1:02d}',
                        'warnreg': 10 + (idx % 2),
                        'lat': 46.0 + idx / 100,
                        'lon': 8.0 + idx / 100,
                        'elevation_station': 1600 + (danger * 200),
                        'Pen_depth': float(10 * danger + idx),
                        'ccl': float(danger) / 10.0,
                        'Sn38': float(danger),
                        'Sk38': float(danger) / 2.0,
                        'SSI': float(5 - danger),
                        'HN24': float(danger * 4),
                        'wind_speed': float(danger * 3),
                        'set': 'train',
                        'dangerLevel': danger,
                    }
                )
        return pd.DataFrame(rows)

    def test_rf1_and_rf2_schema_reports_are_research_only(self) -> None:
        rf1_report = validate_swiss_frame(self._sample_frame('D_forecast'), resource_key=RF1_RESOURCE_KEY)
        rf2_report = validate_swiss_frame(self._sample_frame('D_tidy'), resource_key=RF2_RESOURCE_KEY)

        self.assertEqual(rf1_report.usage_boundary, USAGE_BOUNDARY)
        self.assertEqual(rf1_report.target_column, 'D_forecast')
        self.assertTrue(rf1_report.valid_for_stage2)
        self.assertEqual(rf2_report.target_column, 'D_tidy')
        self.assertTrue(rf2_report.valid_for_stage1)
        self.assertIn('SSI', rf2_report.snowpack_profile_features)

    def test_schema_rejects_binary_production_frame_without_swiss_target(self) -> None:
        frame = self._sample_frame('label').drop(columns=['D_forecast'], errors='ignore')

        report = inspect_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)

        self.assertFalse(report.valid_for_stage1)
        self.assertIn('target_label', report.missing_required_groups)
        with self.assertRaisesRegex(ValueError, 'not valid for Stage-1'):
            validate_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)

    def test_schema_accepts_real_envidat_column_names(self) -> None:
        frame = pd.DataFrame(
            {
                'datum': ['2020-01-01', '2020-01-02'],
                'station_code': ['ST01', 'ST02'],
                'warnreg': [111, 222],
                'elevation_station': [1800, 2200],
                'dangerLevel': [2, 3],
                'pwl_100': [0.0, 1.0],
                'sn38_pwl': [0.2, 0.3],
                'sk38_pwl_100': [0.4, 0.5],
                'Pen_depth': [25.0, 31.0],
                'min_ccl_pen': [0.1, 0.2],
                'HN24': [5.0, 10.0],
            }
        )

        rf1_report = validate_swiss_frame(frame, resource_key=RF1_RESOURCE_KEY)
        rf2_report = validate_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)

        self.assertEqual(rf1_report.target_column, 'dangerLevel')
        self.assertEqual(rf1_report.date_column, 'datum')
        self.assertEqual(rf1_report.station_column, 'station_code')
        self.assertEqual(rf1_report.elevation_column, 'elevation_station')
        self.assertIn('sn38_pwl', rf1_report.snowpack_profile_features)
        self.assertIn('HN24', rf2_report.meteo_feature_candidates)

    def test_manifest_requires_both_resources_and_blocks_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rf1 = root / 'data_rf1_forecast.csv'
            rf2 = root / 'data_rf2_tidy.csv'
            rf1.write_text('station_id,date,D_forecast\nA,2020-01-01,2\n', encoding='utf-8')
            rf2.write_text('station_id,date,D_tidy\nA,2020-01-01,2\n', encoding='utf-8')
            resources = [
                build_resource(resource_key=RF1_RESOURCE_KEY, path=rf1, source_url='https://example.test/rf1.csv'),
                build_resource(resource_key=RF2_RESOURCE_KEY, path=rf2, source_url='https://example.test/rf2.csv'),
            ]

            manifest = build_manifest_payload(resources=resources)
            manifest_path = root / 'manifest.json'
            write_manifest(manifest, manifest_path)
            loaded = read_manifest(manifest_path)

            self.assertEqual(loaded['usage_boundary'], USAGE_BOUNDARY)
            self.assertFalse(loaded['production_scoring_allowed'])
            self.assertFalse(loaded['model_status_mutation_allowed'])

            incomplete = dict(manifest)
            incomplete['resources'] = incomplete['resources'][:1]
            with self.assertRaisesRegex(ValueError, 'missing required resources'):
                build_manifest_payload(resources=resources[:1])

    def test_manifest_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'data_rf1_forecast.csv'
            path.write_text('changed', encoding='utf-8')
            resource = build_resource(
                resource_key=RF1_RESOURCE_KEY,
                path=path,
                source_url='https://example.test/rf1.csv',
                expected_sha256='0' * 64,
            )
            self.assertEqual(resource.checksum_status, 'mismatch')
            with self.assertRaisesRegex(ValueError, 'missing required resources|checksum mismatch'):
                build_manifest_payload(resources=[resource])

    def test_resource_selection_uses_rf1_forecast_and_rf2_tidy_patterns(self) -> None:
        resources = [
            {'name': 'readme', 'url': 'https://example.test/readme.txt', 'format': 'TXT'},
            {'name': 'data_rf1_forecast.csv', 'url': 'https://example.test/data_rf1_forecast.csv', 'format': 'CSV'},
            {'name': 'data_rf2_tidy.csv', 'url': 'https://example.test/data_rf2_tidy.csv', 'format': 'CSV'},
        ]

        self.assertEqual(
            select_resource_url(resources, resource_key=RF1_RESOURCE_KEY),
            'https://example.test/data_rf1_forecast.csv',
        )
        self.assertEqual(
            select_resource_url(resources, resource_key=RF2_RESOURCE_KEY),
            'https://example.test/data_rf2_tidy.csv',
        )

    def test_train_rf4_keeps_research_boundary_and_reports_paper_metrics(self) -> None:
        frame = self._rf4_training_frame().rename(columns={'dangerLevel': 'D_tidy'})

        result = train_rf4_danger(
            frame,
            config=SwissRF4Config(seed=7, n_estimators=10, min_samples_leaf=1),
        )

        self.assertEqual(result['usage_boundary'], USAGE_BOUNDARY)
        self.assertFalse(result['production_scoring_allowed'])
        self.assertEqual(result['model_key'], 'rf4_danger_v0')
        self.assertIn('accuracy', result['metrics'])
        self.assertIn('macro_f1', result['metrics'])
        self.assertIn('calibration', result)
        self.assertIn('uncalibrated_metrics', result)
        self.assertIn('class_support', result['metrics'])
        self.assertEqual(result['metrics']['confusion_matrix_labels'], [1, 2, 3, 4])
        self.assertGreater(result['split']['train_rows'], 0)
        self.assertGreater(result['split']['test_rows'], 0)
        self.assertGreater(len(result['evaluation_rows']), 0)
        self.assertEqual(set(result['evaluation_rows'][0]['class_probabilities']), {'1', '2', '3', '4'})
        self.assertAlmostEqual(sum(result['evaluation_rows'][0]['class_probabilities'].values()), 1.0)

    def test_feature_sets_reject_banned_columns_and_audit_variants(self) -> None:
        frame = self._rf4_training_frame()

        with self.assertRaisesRegex(ValueError, 'banned leakage'):
            validate_no_banned_features(['dangerLevel', 'Pen_depth'])

        guarded = select_feature_set(frame, feature_set_name='leakage_guarded', target_column='dangerLevel')
        self.assertNotIn('dangerLevel', guarded.selected_columns)
        self.assertNotIn('set', guarded.selected_columns)
        self.assertNotIn('warnreg', guarded.selected_columns)

        audit = build_rf4_feature_audit(
            frame,
            config=SwissRF4Config(seed=7, n_estimators=5, min_samples_leaf=1),
        )

        self.assertEqual(audit['usage_boundary'], USAGE_BOUNDARY)
        self.assertFalse(audit['production_scoring_allowed'])
        self.assertEqual({variant['feature_set']['name'] for variant in audit['variants']}, set(FEATURE_SET_NAMES))
        self.assertIn('class_support', audit['variants'][0]['metrics'])
        self.assertIn('calibrated_brier_score', audit['variants'][0]['calibration'])

    def test_calibration_split_is_used_and_probability_quality_reported(self) -> None:
        frame = self._rf4_training_frame()

        result = train_rf4_danger(
            frame,
            config=SwissRF4Config(seed=7, n_estimators=5, min_samples_leaf=1),
        )

        calibration = result['calibration']
        self.assertEqual(calibration['schema_version'], 'swiss_rf4_probability_calibration_v1')
        self.assertGreater(calibration['calibration_rows'], 0)
        self.assertIn(calibration['method'], {'isotonic', 'mixed_with_sigmoid_fallback', 'mixed_isotonic_identity'})
        self.assertIn('brier_score', calibration['uncalibrated'])
        self.assertIn('brier_score', calibration['calibrated'])
        self.assertIn('classwise_bins', calibration['calibrated'])

    def test_gpxyz_readiness_blocks_without_station_coordinates(self) -> None:
        frame = pd.DataFrame(
            {
                'datum': ['2020-01-01', '2020-01-02'],
                'station_code': ['ST01', 'ST02'],
                'elevation_station': [1800, 2200],
                'dangerLevel': [2, 3],
                'pwl_100': [0.0, 1.0],
                'sn38_pwl': [0.2, 0.3],
                'sk38_pwl_100': [0.4, 0.5],
                'Pen_depth': [25.0, 31.0],
            }
        )

        report = inspect_gpxyz_readiness(frame, min_station_count=1)
        payload = build_gpxyz_readiness_payload(frame)

        self.assertFalse(report.ready)
        self.assertEqual(report.decision, 'blocked_station_coordinates_required')
        self.assertIn('latitude', report.missing_required_columns)
        self.assertFalse(payload['production_scoring_allowed'])

        metadata_payload = build_station_metadata_payload(frame)
        self.assertEqual(metadata_payload['readiness']['decision'], 'blocked_station_coordinates_required')
        self.assertFalse(metadata_payload['production_scoring_allowed'])

    def test_station_metadata_template_preserves_station_list_but_does_not_unblock_blank_coordinates(self) -> None:
        frame = pd.DataFrame(
            {
                'datum': ['2020-01-01', '2020-01-03', '2020-01-02'],
                'station_code': ['ST01', 'ST01', 'ST02'],
                'elevation_station': [1800, 1820, 2200],
                'dangerLevel': [2, 3, 1],
                'pwl_100': [0.0, 1.0, 0.0],
                'sn38_pwl': [0.2, 0.3, 0.1],
                'sk38_pwl_100': [0.4, 0.5, 0.2],
                'Pen_depth': [25.0, 31.0, 18.0],
            }
        )

        template = build_station_metadata_template_frame(frame)
        payload = build_station_metadata_payload(frame, template)

        self.assertEqual(list(template['station_code']), ['ST01', 'ST02'])
        self.assertEqual(template.loc[0, 'source_row_count'], 2)
        self.assertEqual(template.loc[0, 'elevation_m'], 1810.0)
        self.assertEqual(payload['readiness']['decision'], 'blocked_station_metadata_incomplete')
        self.assertEqual(payload['readiness']['coordinate_missing_row_count'], 2)

    def test_station_metadata_template_writer_and_complete_metadata_join(self) -> None:
        frame = pd.DataFrame(
            {
                'datum': ['2020-01-01', '2020-01-02'],
                'station_code': ['ST01', 'ST02'],
                'elevation_station': [1800, 2200],
                'dangerLevel': [2, 3],
                'pwl_100': [0.0, 1.0],
                'sn38_pwl': [0.2, 0.3],
                'sk38_pwl_100': [0.4, 0.5],
                'Pen_depth': [25.0, 31.0],
            }
        )
        metadata = pd.DataFrame(
            {
                'station_code': ['ST01', 'ST02'],
                'latitude': [46.8, 46.9],
                'longitude': [8.1, 8.2],
                'elevation_m': [1800, 2200],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'station_metadata_template.csv'
            written = write_station_metadata_template(frame, output)
            header = output.read_text(encoding='utf-8').splitlines()[0]

        self.assertEqual(len(written), 2)
        self.assertEqual(header, 'station_code,latitude,longitude,elevation_m,active_start,active_end,source_row_count,metadata_review_status,reviewer_notes')
        payload = build_station_metadata_payload(frame, metadata)
        self.assertEqual(payload['readiness']['decision'], 'ready_for_gpxyz_metadata_join')
        self.assertEqual(payload['readiness']['coordinate_missing_row_count'], 0)
        self.assertEqual(payload['coordinate_coverage']['latitude_non_null_rows'], 2)

    def test_gpxyz_predicts_on_synthetic_coordinates(self) -> None:
        train = pd.DataFrame(
            {
                'latitude': [46.0, 46.1, 46.2],
                'longitude': [8.0, 8.1, 8.2],
                'elevation_m': [1600, 2000, 2400],
                'expected_danger': [1.0, 2.0, 3.0],
            }
        )
        grid = pd.DataFrame(
            {
                'latitude': [46.05, 46.15],
                'longitude': [8.05, 8.15],
                'elevation_m': [1800, 2200],
            }
        )

        result = predict_gpxyz(train, grid)

        self.assertEqual(result['usage_boundary'], USAGE_BOUNDARY)
        self.assertFalse(result['production_scoring_allowed'])
        self.assertEqual(len(result['predictions']), 2)
        self.assertIn('expected_danger_std', result['predictions'][0])

    def test_gpxyz_refuses_oversized_exact_gp_and_reports_loocv(self) -> None:
        frame = pd.DataFrame(
            {
                'latitude': [46.0, 46.1, 46.2],
                'longitude': [8.0, 8.1, 8.2],
                'elevation_m': [1600, 2000, 2400],
                'expected_danger': [1.0, 2.0, 3.0],
            }
        )

        with self.assertRaisesRegex(ValueError, 'blocked_requires_sparse_gp_design'):
            predict_gpxyz(frame, frame, max_train_rows=2)

        blocked = evaluate_gpxyz_loocv(frame, max_train_rows=2)
        self.assertEqual(blocked['decision'], 'blocked_requires_sparse_gp_design')
        complete = evaluate_gpxyz_loocv(frame, max_train_rows=5)
        self.assertEqual(complete['decision'], 'loocv_complete')
        self.assertIn('rmse', complete['metrics'])

    def test_elev_simple_aggregation_keeps_research_boundary(self) -> None:
        rows = [
            {
                'date': '2020-01-01',
                'warnreg': 11,
                'elevation_station': 1590,
                'true_danger': 2,
                'predicted_danger': 2,
                'expected_danger': 2.1,
            },
            {
                'date': '2020-01-01',
                'warnreg': 11,
                'elevation_station': 2410,
                'true_danger': 3,
                'predicted_danger': 4,
                'expected_danger': 3.6,
            },
            {
                'date': '2020-01-02',
                'warnreg': 12,
                'elevation_station': 1205,
                'true_danger': 1,
                'predicted_danger': 1,
                'expected_danger': 1.1,
            },
        ]

        result = build_elev_simple_aggregation(rows)

        self.assertEqual(nearest_elevation_band(1510), 1600)
        self.assertEqual(result['usage_boundary'], USAGE_BOUNDARY)
        self.assertFalse(result['production_scoring_allowed'])
        self.assertEqual(result['input_rows'], 3)
        self.assertEqual(len(result['region_day_rows']), 2)
        self.assertIn('accuracy', result['metrics'])

        readiness = build_full_aggregation_readiness(
            gp_grid_available=False,
            warning_region_polygons_available=False,
        )
        self.assertEqual(readiness['decision'], 'blocked_full_aggregation_inputs_required')
        self.assertIn('gpxyz_1km_grid', readiness['missing_required_inputs'])
        self.assertFalse(readiness['production_scoring_allowed'])

    def test_refined_discretization_uses_monotonic_training_thresholds(self) -> None:
        thresholds = compute_refined_discretization_thresholds(
            expected_danger_values=[1.1, 1.5, 2.1, 2.8, 3.2, 3.7],
            true_training_labels=[1, 1, 2, 3, 3, 4],
        )

        self.assertEqual(thresholds[0], 0.5)
        self.assertTrue(all(left <= right for left, right in zip(thresholds, thresholds[1:])))
        self.assertEqual(discretize_expected_danger(2.42), 3)
        self.assertEqual(discretize_expected_danger(3.44), 4)
        self.assertEqual(discretize_expected_danger(3.43), 3)

        with self.assertRaisesRegex(ValueError, 'equal length'):
            compute_refined_discretization_thresholds([1.0, 2.0], [1])

    def test_elev_simple_aggregation_can_use_refined_expected_danger_thresholds(self) -> None:
        rows = [
            {
                'date': '2020-01-03',
                'warnreg': 14,
                'elevation_station': 2020,
                'true_danger': 4,
                'predicted_danger': 3,
                'expected_danger': 3.45,
            }
        ]

        result = build_elev_simple_aggregation(
            rows,
            refined_thresholds=RAVAFCAST_REFERENCE_REFINED_THRESHOLDS,
        )

        self.assertEqual(result['discretization']['method'], 'research_refined_expected_danger_thresholds')
        self.assertEqual(result['region_day_rows'][0]['predicted_danger'], 4)
        self.assertFalse(result['production_scoring_allowed'])

    def test_reproduction_summary_separates_research_from_operational_claims(self) -> None:
        validation_report = {
            'schema_version': 'swiss_ravafcast_validation_report_v1',
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'reports': [
                {'resource_key': RF1_RESOURCE_KEY, 'row_count': 10},
                {'resource_key': RF2_RESOURCE_KEY, 'row_count': 5},
            ],
        }
        rf4_result = {
            'schema_version': 'swiss_rf4_reproduction_result_v1',
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'model_status_mutation_allowed': False,
            'metrics': {'accuracy': 0.74, 'macro_f1': 0.61, 'per_class_f1': {'4': 0.2}},
        }
        gpxyz_report = {
            'schema_version': 'swiss_gpxyz_readiness_report_v1',
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'model_status_mutation_allowed': False,
            'readiness': {
                'ready': False,
                'decision': 'blocked_station_coordinates_required',
                'station_count': 129,
                'missing_required_columns': ['latitude', 'longitude'],
            },
        }
        aggregation_result = {
            'schema_version': 'swiss_elev_simple_aggregation_result_v1',
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'model_status_mutation_allowed': False,
            'metrics': {'accuracy': 0.66, 'macro_f1': 0.58},
            'claim_boundary': 'station_row_baseline',
        }

        summary = build_reproduction_summary(
            validation_report=validation_report,
            rf4_result=rf4_result,
            gpxyz_report=gpxyz_report,
            aggregation_result=aggregation_result,
        )
        markdown = markdown_summary(summary)

        self.assertFalse(summary['production_scoring_allowed'])
        self.assertFalse(summary['full_operational_detection_claim_allowed'])
        self.assertTrue(summary['sar_remote_sensing_shadow_gated'])
        self.assertEqual(summary['rf4_claim_boundary'], 'initial_reproduction_signal_pending_parity_audit')
        self.assertEqual(summary['headline_metrics']['gpxyz_decision'], 'blocked_station_coordinates_required')
        self.assertIn('station_coordinates_required_for_gpxyz', {item['blocker'] for item in summary['remaining_blockers']})
        self.assertIn('Full operational detection claim allowed', markdown)
        self.assertIn('RF4 claim boundary', markdown)

    def test_reproduction_summary_fails_closed_on_production_claim(self) -> None:
        payload = {
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'model_status_mutation_allowed': False,
        }
        bad_rf4 = dict(payload)
        bad_rf4['production_scoring_allowed'] = True

        with self.assertRaisesRegex(ValueError, 'production_scoring_allowed=false'):
            build_reproduction_summary(
                validation_report={**payload, 'reports': []},
                rf4_result=bad_rf4,
                gpxyz_report={**payload, 'readiness': {}},
                aggregation_result={**payload, 'metrics': {}},
            )


if __name__ == '__main__':
    unittest.main()
