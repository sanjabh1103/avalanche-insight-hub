"""Integration tests for the 4-tier snowpack physics fallback chain.

Tests verify that:
1. SnowpackPhysicsResult dataclass holds all expected fields
2. Heuristic fallback produces valid results
3. build_real_feature_row with snowpack_physics_override produces 29 features
4. SMET file generation produces valid MeteoIO format
5. Grain type classification maps Swiss codes correctly
6. Weather history fetch function signature is correct
7. Fallback chain order: SNOWPACK → COSIPY → heuristic → synthetic
"""
from __future__ import annotations

import ast
import math
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestSnowpackPhysicsResult(unittest.TestCase):
    """Test SnowpackPhysicsResult dataclass structure."""

    def test_result_has_all_fields(self):
        from backend.common.snowpack_physics import SnowpackPhysicsResult
        result = SnowpackPhysicsResult(
            weak_layer_depth_m=0.5,
            weak_layer_grain_type='faceted',
            weak_layer_shear_strength_kpa=1.2,
            snowpack_stability_index=0.8,
            temperature_gradient_per_m=15.0,
            liquid_water_content_pct=2.0,
            layer_count=5,
            snow_height_m=1.2,
            bulk_density_kgm3=300.0,
            method='cosipy_v2',
            layers=[{'density': 300, 'temp': -5}],
        )
        self.assertEqual(result.weak_layer_depth_m, 0.5)
        self.assertEqual(result.weak_layer_grain_type, 'faceted')
        self.assertEqual(result.method, 'cosipy_v2')
        self.assertEqual(result.layer_count, 5)

    def test_result_is_frozen(self):
        from backend.common.snowpack_physics import SnowpackPhysicsResult
        result = SnowpackPhysicsResult(
            weak_layer_depth_m=0.3,
            weak_layer_grain_type='depth_hoar',
            weak_layer_shear_strength_kpa=0.5,
            snowpack_stability_index=0.4,
            temperature_gradient_per_m=25.0,
            liquid_water_content_pct=1.0,
            layer_count=3,
            snow_height_m=0.8,
            bulk_density_kgm3=220.0,
            method='heuristic_fallback',
            layers=[],
        )
        with self.assertRaises((AttributeError, Exception)):
            result.weak_layer_depth_m = 999


class TestHeuristicFallback(unittest.TestCase):
    """Test heuristic fallback path (no COSIPY or SNOWPACK binary needed)."""

    def test_heuristic_produces_valid_result(self):
        from backend.common.snowpack_physics import compute_cell_snowpack_physics
        from backend.common.snowpack_proxy import SnowpackProxy

        # Create a minimal SnowpackProxy-like input
        proxy = SnowpackProxy(
            estimated_shear_strength=5.0,
            snow_settlement_index=0.6,
            season_start='2024-11-01',
            method='regional',
        )

        as_of = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        # G9: Mock network calls to prevent hang in test environment
        with patch('requests.get', side_effect=Exception('network disabled in test')):
            result = compute_cell_snowpack_physics(
                lat=28.0,
                lng=86.25,
                elevation_m=3000,
                as_of=as_of,
                weather_inputs={
                    'temperature_2m': -10.0,
                    'windspeed_10m': 5.0,
                    'precipitation': 0.0,
                    'snowfall_24h': 0.05,
                },
                terrain_inputs={
                    'elevation_m': 3000,
                    'slope_angle': 35,
                    'aspect': 180,
                },
            )

            self.assertIsNotNone(result)
            self.assertIn(result.method, ('heuristic_fallback', 'cosipy_v2', 'snowpack_native'))
            self.assertGreaterEqual(result.weak_layer_depth_m, 0.0)
            self.assertIn(result.weak_layer_grain_type, ('faceted', 'depth_hoar', 'surface_hoar', 'melt_form', 'rounded'))
            self.assertGreaterEqual(result.snowpack_stability_index, 0.0)


class TestFeatureColumnsCount(unittest.TestCase):
    """Test that FEATURE_COLUMNS includes the 6 new physics features."""

    def test_feature_columns_count(self):
        from backend.common.features import FEATURE_COLUMNS
        self.assertGreaterEqual(len(FEATURE_COLUMNS), 29,
            f'FEATURE_COLUMNS should have at least 29 entries, got {len(FEATURE_COLUMNS)}')

    def test_physics_features_present(self):
        from backend.common.features import FEATURE_COLUMNS
        expected = [
            'weak_layer_depth',
            'grain_type_faceted',
            'grain_type_depth_hoar',
            'stability_index',
            'temp_gradient_profile',
            'liquid_water_content',
        ]
        for feat in expected:
            self.assertIn(feat, FEATURE_COLUMNS, f'Missing feature: {feat}')


class TestSMETGeneration(unittest.TestCase):
    """Test SMET file generation from Open-Meteo weather data."""

    def test_smet_file_format(self):
        from backend.common.meteoio_openmeteo import write_smet_file, SMET_COLUMNS

        samples = [
            {
                'time': '2025-01-15T00:00',
                'temperature_2m': -10.0,
                'relative_humidity_2m': 80.0,
                'windspeed_10m': 5.0,
                'winddirection_10m': 180.0,
                'shortwave_radiation': 0.0,
                'cloud_cover': 50.0,
                'precipitation': 0.0,
                'snow_depth': 0.5,
            },
            {
                'time': '2025-01-15T01:00',
                'temperature_2m': -12.0,
                'relative_humidity_2m': 85.0,
                'windspeed_10m': 3.0,
                'winddirection_10m': 190.0,
                'shortwave_radiation': 0.0,
                'cloud_cover': 60.0,
                'precipitation': 0.1,
                'snow_depth': 0.55,
            },
        ]

        with tempfile.NamedTemporaryFile(suffix='.smet', mode='w', delete=False) as f:
            smet_path = Path(f.name)

        try:
            write_smet_file(
                output_path=smet_path,
                station_id='test_cell',
                latitude=28.0,
                longitude=86.25,
                elevation=3000.0,
                samples=samples,
            )

            content = smet_path.read_text()
            self.assertIn('SMET 1.1 ASCII', content)
            self.assertIn('[HEADER]', content)
            self.assertIn('[DATA]', content)
            self.assertIn('station_id       = test_cell', content)
            self.assertIn('latitude         = 28.000000', content)

            # Verify data section has 2 rows
            data_lines = [l for l in content.split('[DATA]')[1].strip().split('\n') if l.strip()]
            self.assertEqual(len(data_lines), 2)
            # MeteoIO's SMET contract represents RH as a fraction [0, 1],
            # while the source Open-Meteo field is expressed in percent.
            self.assertAlmostEqual(float(data_lines[0].split()[2]), 0.8, places=4)

            # Verify column count in header
            self.assertIn('ncolumns         = 11', content)
        finally:
            smet_path.unlink(missing_ok=True)

    def test_smet_strict_validation_rejects_missing_critical_source(self):
        from backend.common.meteoio_openmeteo import validate_smet_samples
        with self.assertRaises(ValueError):
            validate_smet_samples([{
                'time': '2025-01-15T00:00',
                'temperature_2m': -10.0,
                'relative_humidity_2m': 80.0,
                'windspeed_10m': 5.0,
            }])

    def test_smet_strict_validation_accepts_official_alternative_inputs(self):
        from backend.common.meteoio_openmeteo import validate_smet_samples
        validate_smet_samples([{
            'time': '2025-01-15T00:00',
            'temperature_2m': -10.0,
            'relative_humidity_2m': 80.0,
            'windspeed_10m': 5.0,
            'reflected_shortwave_radiation': 10.0,
            'cloud_cover': 50.0,
            'snow_depth': 0.5,
        }])

    def test_smet_columns_standard(self):
        from backend.common.meteoio_openmeteo import SMET_COLUMNS
        expected = ['timestamp', 'TA', 'RH', 'VW', 'DW', 'ISWR', 'ILWR', 'PSUM', 'HS', 'TSG', 'TSS']
        self.assertEqual(SMET_COLUMNS, expected)

    def test_terrestrial_radiation_does_not_control_ilwr(self):
        from backend.common.meteoio_openmeteo import _open_meteo_to_smet_row

        base = {
            'temperature_2m': -10.0,
            'relative_humidity_2m': 80.0,
            'windspeed_10m': 5.0,
            'shortwave_radiation': 0.0,
            'cloud_cover': 50.0,
            'precipitation': 0.0,
        }
        with_toa = dict(base, terrestrial_radiation=1367.7)
        self.assertEqual(
            _open_meteo_to_smet_row(with_toa)['ILWR'],
            _open_meteo_to_smet_row(base)['ILWR'],
        )
        self.assertLess(_open_meteo_to_smet_row(with_toa)['ILWR'], 1000.0)


class TestGrainTypeClassification(unittest.TestCase):
    """Test Swiss grain code to string mapping."""

    def test_depth_hoar(self):
        from backend.common.meteoio_openmeteo import _swiss_grain_code_to_str
        self.assertEqual(_swiss_grain_code_to_str(10), 'depth_hoar')
        self.assertEqual(_swiss_grain_code_to_str(11), 'depth_hoar')

    def test_faceted(self):
        from backend.common.meteoio_openmeteo import _swiss_grain_code_to_str
        self.assertEqual(_swiss_grain_code_to_str(8), 'faceted')
        self.assertEqual(_swiss_grain_code_to_str(9), 'faceted')

    def test_surface_hoar(self):
        from backend.common.meteoio_openmeteo import _swiss_grain_code_to_str
        self.assertEqual(_swiss_grain_code_to_str(12), 'surface_hoar')

    def test_melt_form(self):
        from backend.common.meteoio_openmeteo import _swiss_grain_code_to_str
        self.assertEqual(_swiss_grain_code_to_str(13), 'melt_form')
        self.assertEqual(_swiss_grain_code_to_str(14), 'melt_form')

    def test_rounded_default(self):
        from backend.common.meteoio_openmeteo import _swiss_grain_code_to_str
        self.assertEqual(_swiss_grain_code_to_str(6), 'rounded')
        self.assertEqual(_swiss_grain_code_to_str(0), 'rounded')


class TestWeatherHistoryFetch(unittest.TestCase):
    """Test weather history fetch function signature and structure."""

    def test_fetch_function_exists(self):
        from backend.common.snowpack_physics import fetch_weather_history_for_snowpack
        self.assertTrue(callable(fetch_weather_history_for_snowpack))

    def test_fetch_returns_empty_on_network_failure(self):
        from backend.common.snowpack_physics import fetch_weather_history_for_snowpack
        with patch('requests.get', side_effect=Exception('network error')):
            samples = fetch_weather_history_for_snowpack(
                lat=28.0,
                lng=86.25,
                as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
                max_days=7,
            )
            self.assertEqual(samples, [])

    def test_fetch_parses_api_response(self):
        from backend.common.snowpack_physics import fetch_weather_history_for_snowpack

        mock_response = type('MockResponse', (), {
            'status_code': 200,
            'json': lambda self: {
                'hourly': {
                    'time': ['2025-01-14T00:00', '2025-01-14T01:00'],
                    'temperature_2m': [-10.0, -12.0],
                    'precipitation': [0.0, 0.1],
                    'snowfall': [0.0, 0.1],
                    'snow_depth': [0.5, 0.55],
                    'windspeed_10m': [5.0, 3.0],
                    'winddirection_10m': [180.0, 190.0],
                    'relative_humidity_2m': [80.0, 85.0],
                    'shortwave_radiation': [0.0, 0.0],
                    'cloud_cover': [50.0, 60.0],
                    'surface_pressure': [700.0, 700.0],
                }
            },
            'raise_for_status': lambda self: None,
        })()

        with patch('requests.get', return_value=mock_response):
            samples = fetch_weather_history_for_snowpack(
                lat=28.0,
                lng=86.25,
                as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
                max_days=7,
            )
            self.assertEqual(len(samples), 2)
            self.assertEqual(samples[0]['temperature_2m'], -10.0)
            self.assertEqual(samples[1]['precipitation'], 0.1)
            self.assertIn('time', samples[0])


class TestFallbackChainOrder(unittest.TestCase):
    """Test that the fallback chain is wired in correct order via AST inspection."""

    def test_snowpack_native_attempted_before_cosipy(self):
        with open(Path(__file__).resolve().parents[2] / 'backend/common/snowpack_physics.py') as f:
            src = f.read()

        # Find the positions of each fallback attempt in compute_cell_snowpack_physics
        # The import at top has snowpack_binary_available too, so find the one in the function body
        compute_func_pos = src.find('def compute_cell_snowpack_physics')
        src_after_func = src[compute_func_pos:]

        snowpack_pos = src_after_func.find('snowpack_binary_available()')
        cosipy_pos = src_after_func.find('_cosipy_available()')
        heuristic_pos = src_after_func.find('compute_cell_snowpack_proxy(')

        self.assertGreater(snowpack_pos, 0, 'SNOWPACK native path not found in compute_cell_snowpack_physics')
        self.assertGreater(cosipy_pos, 0, 'COSIPY path not found in compute_cell_snowpack_physics')
        self.assertGreater(heuristic_pos, 0, 'Heuristic path not found in compute_cell_snowpack_physics')

        # SNOWPACK should be attempted before COSIPY
        self.assertLess(snowpack_pos, cosipy_pos,
            'SNOWPACK native should be attempted before COSIPY')
        # COSIPY should be attempted before heuristic
        self.assertLess(cosipy_pos, heuristic_pos,
            'COSIPY should be attempted before heuristic fallback')

    def test_snowpack_native_cell_function_exists(self):
        with open(Path(__file__).resolve().parents[2] / 'backend/common/snowpack_physics.py') as f:
            tree = ast.parse(f.read())
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        self.assertIn('run_snowpack_native_cell', funcs)

    def test_meteoio_openmeteo_functions_exist(self):
        with open(Path(__file__).resolve().parents[2] / 'backend/common/meteoio_openmeteo.py') as f:
            tree = ast.parse(f.read())
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        for expected in ['write_smet_file', 'snowpack_binary_available', 'run_snowpack_native', 'parse_snowpack_pro']:
            self.assertIn(expected, funcs, f'Missing function: {expected}')

class TestAWSOMERunner(unittest.TestCase):
    """Test AWSOME runner module structure."""

    def test_awsome_runner_functions(self):
        from backend.common.awsome_runner import (
            run_awsome_for_region,
            run_awsome_all_regions,
            validate_awsome_setup,
            load_awsome_region_config,
        )
        self.assertTrue(callable(run_awsome_for_region))
        self.assertTrue(callable(run_awsome_all_regions))
        self.assertTrue(callable(validate_awsome_setup))
        self.assertTrue(callable(load_awsome_region_config))

    def test_awsome_region_config_has_12_regions(self):
        from backend.common.awsome_runner import load_awsome_region_config
        config = load_awsome_region_config()
        self.assertEqual(len(config), 12)
        self.assertIn('himalayas_nepal', config)
        self.assertIn('colorado_rockies', config)
        self.assertIn('pir_panjal_nw_himalaya', config)
        self.assertIn('karakoram_&_ladakh', config)

    def test_validate_setup_returns_dict(self):
        from backend.common.awsome_runner import validate_awsome_setup
        status = validate_awsome_setup()
        self.assertIsInstance(status, dict)
        self.assertIn('awsome_installed', status)
        self.assertIn('snowpack_binary', status)


if __name__ == '__main__':
    unittest.main(verbosity=2)
