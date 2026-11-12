"""Acceptance tests for immutable evidence replay and shadow-only candidates."""
from __future__ import annotations

import unittest

from backend.common.evidence_replay import (
    SCIENTIST_ONLY_CLAIM_BOUNDARY,
    build_evidence_replay_frame,
    replay_is_grounded_for_shadow_training,
)
from backend.common.reviewed_shadow_training import (
    build_shadow_training_candidate_pack,
    evaluate_reviewed_shadow_training_case,
)
from backend.common.scientist_evidence_cases import build_scientist_evidence_cases


def grounded_cell(**overrides):
    cell = {
        'row': 4,
        'col': 7,
        'lat': 35.123,
        'lng': 76.456,
        'lat_end': 35.133,
        'lng_end': 76.466,
        'forecast_hour': 12,
        'risk_score': 4,
        'probability': 0.72,
        'uncertainty_class': 'high',
        'uncertainty_span': 0.18,
        'feature_values': {'snowfall_24h_cm': 24.0, 'wind_speed_kmh': 48.0},
        'weather_inputs': {'snowfall_24h_cm': 24.0},
        'terrain_inputs': {'slope_angle_deg': 38.0},
        'verification_packet': {
            'baseline_p25': 0.2,
            'baseline_p50': 0.4,
            'baseline_p75': 0.6,
            'observed': 0.8,
            'residual_zscore': 2.1,
            'anomaly_state': 'anomaly',
            'source_freshness_hours': {'weather': 3.0},
            'evidence_refs': ['weather:great_himalaya:cell_4_7:2026-01-15T12:00:00Z'],
            'contributing_sensors': ['weather'],
            'baseline_ids': ['baseline:great_himalaya:cell_4_7:seasonal'],
            'lineage': {
                'verified': True,
                'source_lineage': {
                    'weather': {
                        'reference': 'weather:great_himalaya:cell_4_7:2026-01-15T12:00:00Z',
                        'verified': True,
                        'acquisition_time': '2026-01-15T09:00:00Z',
                    },
                },
            },
            'attribution_bucket': 'forcing_error',
            'has_synthetic_evidence': False,
            'data_quality': {
                'minimum_sources_satisfied': True,
                'lineage_verified': True,
                'freshness_complete': True,
            },
        },
        'fusion_evidence': {'snow_depth_m': 1.1, 'consensus_score': 0.85},
    }
    cell.update(overrides)
    return cell


def grounded_metadata(**overrides):
    metadata = {
        'synthetic_inputs_present': False,
        'model_version': 'rf-2026.01',
        'config_hash': 'a' * 64,
        'feature_schema_hash': 'b' * 64,
    }
    metadata.update(overrides)
    return metadata


class TestEvidenceReplayFrame(unittest.TestCase):
    def test_grounded_frame_preserves_raw_display_and_alignment(self) -> None:
        frame = build_evidence_replay_frame(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(),
            model_metadata=grounded_metadata(),
        )

        self.assertEqual(frame['claim_boundary'], SCIENTIST_ONLY_CLAIM_BOUNDARY)
        self.assertEqual(frame['display']['label'], 'MODEL-RENDERED SCIENTIST REPLAY')
        self.assertFalse(frame['display']['satellite_imagery'])
        self.assertFalse(frame['display']['may_change_public_risk'])
        self.assertEqual(frame['observed']['status'], 'available')
        self.assertEqual(frame['raw_layers']['feature_values']['snowfall_24h_cm'], 24.0)
        self.assertEqual(frame['forecast']['cell_row'], 4)
        self.assertEqual(frame['forecast']['forecast_hour'], 12)
        self.assertTrue(replay_is_grounded_for_shadow_training(frame))

    def test_synthetic_or_unavailable_evidence_never_becomes_grounded(self) -> None:
        synthetic = build_evidence_replay_frame(
            forecast_run_id='run-1',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(verification_packet={
                **grounded_cell()['verification_packet'],
                'has_synthetic_evidence': True,
            }),
            model_metadata=grounded_metadata(),
        )
        unavailable = build_evidence_replay_frame(
            forecast_run_id='run-1',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(verification_packet={
                **grounded_cell()['verification_packet'],
                'observed': None,
            }),
            model_metadata=grounded_metadata(),
        )

        self.assertEqual(synthetic['observed']['status'], 'unavailable')
        self.assertEqual(synthetic['observed']['unavailable_reason'], 'synthetic_evidence_status_not_verified_false')
        self.assertFalse(replay_is_grounded_for_shadow_training(synthetic))
        self.assertEqual(unavailable['observed']['status'], 'unavailable')
        self.assertEqual(unavailable['observed']['unavailable_reason'], 'no_independent_observation')
        self.assertFalse(replay_is_grounded_for_shadow_training(unavailable))

    def test_missing_lineage_is_not_provenance_complete(self) -> None:
        frame = build_evidence_replay_frame(
            forecast_run_id='run-1',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(verification_packet={
                **grounded_cell()['verification_packet'],
                'lineage': {},
                'evidence_refs': [],
                'baseline_ids': [],
            }),
            model_metadata=grounded_metadata(),
        )

        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_derives_model_and_feature_hashes_from_persisted_metadata(self) -> None:
        frame = build_evidence_replay_frame(
            forecast_run_id='run-1',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(),
            model_metadata={
                'synthetic_inputs_present': False,
                'model_version': 'rf-2026.01',
                'feature_columns': ['snowfall_24h_cm', 'wind_speed_kmh'],
                'selected_features': ['snowfall_24h_cm', 'wind_speed_kmh'],
                'calibration_profile_version': 'calibration-v1',
            },
        )

        self.assertIn('model_config_sha256', frame['lineage']['source_hashes'])
        self.assertIn('feature_schema_sha256', frame['lineage']['source_hashes'])


class TestReplayGroundingParityMatrix(unittest.TestCase):
    """Negative fixture matrix — every invalid frame must return False.

    These mirror the SQL materialisation trigger conditions in
    20260714170000_reviewed_shadow_training_candidates.sql lines 148-174.
    """

    @staticmethod
    def _valid_frame():
        return build_evidence_replay_frame(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(),
            model_metadata=grounded_metadata(),
        )

    @staticmethod
    def _matching_case(frame):
        return {
            'forecast_run_id': '11111111-1111-1111-1111-111111111111',
            'region_key': 'great_himalaya',
            'cell_row': 4,
            'cell_col': 7,
        }

    def test_valid_frame_is_grounded(self) -> None:
        frame = self._valid_frame()
        self.assertTrue(replay_is_grounded_for_shadow_training(frame))
        self.assertTrue(
            replay_is_grounded_for_shadow_training(frame, case=self._matching_case(frame))
        )

    def test_missing_valid_time_utc_rejected(self) -> None:
        frame = self._valid_frame()
        frame['forecast']['valid_time_utc'] = None
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_empty_valid_time_utc_rejected(self) -> None:
        frame = self._valid_frame()
        frame['forecast']['valid_time_utc'] = ''
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_noncanonical_offset_timestamp_rejected(self) -> None:
        frame = self._valid_frame()
        frame['forecast']['valid_time_utc'] = '2026-01-15T12:00:00+00:00'
        frame['alignment']['time']['forecast_valid_time_utc'] = frame['forecast']['valid_time_utc']
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_empty_region_and_non_integer_cells_rejected(self) -> None:
        empty_region = self._valid_frame()
        empty_region['forecast']['region_key'] = ''
        decimal_cell = self._valid_frame()
        decimal_cell['forecast']['cell_row'] = 4.5
        self.assertFalse(replay_is_grounded_for_shadow_training(empty_region))
        self.assertFalse(replay_is_grounded_for_shadow_training(decimal_cell))

    def test_missing_source_freshness_hours_rejected(self) -> None:
        frame = self._valid_frame()
        frame['alignment']['time']['source_freshness_hours'] = {}
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_source_freshness_hours_not_mapping_rejected(self) -> None:
        frame = self._valid_frame()
        frame['alignment']['time']['source_freshness_hours'] = 'not-a-dict'
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_negative_or_nonfinite_source_freshness_rejected(self) -> None:
        negative = self._valid_frame()
        negative['alignment']['time']['source_freshness_hours'] = {'weather': -1.0}
        nonfinite = self._valid_frame()
        nonfinite['alignment']['time']['source_freshness_hours'] = {'weather': float('inf')}
        self.assertFalse(replay_is_grounded_for_shadow_training(negative))
        self.assertFalse(replay_is_grounded_for_shadow_training(nonfinite))

    def test_missing_observation_time_rejected(self) -> None:
        frame = self._valid_frame()
        frame['alignment']['time']['observation_times_utc'] = []
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_mismatched_alignment_grid_and_time_rejected(self) -> None:
        grid_mismatch = self._valid_frame()
        grid_mismatch['alignment']['grid']['cell_row'] = 99
        time_mismatch = self._valid_frame()
        time_mismatch['alignment']['time']['forecast_valid_time_utc'] = '2026-01-15T13:00:00Z'
        self.assertFalse(replay_is_grounded_for_shadow_training(grid_mismatch))
        self.assertFalse(replay_is_grounded_for_shadow_training(time_mismatch))

    def test_missing_forecast_identity_rejected(self) -> None:
        frame = self._valid_frame()
        frame['forecast']['forecast_run_id'] = ''
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_nonfinite_feature_value_rejected(self) -> None:
        frame = self._valid_frame()
        frame['raw_layers']['feature_values']['snowfall_24h_cm'] = float('nan')
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_invalid_source_hash_rejected(self) -> None:
        frame = self._valid_frame()
        frame['lineage']['source_hashes']['model_hash'] = 'not-a-sha256'
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_empty_lineage_reference_rejected(self) -> None:
        frame = self._valid_frame()
        frame['lineage']['evidence_refs'] = ['']
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_empty_source_hashes_rejected(self) -> None:
        frame = self._valid_frame()
        frame['lineage']['source_hashes'] = {}
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_mismatched_forecast_run_id_rejected(self) -> None:
        frame = self._valid_frame()
        case = {**self._matching_case(frame), 'forecast_run_id': 'different-run-id'}
        self.assertFalse(replay_is_grounded_for_shadow_training(frame, case=case))

    def test_mismatched_region_key_rejected(self) -> None:
        frame = self._valid_frame()
        case = {**self._matching_case(frame), 'region_key': 'different_region'}
        self.assertFalse(replay_is_grounded_for_shadow_training(frame, case=case))

    def test_mismatched_cell_row_rejected(self) -> None:
        frame = self._valid_frame()
        case = {**self._matching_case(frame), 'cell_row': 99}
        self.assertFalse(replay_is_grounded_for_shadow_training(frame, case=case))

    def test_mismatched_cell_col_rejected(self) -> None:
        frame = self._valid_frame()
        case = {**self._matching_case(frame), 'cell_col': 99}
        self.assertFalse(replay_is_grounded_for_shadow_training(frame, case=case))

    def test_without_case_param_frame_alignment_is_still_checked(self) -> None:
        frame = self._valid_frame()
        frame['alignment']['grid']['cell_col'] = 99
        self.assertFalse(replay_is_grounded_for_shadow_training(frame))

    def test_case_grid_mismatch_rejected(self) -> None:
        frame = self._valid_frame()
        case = {**self._matching_case(frame), 'forecast_grid_id': 'grid-b'}
        frame['forecast']['forecast_grid_id'] = 'grid-a'
        frame['alignment']['grid']['forecast_grid_id'] = 'grid-a'
        self.assertFalse(replay_is_grounded_for_shadow_training(frame, case=case))


class TestShadowTrainingEligibility(unittest.TestCase):
    def _case(self, **overrides):
        replay = build_evidence_replay_frame(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            forecast_hour=12,
            cell=grounded_cell(),
            model_metadata=grounded_metadata(),
        )
        case = {
            'id': 'case-1',
            'case_origin': 'forecast_publication',
            'status': 'reviewed',
            'priority': 5,
            'requires_two_reviewers': True,
            'forecast_run_id': '11111111-1111-1111-1111-111111111111',
            'region_key': 'great_himalaya',
            'cell_row': 4,
            'cell_col': 7,
            'cell_snapshot': {'evidence_replay': replay},
            'evidence': {},
        }
        case.update(overrides)
        return case

    def _reviews(self, **overrides):
        review = {
            'id': 'review-1',
            'case_id': 'case-1',
            'reviewer_id': 'scientist-1',
            'verdict': 'accepted',
            'claim_impact': 'no_change',
            'label_quality_verdict': 'label_reliable',
            'model_error_verdict': 'model_false_positive',
        }
        second = {**review, 'id': 'review-2', 'reviewer_id': 'scientist-2'}
        review.update(overrides)
        return [review, second]

    def test_reviewed_provenance_complete_consensus_is_shadow_only(self) -> None:
        decision = evaluate_reviewed_shadow_training_case(self._case(), self._reviews())

        self.assertTrue(decision.eligible)
        self.assertEqual(decision.candidate['training_status'], 'shadow_only')
        self.assertFalse(decision.candidate['production_eligible'])
        self.assertEqual(decision.candidate['feature_snapshot_sha256'], self._case()['cell_snapshot']['evidence_replay']['feature_snapshot_sha256'])

    def test_auto_label_or_reviewer_conflict_is_excluded(self) -> None:
        auto_label_case = self._case(evidence={'auto_label': {'source': 'sar_detection'}})
        auto_label_decision = evaluate_reviewed_shadow_training_case(auto_label_case, self._reviews())
        conflict_decision = evaluate_reviewed_shadow_training_case(
            self._case(),
            self._reviews(verdict='rejected'),
        )

        self.assertFalse(auto_label_decision.eligible)
        self.assertIn('auto_label_or_synthetic_signal_present', auto_label_decision.reasons)
        self.assertFalse(conflict_decision.eligible)
        self.assertIn('reviewer_verdict_conflict', conflict_decision.reasons)

    def test_candidate_pack_cannot_claim_production_eligibility(self) -> None:
        pack = build_shadow_training_candidate_pack([self._case()], self._reviews())

        self.assertEqual(pack['summary']['production_eligible_candidate_count'], 0)
        self.assertFalse(pack['candidates'][0]['production_eligible'])


class TestPublishedEvidenceCases(unittest.TestCase):
    def test_discrepancy_case_links_immutable_replay_to_forecast_run(self) -> None:
        cases = build_scientist_evidence_cases(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            region_name='Great Himalaya',
            forecast_date='2026-01-15',
            rows=[grounded_cell()],
            model_metadata=grounded_metadata(),
        )

        discrepancy = next(case for case in cases if case['case_type'] == 'verification_discrepancy')
        self.assertEqual(discrepancy['forecast_run_id'], '11111111-1111-1111-1111-111111111111')
        self.assertEqual(discrepancy['case_origin'], 'forecast_publication')
        self.assertEqual(discrepancy['cell_snapshot']['evidence_replay']['observed']['status'], 'available')


if __name__ == '__main__':
    unittest.main()
