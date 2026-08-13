"""Tests for P1 fixes: config, snowpack adapter, AWS adapter, bulletin generator, partner evidence validator."""
from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from backend.common.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_pilot_grid_resolution_defaults_none(self) -> None:
        import os
        os.environ.pop('PILOT_GRID_RESOLUTION_M', None)
        settings = load_settings()
        self.assertIsNone(settings.pilot_grid_resolution_m)

    def test_pilot_grid_resolution_set(self) -> None:
        import os
        os.environ['PILOT_GRID_RESOLUTION_M'] = '1000'
        try:
            settings = load_settings()
            self.assertEqual(settings.pilot_grid_resolution_m, 1000)
        finally:
            os.environ.pop('PILOT_GRID_RESOLUTION_M', None)

    def test_research_model_gate_defaults_true(self) -> None:
        import os
        os.environ.pop('RESEARCH_MODEL_GATE_ENABLED', None)
        settings = load_settings()
        self.assertTrue(settings.research_model_gate_enabled)

    def test_research_model_gate_disabled(self) -> None:
        import os
        os.environ['RESEARCH_MODEL_GATE_ENABLED'] = 'false'
        try:
            settings = load_settings()
            self.assertFalse(settings.research_model_gate_enabled)
        finally:
            os.environ.pop('RESEARCH_MODEL_GATE_ENABLED', None)


class PartnerSnowpackAdapterTests(unittest.TestCase):
    def test_parse_snowpack_csv(self) -> None:
        from backend.common.Partner_snowpack_adapter import parse_snowpack_csv
        csv_content = (
            'station_id,timestamp,snow_depth_cm,shear_strength_kpa,'
            'settlement_index,weak_layer_depth_cm,grain_type,stability_index\n'
            'ST001,2026-01-15T06:00:00,120.0,1.5,0.6,45.0,FC,0.85\n'
            'ST001,2026-01-15T09:00:00,122.0,1.8,0.65,48.0,FC,0.80\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            records = parse_snowpack_csv(f.name)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].station_id, 'ST001')
        self.assertEqual(records[0].snow_depth_cm, 120.0)
        self.assertEqual(records[0].grain_type, 'FC')

    def test_to_snowpack_proxy(self) -> None:
        from backend.common.Partner_snowpack_adapter import PartnerSnowpackRecord, to_snowpack_proxy
        record = PartnerSnowpackRecord(
            station_id='ST001',
            timestamp=datetime(2026, 1, 15, 6, 0, 0),
            snow_depth_cm=120.0,
            shear_strength_kpa=1.5,
            settlement_index=0.6,
            weak_layer_depth_cm=45.0,
            grain_type='FC',
            stability_index=0.85,
        )
        proxy = to_snowpack_proxy(record)
        self.assertEqual(proxy.method, 'Partner_snowpack_1d')
        self.assertEqual(proxy.estimated_shear_strength, 1.5)

    def test_load_disabled_returns_empty(self) -> None:
        from backend.common.Partner_snowpack_adapter import load_Partner_snowpack
        result = load_Partner_snowpack('/nonexistent/path.csv')
        self.assertEqual(result, [])

    def test_csv_with_coordinates_carries_them(self) -> None:
        from backend.common.Partner_snowpack_adapter import parse_snowpack_csv
        csv_content = (
            'station_id,timestamp,snow_depth_cm,shear_strength_kpa,'
            'settlement_index,weak_layer_depth_cm,grain_type,stability_index,'
            'latitude,longitude,elevation_m\n'
            'ST001,2026-01-15T06:00:00,120.0,1.5,0.6,45.0,FC,0.85,34.05,74.10,3200.0\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            records = parse_snowpack_csv(f.name)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].latitude, 34.05)
        self.assertEqual(records[0].longitude, 74.10)
        self.assertEqual(records[0].elevation_m, 3200.0)

    def test_csv_without_coordinates_defaults_to_none(self) -> None:
        from backend.common.Partner_snowpack_adapter import parse_snowpack_csv
        csv_content = (
            'station_id,timestamp,snow_depth_cm,shear_strength_kpa,'
            'settlement_index,weak_layer_depth_cm,grain_type,stability_index\n'
            'ST001,2026-01-15T06:00:00,120.0,1.5,0.6,45.0,FC,0.85\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            f.flush()
            records = parse_snowpack_csv(f.name)
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].latitude)
        self.assertIsNone(records[0].longitude)
        self.assertIsNone(records[0].elevation_m)

    def test_normalized_obs_with_coordinates_passes_validation(self) -> None:
        from backend.common.Partner_snowpack_adapter import PartnerSnowpackRecord, to_snowpack_proxy
        from backend.common.partner_observation import normalize_snowpack_proxy, validate_partner_observation
        record = PartnerSnowpackRecord(
            station_id='ST001',
            timestamp=datetime(2026, 1, 15, 6, 0, 0),
            snow_depth_cm=120.0,
            shear_strength_kpa=1.5,
            settlement_index=0.6,
            weak_layer_depth_cm=45.0,
            grain_type='FC',
            stability_index=0.85,
            latitude=34.05,
            longitude=74.10,
            elevation_m=3200.0,
        )
        proxy = to_snowpack_proxy(record)
        obs = normalize_snowpack_proxy(
            proxy,
            station_id='ST001',
            latitude=record.latitude,
            longitude=record.longitude,
            elevation_m=record.elevation_m,
        )
        self.assertIsNotNone(obs)
        errors = validate_partner_observation(obs)
        self.assertEqual(errors, [])


class AWSStationAdapterTests(unittest.TestCase):
    def test_parse_csv_feed(self) -> None:
        from backend.common.aws_station_adapter import _parse_csv_feed
        csv_data = (
            'station_id,observed_at,air_temp_c,snow_depth_cm,snowfall_cm,'
            'wind_speed_ms,wind_dir_deg,precipitation_mm\n'
            'ST001,2026-01-15T06:00:00,-8.5,120.0,12.0,5.2,180,3.5\n'
        )
        records = _parse_csv_feed(csv_data)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['station_id'], 'ST001')
        self.assertEqual(records[0]['air_temp_c'], -8.5)

    def test_parse_json_feed(self) -> None:
        from backend.common.aws_station_adapter import _parse_json_feed
        json_data = json.dumps([
            {'station_id': 'ST001', 'observed_at': '2026-01-15T06:00:00', 'air_temp_c': -8.5, 'snow_depth_cm': 120.0},
        ])
        records = _parse_json_feed(json_data)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['station_id'], 'ST001')

    def test_validate_schema_missing_fields(self) -> None:
        from backend.common.aws_station_adapter import validate_aws_feed_schema
        records = [{'station_id': 'ST001'}]
        errors = validate_aws_feed_schema(records)
        self.assertTrue(len(errors) > 0)

    def test_validate_schema_valid(self) -> None:
        from backend.common.aws_station_adapter import validate_aws_feed_schema
        records = [{
            'station_id': 'ST001',
            'observed_at': '2026-01-15T06:00:00',
            'air_temp_c': -8.5,
            'snow_depth_cm': 120.0,
        }]
        errors = validate_aws_feed_schema(records)
        self.assertEqual(errors, [])


class PartnerBulletinGeneratorTests(unittest.TestCase):
    def test_generate_shadow_bulletin(self) -> None:
        from backend.common.Partner_bulletin_generator import generate_shadow_bulletin
        cells = [
            {
                'status': 'ready', 'risk_score': 4, 'impact_risk_level': 3,
                'impact_risk_score': 0.65, 'probability': 0.7,
                'weather_inputs': {'snow_depth_cm': 120.0, 'snowfall_24h_cm': 15.0},
            },
            {
                'status': 'ready', 'risk_score': 3, 'impact_risk_level': 2,
                'impact_risk_score': 0.45, 'probability': 0.5,
                'weather_inputs': {'snow_depth_cm': 100.0, 'snowfall_24h_cm': 8.0},
            },
        ]
        bulletin = generate_shadow_bulletin(
            cells, district='Lahaul', altitude_band='3000-4000m',
            bulletin_date=date(2026, 1, 15),
        )
        self.assertIsNotNone(bulletin)
        self.assertEqual(bulletin.district, 'Lahaul')
        self.assertEqual(bulletin.danger_level, 4)
        self.assertEqual(bulletin.danger_label, 'very_high')
        self.assertIn('Fresh snow', bulletin.snow_condition)
        self.assertEqual(bulletin.hazard_level, 4)
        self.assertEqual(bulletin.impact_risk_level, 3)

    def test_generate_bulletin_no_ready_cells(self) -> None:
        from backend.common.Partner_bulletin_generator import generate_shadow_bulletin
        cells = [{'status': 'unavailable', 'risk_score': 0}]
        bulletin = generate_shadow_bulletin(
            cells, district='Kargil', altitude_band='>4000m',
            bulletin_date=date(2026, 1, 15),
        )
        self.assertIsNone(bulletin)

    def test_bulletin_to_dict(self) -> None:
        from backend.common.Partner_bulletin_generator import generate_shadow_bulletin
        cells = [{'status': 'ready', 'risk_score': 2, 'impact_risk_level': 1,
                  'impact_risk_score': 0.3, 'probability': 0.3,
                  'weather_inputs': {'snow_depth_cm': 60.0, 'snowfall_24h_cm': 3.0}}]
        bulletin = generate_shadow_bulletin(
            cells, district='Kullu', altitude_band='2000-3000m',
            bulletin_date=date(2026, 1, 15),
        )
        d = bulletin.to_dict()
        self.assertEqual(d['schema_version'], 'Partner-shadow-bulletin/v1')
        self.assertEqual(d['district'], 'Kullu')
        self.assertEqual(d['provenance'], 'avalanche_insight_hub_shadow')


class PartnerEvidenceValidatorTests(unittest.TestCase):
    def test_validate_directory_all_missing(self) -> None:
        from backend.scripts.validate_partner_evidence import validate_directory
        with tempfile.TemporaryDirectory() as tmpdir:
            results = validate_directory(Path(tmpdir))
            self.assertEqual(results['decision'], 'blocked_pending_partner_evidence')
            self.assertIn('reports', results)
            self.assertGreater(len(results['reports']), 0)

    def test_validate_directory_with_manifest(self) -> None:
        from backend.scripts.validate_partner_evidence import validate_directory
        with tempfile.TemporaryDirectory() as tmpdir:
            results = validate_directory(Path(tmpdir), manifest_path=None)
            self.assertEqual(results['decision'], 'blocked_pending_partner_evidence')
            self.assertIn('partner_source_manifest', results)
            self.assertEqual(results['partner_source_manifest']['decision'], 'partner_source_manifest_not_supplied')

    def test_validate_directory_missing_files_blocked(self) -> None:
        from backend.scripts.validate_partner_evidence import validate_directory
        with tempfile.TemporaryDirectory() as tmpdir:
            results = validate_directory(Path(tmpdir))
            self.assertNotEqual(results['decision'], 'all_partner_evidence_available')
            self.assertGreater(len(results['blocked_requirements']), 0)


class TestSlopeNormalization(unittest.TestCase):
    """G-10: Verify slope normalization fixes saturation bug at caller boundary."""

    def test_slope_0_is_zero(self):
        """0° (flat) should produce 0.0 score."""
        from backend.daily_inference import _normalize_slope_to_score
        self.assertEqual(_normalize_slope_to_score(0.0), 0.0)

    def test_slope_38_is_peak(self):
        """38° should produce 1.0 (peak avalanche danger)."""
        from backend.daily_inference import _normalize_slope_to_score
        self.assertAlmostEqual(_normalize_slope_to_score(38.0), 1.0, places=6)

    def test_slope_30_is_moderate(self):
        """30° should produce a moderate score (~0.789)."""
        from backend.daily_inference import _normalize_slope_to_score
        score = _normalize_slope_to_score(30.0)
        self.assertGreater(score, 0.7)
        self.assertLess(score, 1.0)

    def test_slope_45_is_high_but_decreasing(self):
        """45° should be high but less than 38° score (~0.816)."""
        from backend.daily_inference import _normalize_slope_to_score
        score_45 = _normalize_slope_to_score(45.0)
        score_38 = _normalize_slope_to_score(38.0)
        self.assertGreater(score_45, 0.7)
        self.assertLess(score_45, score_38)

    def test_slope_60_is_lower(self):
        """60° should be significantly lower (~0.421) — steep slopes shed snow."""
        from backend.daily_inference import _normalize_slope_to_score
        score_60 = _normalize_slope_to_score(60.0)
        self.assertLess(score_60, 0.5)
        self.assertGreater(score_60, 0.0)

    def test_no_saturation_above_38(self):
        """G-10 core: slopes above 38° must NOT all produce the same score."""
        from backend.daily_inference import _normalize_slope_to_score
        score_39 = _normalize_slope_to_score(39.0)
        score_45 = _normalize_slope_to_score(45.0)
        score_60 = _normalize_slope_to_score(60.0)
        self.assertNotEqual(score_39, score_45)
        self.assertNotEqual(score_45, score_60)
        # Monotonically decreasing above 38°
        self.assertGreater(score_39, score_45)
        self.assertGreater(score_45, score_60)

    def test_monotonic_below_38(self):
        """Slopes below 38° should be monotonically increasing toward 38°."""
        from backend.daily_inference import _normalize_slope_to_score
        score_0 = _normalize_slope_to_score(0.0)
        score_10 = _normalize_slope_to_score(10.0)
        score_20 = _normalize_slope_to_score(20.0)
        score_30 = _normalize_slope_to_score(30.0)
        score_38 = _normalize_slope_to_score(38.0)
        self.assertLess(score_0, score_10)
        self.assertLess(score_10, score_20)
        self.assertLess(score_20, score_30)
        self.assertLess(score_30, score_38)


if __name__ == '__main__':
    unittest.main()
