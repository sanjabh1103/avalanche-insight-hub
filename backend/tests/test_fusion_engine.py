"""Tests for fusion_engine.py."""
from __future__ import annotations

import math
import unittest

from backend.common.fusion_engine import (
    SensorObservation,
    fuse_snow_depth,
    fuse_snow_cover,
    fuse_wet_snow,
    fuse_loading_rate,
    compute_consensus,
    fuse_observations,
    FRESH_THRESHOLD_H,
    STALE_THRESHOLD_H,
)


class TestSensorObservation(unittest.TestCase):
    def test_default_uncertainty(self):
        obs = SensorObservation(source='sar')
        self.assertGreater(obs.effective_uncertainty, 0)

    def test_custom_uncertainty(self):
        obs = SensorObservation(source='sar', uncertainty=0.05)
        self.assertAlmostEqual(obs.effective_uncertainty, 0.05)

    def test_freshness_weight_fresh(self):
        obs = SensorObservation(source='sar', freshness_hours=3.0)
        self.assertAlmostEqual(obs.freshness_weight, 1.0)

    def test_freshness_weight_stale(self):
        obs = SensorObservation(source='sar', freshness_hours=100.0)
        self.assertAlmostEqual(obs.freshness_weight, 0.5)

    def test_freshness_weight_midpoint(self):
        obs = SensorObservation(source='sar', freshness_hours=(FRESH_THRESHOLD_H + STALE_THRESHOLD_H) / 2)
        self.assertGreater(obs.freshness_weight, 0.5)
        self.assertLess(obs.freshness_weight, 1.0)

    def test_cloud_weight_non_optical(self):
        obs = SensorObservation(source='sar', cloud_cover=0.9)
        self.assertAlmostEqual(obs.cloud_weight, 1.0)

    def test_cloud_weight_optical_clear(self):
        obs = SensorObservation(source='optical', cloud_cover=0.0)
        self.assertAlmostEqual(obs.cloud_weight, 1.0)

    def test_cloud_weight_optical_cloudy(self):
        obs = SensorObservation(source='optical', cloud_cover=0.8)
        self.assertAlmostEqual(obs.cloud_weight, 0.1)

    def test_effective_weight_combines_factors(self):
        obs = SensorObservation(source='optical', uncertainty=0.1, freshness_hours=100.0, cloud_cover=0.5)
        w = obs.effective_weight
        self.assertLess(w, 1.0 / (0.1 * 0.1))  # less than pure inverse-variance


class TestFuseSnowDepth(unittest.TestCase):
    def test_no_observations(self):
        depth, unc = fuse_snow_depth([])
        self.assertIsNone(depth)
        self.assertIsNone(unc)

    def test_single_observation(self):
        obs = SensorObservation(source='sar', snow_depth_m=0.5, uncertainty=0.1)
        depth, unc = fuse_snow_depth([obs])
        self.assertAlmostEqual(depth, 0.5)
        self.assertAlmostEqual(unc, 0.1)

    def test_two_observations_equal_weight(self):
        obs1 = SensorObservation(source='sar', snow_depth_m=0.5, uncertainty=0.1)
        obs2 = SensorObservation(source='weather', snow_depth_m=0.7, uncertainty=0.1)
        depth, unc = fuse_snow_depth([obs1, obs2])
        self.assertAlmostEqual(depth, 0.6, places=2)
        self.assertLess(unc, 0.1)  # fused uncertainty < individual

    def test_two_observations_unequal_weight(self):
        obs1 = SensorObservation(source='sar', snow_depth_m=0.5, uncertainty=0.05)  # high weight
        obs2 = SensorObservation(source='gibs', snow_depth_m=1.0, uncertainty=0.25)  # low weight
        depth, unc = fuse_snow_depth([obs1, obs2])
        self.assertLess(depth, 0.75)  # pulled toward more certain sensor
        self.assertGreater(depth, 0.5)


class TestFuseSnowCover(unittest.TestCase):
    def test_no_observations(self):
        self.assertIsNone(fuse_snow_cover([]))

    def test_single(self):
        obs = SensorObservation(source='optical', snow_cover_fraction=0.8)
        self.assertAlmostEqual(fuse_snow_cover([obs]), 0.8)

    def test_multiple(self):
        obs1 = SensorObservation(source='optical', snow_cover_fraction=0.8, uncertainty=0.1)
        obs2 = SensorObservation(source='gibs', snow_cover_fraction=0.6, uncertainty=0.2)
        result = fuse_snow_cover([obs1, obs2])
        self.assertGreater(result, 0.6)
        self.assertLess(result, 0.8)


class TestConsensus(unittest.TestCase):
    def test_single_sensor_full_consensus(self):
        obs = SensorObservation(source='sar', snow_depth_m=0.5)
        self.assertAlmostEqual(compute_consensus([obs]), 1.0)

    def test_no_sensors_zero_consensus(self):
        self.assertAlmostEqual(compute_consensus([]), 0.0)

    def test_agreeing_sensors(self):
        obs1 = SensorObservation(source='sar', snow_depth_m=0.5, uncertainty=0.2)
        obs2 = SensorObservation(source='weather', snow_depth_m=0.55, uncertainty=0.2)
        self.assertGreater(compute_consensus([obs1, obs2]), 0.5)

    def test_disagreeing_sensors(self):
        obs1 = SensorObservation(source='sar', snow_depth_m=0.1, uncertainty=0.01)
        obs2 = SensorObservation(source='weather', snow_depth_m=2.0, uncertainty=0.01)
        self.assertAlmostEqual(compute_consensus([obs1, obs2]), 0.0)


class TestFuseObservations(unittest.TestCase):
    def setUp(self):
        import backend.common.fusion_engine as fe
        self._original_flag = fe.VERIFICATION_SPINE_ENABLED
        fe.VERIFICATION_SPINE_ENABLED = True

    def tearDown(self):
        import backend.common.fusion_engine as fe
        fe.VERIFICATION_SPINE_ENABLED = self._original_flag

    def test_empty_returns_default(self):
        fused = fuse_observations([])
        self.assertIsNone(fused.snow_depth_m)
        self.assertEqual(fused.consensus_score, 0.0)

    def test_full_fusion(self):
        observations = [
            SensorObservation(source='sar', snow_depth_m=0.5, uncertainty=0.1, freshness_hours=6.0),
            SensorObservation(source='weather', snow_depth_m=0.6, uncertainty=0.15, freshness_hours=3.0),
        ]
        fused = fuse_observations(observations)
        self.assertIsNotNone(fused.snow_depth_m)
        self.assertGreater(fused.consensus_score, 0.0)
        self.assertIn('sar', fused.contributing_sensors)
        self.assertIn('weather', fused.contributing_sensors)
        self.assertIn('Decision-support', fused.disclaimer)

    def test_disabled_flag_returns_empty(self):
        import backend.common.fusion_engine as fe
        original = fe.VERIFICATION_SPINE_ENABLED
        fe.VERIFICATION_SPINE_ENABLED = False
        try:
            fused = fuse_observations([
                SensorObservation(source='sar', snow_depth_m=0.5),
            ])
            self.assertIsNone(fused.snow_depth_m)
        finally:
            fe.VERIFICATION_SPINE_ENABLED = original


if __name__ == '__main__':
    unittest.main()
