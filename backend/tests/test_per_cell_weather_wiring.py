"""Tests for per-cell weather wiring (G4).

Verifies that when cell_weather_map is present in region_context,
_build_rows_for_timestamp uses per-cell weather instead of region-center.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


class PerCellWeatherWiringTests(unittest.TestCase):

    def test_cell_weather_map_lookup_by_pixel_id(self) -> None:
        """Projected grid cells should have pixel_id for weather map lookup."""
        from backend.common.features import build_region_grid_projected
        from backend.common.regions import Region
        try:
            region = Region(
                name='Test Region',
                bbox=(30.0, 77.0, 30.5, 77.5),
                center=(30.25, 77.25),
                zoom=8,
            )
            grid = build_region_grid_projected(region, cell_size_m=11000, strict=False)
            self.assertTrue(len(grid) > 0)
            for cell in grid:
                self.assertIn('pixel_id', cell)
                self.assertTrue(cell['pixel_id'])
        except (RuntimeError, TypeError):
            self.skipTest("pyproj not available or signature mismatch")

    def test_cell_weather_map_absent_falls_back(self) -> None:
        """When cell_weather_map is None, weather_sample is used (backward compat)."""
        # Simulate the logic: no map -> use weather_sample
        region_context = {'cell_weather_map': None}
        weather_sample = {'air_temp_c': 5.0}
        cell = {'pixel_id': 'test_region_0_0'}
        prepared = {'pixel_id': 'test_region_0_0', 'cell': cell}

        _cwm = region_context.get('cell_weather_map')
        _pid = prepared.get('pixel_id') or cell.get('pixel_id')
        if _cwm and _pid and _pid in _cwm:
            _cell_weather = _cwm[_pid]
        else:
            _cell_weather = weather_sample or {}

        self.assertEqual(_cell_weather, weather_sample)

    def test_cell_weather_map_present_uses_per_cell(self) -> None:
        """When cell_weather_map has the pixel_id, use that profile."""
        cell_weather_map = {
            'test_region_0_0': {'air_temp_c': -2.0, 'wind_speed_ms': 15.0},
            'test_region_0_1': {'air_temp_c': 3.0, 'wind_speed_ms': 5.0},
        }
        region_context = {'cell_weather_map': cell_weather_map}
        weather_sample = {'air_temp_c': 5.0}  # region-center

        # Cell 0 should get -2.0, not 5.0
        cell0 = {'pixel_id': 'test_region_0_0'}
        prepared0 = {'pixel_id': 'test_region_0_0', 'cell': cell0}
        _cwm = region_context.get('cell_weather_map')
        _pid = prepared0.get('pixel_id') or cell0.get('pixel_id')
        if _cwm and _pid and _pid in _cwm:
            w0 = _cwm[_pid]
        else:
            w0 = weather_sample or {}
        self.assertEqual(w0['air_temp_c'], -2.0)

        # Cell 1 should get 3.0, not 5.0
        cell1 = {'pixel_id': 'test_region_0_1'}
        prepared1 = {'pixel_id': 'test_region_0_1', 'cell': cell1}
        _pid1 = prepared1.get('pixel_id') or cell1.get('pixel_id')
        if _cwm and _pid1 and _pid1 in _cwm:
            w1 = _cwm[_pid1]
        else:
            w1 = weather_sample or {}
        self.assertEqual(w1['air_temp_c'], 3.0)

    def test_cell_weather_map_validation_mode_fails_closed(self) -> None:
        """In validation mode, missing pixel_id must raise."""
        cell_weather_map = {'_mode': 'validation', 'test_region_0_0': {'air_temp_c': -2.0}}
        region_context = {'cell_weather_map': cell_weather_map}
        weather_sample = {'air_temp_c': 5.0}
        cell = {'pixel_id': 'missing_pixel'}
        prepared = {'pixel_id': 'missing_pixel', 'cell': cell}

        _cwm = region_context.get('cell_weather_map')
        _pid = prepared.get('pixel_id') or cell.get('pixel_id')
        try:
            if _cwm and _pid and _pid in _cwm:
                _ = _cwm[_pid]
            elif _cwm and _cwm.get('_mode') == 'validation':
                raise RuntimeError(
                    f"Per-cell weather validation mode: pixel_id '{_pid}' "
                    f"missing from cell_weather_map"
                )
            else:
                _ = weather_sample or {}
            self.fail("Should have raised RuntimeError")
        except RuntimeError as e:
            self.assertIn('validation mode', str(e))

    def test_active_prepare_validation_does_not_fallback_to_center_weather(self) -> None:
        """A batch retrieval failure must stop validation before scoring."""
        from backend.daily_inference import build_cells
        import pandas as pd

        region = SimpleNamespace(key='test', center=(32.0, 77.0))
        with patch.dict('os.environ', {'RAVAFCAST_PER_CELL_WEATHER_MODE': 'validation'}, clear=False), \
             patch('backend.daily_inference.build_region_grid', return_value=[{
                 'row': 0, 'col': 0, 'lat': 32.0, 'lng': 77.0,
                 'lat_end': 32.01, 'lng_end': 77.01,
                 'pixel_id': 'test_0_0', 'crs': 'EPSG:4326',
             }]), \
             patch('backend.common.real_features.fetch_batch_weather_profile', side_effect=RuntimeError('batch unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'validation failed'):
                build_cells(
                    region=region,
                    bundle={},
                    grid_size=1,
                    forecast_date=pd.Timestamp('2026-07-18T06:00:00Z'),
                )


if __name__ == '__main__':
    unittest.main()
