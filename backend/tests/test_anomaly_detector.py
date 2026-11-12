"""Tests for anomaly_detector.py."""
from __future__ import annotations

import unittest

from backend.common.anomaly_detector import (
    SensorReading,
    AnomalyFlag,
    detect_anomalies,
    detect_sar_loading_optical_bare,
    detect_optical_snow_sar_dry,
    detect_weather_snow_no_snowcover,
    detect_rapid_loading,
    detect_rapid_melt,
    attribute_discrepancy,
    compute_severity,
    determine_anomaly_state,
    cluster_anomaly_zones,
    DISCREPANCY_SAR_LOADING_OPTICAL_BARE,
    DISCREPANCY_OPTICAL_SNOW_SAR_DRY,
    DISCREPANCY_WEATHER_SNOW_NO_SNOWCOVER,
    DISCREPANCY_RAPID_LOADING_ANOMALY,
    DISCREPANCY_RAPID_MELT_ANOMALY,
    ATTRIBUTION_FORCING_ERROR,
    ATTRIBUTION_SENSING_GAP,
    ATTRIBUTION_THRESHOLD_MISCALIBRATION,
    ATTRIBUTION_UNATTRIBUTED,
    ANOMALY_NORMAL,
    ANOMALY_WATCH,
    ANOMALY_ANOMALY,
    ANOMALY_UNVERIFIED,
)
from backend.common.verification_contracts import EvidencePacket


class TestDiscrepancyDetection(unittest.TestCase):
    def test_sar_loading_optical_bare_detected(self):
        sar = SensorReading(source='sar', loading_rate_24h=0.1)
        optical = SensorReading(source='optical', snow_cover_fraction=0.05)
        self.assertTrue(detect_sar_loading_optical_bare(sar, optical))

    def test_sar_loading_optical_bare_not_detected(self):
        sar = SensorReading(source='sar', loading_rate_24h=0.01)
        optical = SensorReading(source='optical', snow_cover_fraction=0.5)
        self.assertFalse(detect_sar_loading_optical_bare(sar, optical))

    def test_optical_snow_sar_dry_detected(self):
        optical = SensorReading(source='optical', snow_cover_fraction=0.8)
        sar = SensorReading(source='sar', wet_snow_fraction=0.05)
        self.assertTrue(detect_optical_snow_sar_dry(optical, sar))

    def test_weather_snow_no_snowcover_detected(self):
        self.assertTrue(detect_weather_snow_no_snowcover(10.0, 0.05))
        self.assertFalse(detect_weather_snow_no_snowcover(2.0, 0.05))
        self.assertFalse(detect_weather_snow_no_snowcover(10.0, 0.5))

    def test_rapid_loading_detected(self):
        self.assertTrue(detect_rapid_loading(50.0, 20.0))
        self.assertFalse(detect_rapid_loading(10.0, 20.0))

    def test_rapid_melt_detected(self):
        self.assertTrue(detect_rapid_melt(25.0, -10.0))
        self.assertFalse(detect_rapid_melt(10.0, -10.0))


class TestAttribution(unittest.TestCase):
    def test_weather_snow_stale_weather(self):
        evidence = EvidencePacket(cell_id='c')
        attr = attribute_discrepancy(
            DISCREPANCY_WEATHER_SNOW_NO_SNOWCOVER, evidence,
            weather_fresh=False, sar_fresh=True, optical_fresh=True,
        )
        self.assertEqual(attr.bucket, ATTRIBUTION_FORCING_ERROR)

    def test_weather_snow_fresh_weather(self):
        evidence = EvidencePacket(cell_id='c')
        attr = attribute_discrepancy(
            DISCREPANCY_WEATHER_SNOW_NO_SNOWCOVER, evidence,
            weather_fresh=True, sar_fresh=True, optical_fresh=True,
        )
        self.assertEqual(attr.bucket, ATTRIBUTION_SENSING_GAP)

    def test_sar_optical_both_stale(self):
        evidence = EvidencePacket(cell_id='c')
        attr = attribute_discrepancy(
            DISCREPANCY_SAR_LOADING_OPTICAL_BARE, evidence,
            weather_fresh=True, sar_fresh=False, optical_fresh=False,
        )
        self.assertEqual(attr.bucket, ATTRIBUTION_SENSING_GAP)

    def test_sar_optical_both_fresh(self):
        evidence = EvidencePacket(cell_id='c')
        attr = attribute_discrepancy(
            DISCREPANCY_SAR_LOADING_OPTICAL_BARE, evidence,
            weather_fresh=True, sar_fresh=True, optical_fresh=True,
        )
        self.assertEqual(attr.bucket, ATTRIBUTION_THRESHOLD_MISCALIBRATION)

    def test_rapid_loading_synthetic_physics(self):
        evidence = EvidencePacket(cell_id='c')
        attr = attribute_discrepancy(
            DISCREPANCY_RAPID_LOADING_ANOMALY, evidence,
            physics_method='synthetic_heuristic',
        )
        self.assertEqual(attr.bucket, 'physics_model_bias')

    def test_unattributed_fallback(self):
        evidence = EvidencePacket(cell_id='c')
        attr = attribute_discrepancy('bogus_type', evidence)
        self.assertEqual(attr.bucket, ATTRIBUTION_UNATTRIBUTED)


class TestSeverityAndState(unittest.TestCase):
    def test_severity_with_high_zscore(self):
        sev = compute_severity(3.0, 3)
        self.assertGreater(sev, 0.5)

    def test_severity_with_no_sources(self):
        sev = compute_severity(3.0, 0)
        self.assertLess(sev, 0.5)

    def test_anomaly_state_normal(self):
        self.assertEqual(determine_anomaly_state(None, 0, False), ANOMALY_UNVERIFIED)
        self.assertEqual(determine_anomaly_state(0.5, 1, False), ANOMALY_NORMAL)

    def test_anomaly_state_watch(self):
        self.assertEqual(determine_anomaly_state(1.5, 2, True), ANOMALY_WATCH)

    def test_anomaly_state_anomaly(self):
        self.assertEqual(determine_anomaly_state(3.0, 3, True), ANOMALY_ANOMALY)


class TestDetectAnomalies(unittest.TestCase):
    def setUp(self):
        import backend.common.anomaly_detector as ad
        self._original_flag = ad.VERIFICATION_SPINE_ENABLED
        ad.VERIFICATION_SPINE_ENABLED = True

    def tearDown(self):
        import backend.common.anomaly_detector as ad
        ad.VERIFICATION_SPINE_ENABLED = self._original_flag

    def test_no_readings_returns_unverified(self):
        flags, packet = detect_anomalies('cell_0', 'colorado_rockies', {})
        self.assertEqual(len(flags), 0)
        self.assertEqual(packet.anomaly_state, ANOMALY_UNVERIFIED)

    def test_weather_snow_no_snowcover_flag(self):
        readings = {
            'weather': SensorReading(source='weather', freshness_hours=3.0),
            'optical': SensorReading(source='optical', snow_cover_fraction=0.05, freshness_hours=6.0),
            'gibs': SensorReading(source='gibs', snow_cover_fraction=0.04, freshness_hours=24.0),
        }
        flags, packet = detect_anomalies(
            'cell_0', 'colorado_rockies', readings,
            weather_snowfall_cm=15.0,
        )
        self.assertTrue(any(f.discrepancy_type == DISCREPANCY_WEATHER_SNOW_NO_SNOWCOVER for f in flags))
        self.assertNotEqual(packet.anomaly_state, ANOMALY_NORMAL)

    def test_sar_loading_optical_bare_flag(self):
        readings = {
            'sar': SensorReading(source='sar', loading_rate_24h=0.1, freshness_hours=12.0),
            'optical': SensorReading(source='optical', snow_cover_fraction=0.03, freshness_hours=6.0),
            'weather': SensorReading(source='weather', snow_depth_m=0.5, freshness_hours=3.0),
        }
        flags, packet = detect_anomalies('cell_0', 'colorado_rockies', readings)
        self.assertTrue(any(f.discrepancy_type == DISCREPANCY_SAR_LOADING_OPTICAL_BARE for f in flags))

    def test_two_sources_remain_unflagged_until_independent_third_source(self):
        readings = {
            'sar': SensorReading(source='sar', loading_rate_24h=0.1, freshness_hours=12.0),
            'optical': SensorReading(source='optical', snow_cover_fraction=0.03, freshness_hours=6.0),
        }
        flags, packet = detect_anomalies('cell_0', 'colorado_rockies', readings)
        self.assertFalse(flags)
        self.assertFalse(packet.data_quality['minimum_sources_satisfied'])

    def test_packet_has_disclaimer(self):
        _, packet = detect_anomalies('cell_0', 'r', {})
        self.assertIn('Decision-support', packet.disclaimer)


class TestClusterAnomalyZones(unittest.TestCase):
    def test_single_flag(self):
        flag = AnomalyFlag(
            cell_id='cell_0',
            discrepancy_type=DISCREPANCY_RAPID_LOADING_ANOMALY,
            severity=0.5,
            zscore=None,
            sources=['sar'],
            attribution=attribute_discrepancy(DISCREPANCY_RAPID_LOADING_ANOMALY, EvidencePacket(cell_id='c')),
        )
        zones = cluster_anomaly_zones([flag], {'cell_0': (39.5, -106.5)})
        self.assertEqual(len(zones), 1)

    def test_clustered_cells(self):
        flags = [
            AnomalyFlag(
                cell_id=f'cell_{i}',
                discrepancy_type=DISCREPANCY_RAPID_LOADING_ANOMALY,
                severity=0.5,
                zscore=None,
                sources=['sar'],
                attribution=attribute_discrepancy(DISCREPANCY_RAPID_LOADING_ANOMALY, EvidencePacket(cell_id='c')),
            )
            for i in range(3)
        ]
        centers = {
            'cell_0': (39.50, -106.50),
            'cell_1': (39.51, -106.51),
            'cell_2': (39.52, -106.52),
        }
        zones = cluster_anomaly_zones(flags, centers, eps_km=5.0)
        self.assertEqual(len(zones), 1)  # all within 5km


if __name__ == '__main__':
    unittest.main()
