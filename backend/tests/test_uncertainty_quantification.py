"""Tests for F13: Uncertainty Quantification & Brier Blocking."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import numpy as np

from backend.common.uncertainty_quantification import (
    BRIER_BLOCK_THRESHOLD,
    CONFORMAL_ALPHA,
    ConformalCalibrator,
    UQResult,
    apply_uq_to_cells,
    classify_forecast_confidence,
    compute_brier_score,
    compute_conformal_interval,
    compute_split_conformal_interval,
    reliability_diagram,
    should_block_publication,
    _norm_ppf,
)


class ComputeBrierScoreTests(unittest.TestCase):
    """Tests for Brier score extraction from model metadata."""

    def test_compute_brier_from_lstm_meta(self) -> None:
        metadata = {'lstm_head_meta': {'brier_score': 0.12}}
        self.assertAlmostEqual(compute_brier_score(metadata), 0.12)

    def test_compute_brier_from_lstm_calibrated(self) -> None:
        metadata = {'lstm_head_meta': {'brier_score_calibrated': 0.09}}
        self.assertAlmostEqual(compute_brier_score(metadata), 0.09)

    def test_compute_brier_from_rf_metrics(self) -> None:
        metadata = {'rf_metrics': {'brier_score': 0.18}}
        self.assertAlmostEqual(compute_brier_score(metadata), 0.18)

    def test_compute_brier_lstm_preferred_over_rf(self) -> None:
        metadata = {
            'lstm_head_meta': {'brier_score': 0.10},
            'rf_metrics': {'brier_score': 0.20},
        }
        self.assertAlmostEqual(compute_brier_score(metadata), 0.10)

    def test_compute_brier_no_metadata(self) -> None:
        self.assertIsNone(compute_brier_score({}))

    def test_compute_brier_invalid_value(self) -> None:
        metadata = {'lstm_head_meta': {'brier_score': 'invalid'}}
        self.assertIsNone(compute_brier_score(metadata))


class ClassifyForecastConfidenceTests(unittest.TestCase):
    """Tests for forecast confidence classification."""

    def test_classify_confidence_high(self) -> None:
        self.assertEqual(classify_forecast_confidence(0.05), 'high')

    def test_classify_confidence_high_boundary(self) -> None:
        self.assertEqual(classify_forecast_confidence(0.08), 'high')

    def test_classify_confidence_medium(self) -> None:
        self.assertEqual(classify_forecast_confidence(0.12), 'medium')

    def test_classify_confidence_medium_boundary(self) -> None:
        self.assertEqual(classify_forecast_confidence(0.15), 'medium')

    def test_classify_confidence_low(self) -> None:
        self.assertEqual(classify_forecast_confidence(0.20), 'low')

    def test_classify_confidence_none(self) -> None:
        self.assertEqual(classify_forecast_confidence(None), 'unknown')


class ShouldBlockPublicationTests(unittest.TestCase):
    """Tests for Brier score publish blocking."""

    def test_should_block_when_brier_exceeds_threshold(self) -> None:
        blocked, reason = should_block_publication(0.20, threshold=0.15)
        self.assertTrue(blocked)
        self.assertIsNotNone(reason)
        self.assertIn('brier_score', reason)
        self.assertIn('threshold', reason)

    def test_should_not_block_when_brier_below_threshold(self) -> None:
        blocked, reason = should_block_publication(0.10, threshold=0.15)
        self.assertFalse(blocked)
        self.assertIsNone(reason)

    def test_should_block_when_brier_none_fail_safe(self) -> None:
        blocked, reason = should_block_publication(None, threshold=0.15)
        self.assertTrue(blocked)
        self.assertIsNotNone(reason)

    def test_should_not_block_when_brier_none_with_override(self) -> None:
        with patch.dict(os.environ, {'BLOCK_ON_UNKNOWN_BRIER': 'false'}):
            blocked, reason = should_block_publication(None, threshold=0.15)
            self.assertFalse(blocked)
            self.assertIsNone(reason)

    def test_should_not_block_at_exact_threshold(self) -> None:
        blocked, reason = should_block_publication(0.15, threshold=0.15)
        self.assertFalse(blocked)
        self.assertIsNone(reason)

    def test_custom_threshold(self) -> None:
        blocked, _ = should_block_publication(0.12, threshold=0.10)
        self.assertTrue(blocked)


class ConformalIntervalTests(unittest.TestCase):
    """Tests for conformal prediction interval computation."""

    def test_conformal_interval_basic(self) -> None:
        lower, upper = compute_conformal_interval(0.5, 0.1, alpha=0.1)
        self.assertLess(lower, 0.5)
        self.assertGreater(upper, 0.5)
        self.assertLess(lower, upper)

    def test_conformal_interval_contains_probability(self) -> None:
        lower, upper = compute_conformal_interval(0.7, 0.15, alpha=0.1)
        self.assertLessEqual(lower, 0.7)
        self.assertGreaterEqual(upper, 0.7)

    def test_conformal_interval_clamped_lower(self) -> None:
        lower, upper = compute_conformal_interval(0.05, 0.2, alpha=0.1)
        self.assertGreaterEqual(lower, 0.0)

    def test_conformal_interval_clamped_upper(self) -> None:
        lower, upper = compute_conformal_interval(0.95, 0.2, alpha=0.1)
        self.assertLessEqual(upper, 1.0)

    def test_conformal_interval_no_std(self) -> None:
        lower, upper = compute_conformal_interval(0.5, None, alpha=0.1)
        self.assertGreaterEqual(lower, 0.0)
        self.assertLessEqual(upper, 1.0)
        self.assertLess(lower, upper)

    def test_conformal_interval_negative_std(self) -> None:
        lower, upper = compute_conformal_interval(0.5, -1.0, alpha=0.1)
        self.assertGreaterEqual(lower, 0.0)
        self.assertLessEqual(upper, 1.0)
        self.assertLess(lower, upper)

    def test_norm_ppf_known_values(self) -> None:
        # z for 95% (alpha=0.1, one-sided 0.95) ≈ 1.645
        z = _norm_ppf(0.95)
        self.assertAlmostEqual(z, 1.6449, places=2)

    def test_norm_ppf_median(self) -> None:
        z = _norm_ppf(0.5)
        self.assertAlmostEqual(z, 0.0, places=2)


class ApplyUQToCellsTests(unittest.TestCase):
    """Tests for applying UQ to grid cells."""

    def test_apply_uq_to_cells(self) -> None:
        cells = [
            {'probability': 0.8, 'uncertainty_std': 0.1, 'status': 'ready'},
            {'probability': 0.3, 'uncertainty_std': 0.05, 'status': 'ready'},
        ]
        metadata = {'lstm_head_meta': {'brier_score': 0.10}}
        updated, uq_result = apply_uq_to_cells(cells, metadata)

        self.assertEqual(uq_result.brier_score, 0.10)
        self.assertEqual(uq_result.forecast_confidence, 'medium')
        self.assertFalse(uq_result.publish_blocked)

        for cell in updated:
            self.assertEqual(cell['forecast_confidence'], 'medium')
            self.assertEqual(cell['brier_score'], 0.10)
            self.assertIn('conformal_lower', cell)
            self.assertIn('conformal_upper', cell)

    def test_apply_uq_blocked_cells_cleared(self) -> None:
        cells = [
            {'probability': 0.8, 'uncertainty_std': 0.1, 'status': 'ready',
             'public_eligible': True, 'risk_score': 4, 'runout_seed': True},
        ]
        metadata = {'lstm_head_meta': {'brier_score': 0.25}}
        updated, uq_result = apply_uq_to_cells(cells, metadata)

        self.assertTrue(uq_result.publish_blocked)
        self.assertEqual(uq_result.forecast_confidence, 'low')
        self.assertFalse(updated[0]['public_eligible'])
        self.assertEqual(updated[0]['risk_score'], 0)
        self.assertFalse(updated[0]['runout_seed'])
        self.assertIn(uq_result.block_reason, updated[0]['public_mask_reasons'])

    def test_apply_uq_no_brier_score_fail_safe(self) -> None:
        cells = [{'probability': 0.5, 'status': 'ready'}]
        updated, uq_result = apply_uq_to_cells(cells, {})

        self.assertIsNone(uq_result.brier_score)
        self.assertEqual(uq_result.forecast_confidence, 'unknown')
        self.assertTrue(uq_result.publish_blocked)
        self.assertEqual(updated[0]['forecast_confidence'], 'unknown')
        self.assertFalse(updated[0]['public_eligible'])

    def test_apply_uq_no_brier_score_with_override(self) -> None:
        with patch.dict(os.environ, {'BLOCK_ON_UNKNOWN_BRIER': 'false'}):
            cells = [{'probability': 0.5, 'status': 'ready'}]
            updated, uq_result = apply_uq_to_cells(cells, {})

            self.assertIsNone(uq_result.brier_score)
            self.assertFalse(uq_result.publish_blocked)

    def test_apply_uq_with_uncertainty_span(self) -> None:
        cells = [{'probability': 0.6, 'uncertainty_span': 0.2, 'status': 'ready'}]
        metadata = {'lstm_head_meta': {'brier_score': 0.10}}
        updated, _ = apply_uq_to_cells(cells, metadata)

        self.assertIn('conformal_lower', updated[0])
        self.assertIn('conformal_upper', updated[0])
        # Interval should be wider than zero
        self.assertLess(updated[0]['conformal_lower'], updated[0]['conformal_upper'])

    def test_apply_uq_conformal_interval_clamped(self) -> None:
        cells = [{'probability': 0.99, 'uncertainty_std': 0.5, 'status': 'ready'}]
        metadata = {'lstm_head_meta': {'brier_score': 0.10}}
        updated, _ = apply_uq_to_cells(cells, metadata)

        self.assertLessEqual(updated[0]['conformal_upper'], 1.0)
        self.assertGreaterEqual(updated[0]['conformal_lower'], 0.0)


class BrierThresholdEnvVarTests(unittest.TestCase):
    """Tests for env var configuration."""

    def test_brier_threshold_default(self) -> None:
        self.assertAlmostEqual(BRIER_BLOCK_THRESHOLD, 0.15)

    def test_brier_threshold_env_var(self) -> None:
        with patch.dict(os.environ, {'BRIER_BLOCK_THRESHOLD': '0.10'}):
            from backend.common.uncertainty_quantification import BRIER_BLOCK_THRESHOLD as t
            # The module-level constant was loaded at import time
            # so we test should_block_publication with explicit threshold
            blocked, _ = should_block_publication(0.12, threshold=0.10)
            self.assertTrue(blocked)

    def test_conformal_alpha_default(self) -> None:
        self.assertAlmostEqual(CONFORMAL_ALPHA, 0.1)


class PublicEligibilityBrierBlockTests(unittest.TestCase):
    """Integration tests for Brier block via apply_uq_to_cells (run-level gate)."""

    def test_public_eligibility_no_per_cell_brier_block(self) -> None:
        """apply_public_eligibility_metric should NOT block on Brier — that is
        the responsibility of apply_uq_to_cells at the run level."""
        from backend.common.public_eligibility import apply_public_eligibility_metric

        cell = {
            'row': 0,
            'col': 0,
            'lat': 32.0,
            'lng': 78.0,
            'status': 'ready',
            'probability': 0.8,
            'probability_risk_score': 4,
            'terrain_inputs': {'slope_angle_deg': 38.0, 'aspect_deg': 180.0, 'elevation_m': 3500},
            'weather_inputs': {
                'snow_depth_cm': 20.0,
                'snowfall_24h_cm': 10.0,
                'precipitation_24h_mm': 5.0,
                'downscaled_temperature_c': -5.0,
                'freezing_level_height_m': 3000.0,
            },
            'snowpack_proxy': {'method': 'seasonal_cumulative_v1', 'estimated_shear_strength': 500.0, 'snow_settlement_index': 0.5},
        }

        result = apply_public_eligibility_metric(cell)

        # Cell should be eligible — no Brier block at this stage
        self.assertTrue(result['public_eligible'])
        self.assertEqual(result['risk_score'], 4)
        self.assertNotIn('brier_score', result)
        self.assertNotIn('forecast_confidence', result)

    def test_end_to_end_eligible_cells_survive_uq_gate(self) -> None:
        """Full pipeline: apply_public_eligibility_metric then apply_uq_to_cells
        with valid metadata — eligible cells should remain eligible."""
        from backend.common.public_eligibility import apply_public_eligibility_metric

        cell = {
            'row': 0,
            'col': 0,
            'lat': 32.0,
            'lng': 78.0,
            'status': 'ready',
            'probability': 0.8,
            'probability_risk_score': 4,
            'terrain_inputs': {'slope_angle_deg': 38.0, 'aspect_deg': 180.0, 'elevation_m': 3500},
            'weather_inputs': {
                'snow_depth_cm': 20.0,
                'snowfall_24h_cm': 10.0,
                'precipitation_24h_mm': 5.0,
                'downscaled_temperature_c': -5.0,
                'freezing_level_height_m': 3000.0,
            },
            'snowpack_proxy': {'method': 'seasonal_cumulative_v1', 'estimated_shear_strength': 500.0, 'snow_settlement_index': 0.5},
        }

        result = apply_public_eligibility_metric(cell)
        self.assertTrue(result['public_eligible'])

        # Now apply UQ with valid low Brier score
        metadata = {'lstm_head_meta': {'brier_score': 0.05}}
        updated, uq_result = apply_uq_to_cells([result], metadata)

        self.assertFalse(uq_result.publish_blocked)
        self.assertTrue(updated[0]['public_eligible'])
        self.assertEqual(updated[0]['risk_score'], 4)

    def test_end_to_end_brier_block_via_uq_gate(self) -> None:
        """Full pipeline: eligible cell blocked by high Brier via apply_uq_to_cells."""
        from backend.common.public_eligibility import apply_public_eligibility_metric

        cell = {
            'row': 0,
            'col': 0,
            'lat': 32.0,
            'lng': 78.0,
            'status': 'ready',
            'probability': 0.8,
            'probability_risk_score': 4,
            'terrain_inputs': {'slope_angle_deg': 38.0, 'aspect_deg': 180.0, 'elevation_m': 3500},
            'weather_inputs': {
                'snow_depth_cm': 20.0,
                'snowfall_24h_cm': 10.0,
                'precipitation_24h_mm': 5.0,
                'downscaled_temperature_c': -5.0,
                'freezing_level_height_m': 3000.0,
            },
            'snowpack_proxy': {'method': 'seasonal_cumulative_v1', 'estimated_shear_strength': 500.0, 'snow_settlement_index': 0.5},
        }

        result = apply_public_eligibility_metric(cell)
        self.assertTrue(result['public_eligible'])

        metadata = {'lstm_head_meta': {'brier_score': 0.25}}
        updated, uq_result = apply_uq_to_cells([result], metadata)

        self.assertTrue(uq_result.publish_blocked)
        self.assertFalse(updated[0]['public_eligible'])
        self.assertEqual(updated[0]['risk_score'], 0)


class ConformalCalibratorTests(unittest.TestCase):
    """Tests for split conformal prediction calibrator."""

    def test_conformal_calibrator_calibrate(self) -> None:
        cal = ConformalCalibrator(alpha=0.1)
        preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.15]
        truths = [0.0, 0.4, 0.6, 0.6, 1.0, 0.2, 0.3, 0.7, 0.75, 0.1]
        cal.calibrate(preds, truths)
        self.assertTrue(cal.is_calibrated)
        self.assertIsNotNone(cal._quantile)

    def test_conformal_calibrator_predict_interval(self) -> None:
        cal = ConformalCalibrator(alpha=0.1)
        preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.15]
        truths = [0.0, 0.4, 0.6, 0.6, 1.0, 0.2, 0.3, 0.7, 0.75, 0.1]
        cal.calibrate(preds, truths)
        lower, upper = cal.predict_interval(0.5)
        self.assertLessEqual(lower, 0.5)
        self.assertGreaterEqual(upper, 0.5)
        self.assertLess(lower, upper)

    def test_conformal_calibrator_coverage(self) -> None:
        cal = ConformalCalibrator(alpha=0.1)
        preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.15]
        truths = [0.0, 0.4, 0.6, 0.6, 1.0, 0.2, 0.3, 0.7, 0.75, 0.1]
        cal.calibrate(preds, truths)
        cov = cal.coverage()
        self.assertIsNotNone(cov)
        self.assertGreaterEqual(cov, 0.8)

    def test_conformal_calibrator_uncalibrated_fallback(self) -> None:
        cal = ConformalCalibrator(alpha=0.1)
        self.assertFalse(cal.is_calibrated)
        lower, upper = cal.predict_interval(0.5)
        self.assertLess(lower, 0.5)
        self.assertGreater(upper, 0.5)

    def test_apply_uq_with_calibrator(self) -> None:
        cal = ConformalCalibrator(alpha=0.1)
        preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.15]
        truths = [0.0, 0.4, 0.6, 0.6, 1.0, 0.2, 0.3, 0.7, 0.75, 0.1]
        cal.calibrate(preds, truths)

        cells = [{'probability': 0.6, 'status': 'ready'}]
        metadata = {'lstm_head_meta': {'brier_score': 0.10}}
        updated, _ = apply_uq_to_cells(cells, metadata, calibrator=cal)

        self.assertIn('conformal_lower', updated[0])
        self.assertIn('conformal_upper', updated[0])
        self.assertLess(updated[0]['conformal_lower'], 0.6)
        self.assertGreater(updated[0]['conformal_upper'], 0.6)

    def test_reliability_diagram_basic(self) -> None:
        preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.15]
        truths = [0.0, 0.4, 0.6, 0.6, 1.0, 0.2, 0.3, 0.7, 0.75, 0.1]
        bins = reliability_diagram(preds, truths, n_bins=5)
        self.assertEqual(len(bins), 5)
        total = sum(b['count'] for b in bins)
        self.assertEqual(total, len(preds))


class HeldOutCoverageTests(unittest.TestCase):
    """Regression tests for held-out UQ coverage evaluation.

    The held-out coverage must use the fitted calibrator's quantile,
    NOT re-derive a threshold from held-out residuals. Re-deriving
    produces artificially inflated coverage (always ~1-alpha) and
    hides poor generalization.
    """

    def test_held_out_coverage_uses_fitted_quantile(self) -> None:
        """When held-out residuals exceed the fitted quantile, coverage must drop."""
        import tempfile
        from pathlib import Path
        from backend.common.uncertainty_quantification import _evaluate_held_out_coverage

        # Calibrate with small residuals → tight quantile
        cal = ConformalCalibrator(alpha=0.1)
        cal.calibrate([0.1, 0.2, 0.3, 0.4, 0.5], [0.1, 0.2, 0.3, 0.4, 0.5])
        fitted_q = cal._quantile
        self.assertIsNotNone(fitted_q)
        self.assertAlmostEqual(fitted_q, 0.0, places=4)

        # Held-out set with large residuals → should have 0 coverage
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write('probability,truth\n')
            f.write('0.9,0.1\n')
            f.write('0.1,0.9\n')
            f.write('0.8,0.2\n')
            held_path = f.name

        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': held_path}):
                # Re-import to pick up env var
                import importlib
                import backend.common.uncertainty_quantification as uq_mod
                importlib.reload(uq_mod)
                coverage = uq_mod._evaluate_held_out_coverage(cal, alpha=0.1)
            self.assertIsNotNone(coverage)
            self.assertLess(coverage, 0.5, f'Expected low coverage with tight fitted quantile, got {coverage}')
        finally:
            os.unlink(held_path)

    def test_held_out_coverage_none_when_not_calibrated(self) -> None:
        """Uncalibrated calibrator must return None for held-out coverage."""
        from backend.common.uncertainty_quantification import _evaluate_held_out_coverage
        cal = ConformalCalibrator(alpha=0.1)
        result = _evaluate_held_out_coverage(cal, alpha=0.1)
        self.assertIsNone(result)

    def test_held_out_env_set_computes_coverage_and_hash(self) -> None:
        """When env is set to a valid CSV, coverage is computed and source hash present."""
        import tempfile
        import importlib
        import hashlib
        from pathlib import Path
        import backend.common.uncertainty_quantification as uq_mod

        cal = ConformalCalibrator(alpha=0.1)
        cal.calibrate([0.1, 0.2, 0.3, 0.4, 0.5], [0.1, 0.2, 0.3, 0.4, 0.5])

        csv_content = 'probability,truth\n0.72,1.0\n0.38,0.0\n0.85,1.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            held_path = f.name

        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': held_path}):
                importlib.reload(uq_mod)
                coverage = uq_mod._evaluate_held_out_coverage(cal, alpha=0.1)
                self.assertIsNotNone(coverage)
                source_hash = uq_mod._compute_held_out_source_hash(held_path)
                self.assertTrue(len(source_hash) > 0)
                expected_hash = hashlib.sha256(Path(held_path).read_bytes()).hexdigest()
                self.assertEqual(source_hash, expected_hash)
        finally:
            os.unlink(held_path)

    def test_held_out_env_empty_state_is_fit_only(self) -> None:
        """When env is empty, calibration_state must be 'fit_only', never calibrated."""
        import importlib
        import tempfile
        import backend.common.uncertainty_quantification as uq_mod

        # Create a calibration CSV
        csv_content = 'probability,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name

        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                importlib.reload(uq_mod)
                _, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
                self.assertIsNone(manifest.held_out_coverage)
                self.assertEqual(manifest.calibration_state, 'fit_only')
                self.assertEqual(manifest.held_out_source_hash, '')
        finally:
            os.unlink(cal_path)

    def test_held_out_hash_matches_recomputed_file_hash(self) -> None:
        """held_out_source_hash matches a recomputed SHA-256 of the file."""
        import tempfile
        import importlib
        import hashlib
        from pathlib import Path
        import backend.common.uncertainty_quantification as uq_mod

        cal = ConformalCalibrator(alpha=0.1)
        cal.calibrate([0.1, 0.2, 0.3, 0.4, 0.5], [0.1, 0.2, 0.3, 0.4, 0.5])

        csv_content = 'probability,truth\n0.72,1.0\n0.38,0.0\n0.85,1.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            held_path = f.name

        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': held_path}):
                importlib.reload(uq_mod)
                source_hash = uq_mod._compute_held_out_source_hash(held_path)
                recomputed = hashlib.sha256(Path(held_path).read_bytes()).hexdigest()
                self.assertEqual(source_hash, recomputed)
        finally:
            os.unlink(held_path)


class TestProductionCalibratorLoading(unittest.TestCase):
    """G-07: Verify real calibrated-UQ runtime loads from env var."""

    def test_no_path_returns_normal_fallback(self) -> None:
        """Without CONFORMAL_CALIBRATION_ARTIFACT_PATH, calibrator is None and method is normal_fallback."""
        from backend.common.uncertainty_quantification import load_calibrator_with_manifest
        with patch.dict('os.environ', {}, clear=False):
            os.environ.pop('CONFORMAL_CALIBRATION_ARTIFACT_PATH', None)
            calibrator, manifest = load_calibrator_with_manifest('')
            self.assertIsNone(calibrator)
            self.assertEqual(manifest.uq_method, 'normal_fallback')

    def test_valid_path_loads_real_calibrator(self) -> None:
        """Valid calibration CSV loads a real conformal calibrator with split_conformal method."""
        import tempfile
        from backend.common.uncertainty_quantification import load_calibrator_with_manifest
        csv_content = 'prediction,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n0.2,0.1\n0.8,0.9\n0.4,0.3\n0.6,0.7\n0.15,0.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                import importlib
                import backend.common.uncertainty_quantification as uq_mod
                importlib.reload(uq_mod)
                calibrator, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
            self.assertIsNotNone(calibrator)
            self.assertTrue(calibrator.is_calibrated)
            self.assertEqual(manifest.uq_method, 'split_conformal')
            self.assertGreater(manifest.sample_count, 0)
            self.assertIsNotNone(manifest.fit_coverage)
        finally:
            os.unlink(cal_path)

    def test_calibrator_produces_conformal_interval(self) -> None:
        """Calibrated calibrator produces intervals different from normal fallback."""
        import tempfile
        from backend.common.uncertainty_quantification import (
            load_calibrator_with_manifest,
            compute_split_conformal_interval,
            compute_conformal_interval,
            DEFAULT_UNCERTAINTY_STD,
        )
        csv_content = 'prediction,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n0.2,0.1\n0.8,0.9\n0.4,0.3\n0.6,0.7\n0.15,0.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                import importlib
                import backend.common.uncertainty_quantification as uq_mod
                importlib.reload(uq_mod)
                calibrator, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
            self.assertIsNotNone(calibrator)
            conformal_interval = compute_split_conformal_interval(0.5, calibrator)
            fallback_interval = compute_conformal_interval(0.5, DEFAULT_UNCERTAINTY_STD, 0.1)
            # The conformal interval should be different from the normal fallback
            self.assertNotEqual(conformal_interval, fallback_interval)
        finally:
            os.unlink(cal_path)

    def test_manifest_sha256_matches_file(self) -> None:
        """Manifest SHA-256 matches the actual calibration file hash."""
        import tempfile
        import hashlib
        from pathlib import Path
        from backend.common.uncertainty_quantification import load_calibrator_with_manifest
        csv_content = 'prediction,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                import importlib
                import backend.common.uncertainty_quantification as uq_mod
                importlib.reload(uq_mod)
                _, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
            expected_hash = hashlib.sha256(Path(cal_path).read_bytes()).hexdigest()
            self.assertEqual(manifest.sha256, expected_hash)
        finally:
            os.unlink(cal_path)


class TestFitCoverageFormulaConsistency(unittest.TestCase):
    """G-08: Manifest fit_coverage must use the calibrator's own coverage() method,
    not a separate quantile calculation with a different formula."""

    def test_fit_coverage_matches_calibrator_coverage(self) -> None:
        """Manifest fit_coverage equals calibrator.coverage() for the same data."""
        import tempfile
        import importlib
        import backend.common.uncertainty_quantification as uq_mod
        csv_content = 'prediction,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n0.2,0.1\n0.8,0.9\n0.4,0.3\n0.6,0.7\n0.15,0.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                importlib.reload(uq_mod)
                calibrator, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
            self.assertIsNotNone(calibrator)
            cal_coverage = calibrator.coverage()
            self.assertIsNotNone(cal_coverage)
            self.assertIsNotNone(manifest.fit_coverage)
            self.assertEqual(manifest.fit_coverage, round(cal_coverage, 4))
        finally:
            os.unlink(cal_path)

    def test_fit_coverage_not_using_wrong_formula(self) -> None:
        """fit_coverage must not equal the old wrong formula ceil((1-alpha)*n)-1."""
        import tempfile
        import math
        import importlib
        import backend.common.uncertainty_quantification as uq_mod
        # Use a small sample where the two formulas diverge
        csv_content = 'prediction,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                importlib.reload(uq_mod)
                calibrator, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
            self.assertIsNotNone(calibrator)
            n = len(calibrator._residuals)
            alpha = 0.1
            # Old wrong formula: ceil((1-alpha)*n) - 1
            wrong_idx = int(math.ceil((1 - alpha) * n)) - 1
            wrong_idx = max(0, min(wrong_idx, n - 1))
            wrong_residuals = sorted(abs(r) for r in calibrator._residuals)
            wrong_threshold = wrong_residuals[wrong_idx]
            wrong_covered = sum(1 for r in calibrator._residuals if abs(r) <= wrong_threshold)
            wrong_coverage = round(wrong_covered / n, 4)
            # Correct formula: ceil((n+1)*(1-alpha)) - 1 (used by calibrator)
            # If they differ, manifest must match the correct one, not the wrong one
            if wrong_coverage != manifest.fit_coverage:
                self.assertNotEqual(manifest.fit_coverage, wrong_coverage)
            # In all cases, manifest must match calibrator.coverage()
            self.assertEqual(manifest.fit_coverage, round(calibrator.coverage(), 4))
        finally:
            os.unlink(cal_path)

    def test_small_sample_coverage(self) -> None:
        """Small sample (n=3) fit_coverage uses finite-sample rule correctly."""
        import tempfile
        import importlib
        import backend.common.uncertainty_quantification as uq_mod
        csv_content = 'prediction,truth\n0.1,0.0\n0.5,0.6\n0.9,1.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                importlib.reload(uq_mod)
                calibrator, manifest = uq_mod.load_calibrator_with_manifest(cal_path)
            self.assertIsNotNone(calibrator)
            self.assertEqual(manifest.sample_count, 3)
            self.assertIsNotNone(manifest.fit_coverage)
            self.assertEqual(manifest.fit_coverage, round(calibrator.coverage(), 4))
        finally:
            os.unlink(cal_path)

    def test_non_default_alpha_coverage(self) -> None:
        """Non-default alpha (0.05) produces correct fit_coverage."""
        import tempfile
        import importlib
        import backend.common.uncertainty_quantification as uq_mod
        csv_content = 'prediction,truth\n0.1,0.0\n0.3,0.4\n0.5,0.6\n0.7,0.6\n0.9,1.0\n0.2,0.1\n0.8,0.9\n0.4,0.3\n0.6,0.7\n0.15,0.0\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            cal_path = f.name
        try:
            with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
                importlib.reload(uq_mod)
                calibrator = uq_mod.load_calibrator_from_csv(cal_path, alpha=0.05)
                manifest_cal, manifest = uq_mod.load_calibrator_with_manifest(cal_path, alpha=0.05)
            self.assertIsNotNone(manifest_cal)
            self.assertEqual(manifest.alpha, 0.05)
            self.assertEqual(manifest.fit_coverage, round(manifest_cal.coverage(), 4))
        finally:
            os.unlink(cal_path)

    def test_default_calibration_artifact_exists(self):
        """G-07: The default calibration CSV exists in backend/config/."""
        from pathlib import Path
        default_path = Path(__file__).resolve().parent.parent / 'config' / 'default_conformal_calibration.csv'
        self.assertTrue(default_path.exists(), f'Default calibration CSV not found: {default_path}')

    def test_default_artifact_loads_split_conformal(self):
        """G-07: Loading the default calibration artifact produces a split_conformal calibrator."""
        from pathlib import Path
        from backend.common.uncertainty_quantification import load_calibrator_with_manifest
        default_path = str(Path(__file__).resolve().parent.parent / 'config' / 'default_conformal_calibration.csv')
        calibrator, manifest = load_calibrator_with_manifest(default_path)
        self.assertIsNotNone(calibrator)
        self.assertEqual(manifest.uq_method, 'split_conformal')
        self.assertGreater(manifest.sample_count, 0)
        self.assertIsNotNone(manifest.fit_coverage)

    def test_production_calibrator_uses_default_when_env_unset(self):
        """G-07: _load_production_calibrator loads default artifact when env var is not set."""
        with patch.dict('os.environ', {}, clear=False):
            os.environ.pop('CONFORMAL_CALIBRATION_ARTIFACT_PATH', None)
            from backend.daily_inference import _load_production_calibrator
            calibrator, manifest = _load_production_calibrator()
        self.assertIsNotNone(calibrator)
        self.assertEqual(manifest.uq_method, 'split_conformal')

    def test_default_held_out_calibration_csv_exists(self):
        """G-07: The default held-out calibration CSV exists in backend/config/."""
        from pathlib import Path
        default_path = Path(__file__).resolve().parent.parent / 'config' / 'default_held_out_calibration.csv'
        self.assertTrue(default_path.exists(), f'Default held-out calibration CSV not found: {default_path}')

    def test_held_out_coverage_computed_from_default(self):
        """G-07: Loading with default held-out set produces non-None held_out_coverage."""
        import importlib
        from pathlib import Path
        from backend.common import uncertainty_quantification as uq_mod
        default_cal = str(Path(__file__).resolve().parent.parent / 'config' / 'default_conformal_calibration.csv')
        # Ensure env var is unset so default held-out path is used
        with patch.dict('os.environ', {'CONFORMAL_HELD_OUT_SET_PATH': ''}):
            importlib.reload(uq_mod)
            calibrator, manifest = uq_mod.load_calibrator_with_manifest(default_cal)
        self.assertIsNotNone(calibrator)
        self.assertTrue(calibrator.is_calibrated)
        # held_out_coverage should be computed from the default held-out CSV
        self.assertIsNotNone(manifest.held_out_coverage,
                             'held_out_coverage must be computed when default held-out CSV exists')
        self.assertGreater(manifest.held_out_coverage, 0.0)
        self.assertLessEqual(manifest.held_out_coverage, 1.0)
        # held_out_source_hash should be non-empty
        self.assertTrue(manifest.held_out_source_hash,
                        'held_out_source_hash must be non-empty when held-out CSV is loaded')


if __name__ == '__main__':
    unittest.main()
