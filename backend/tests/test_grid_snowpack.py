"""Tests for F5: Grid-Scale SNOWPACK Operationalization."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.common.snowpack_physics import (
    SnowpackPhysicsBatchResult,
    SnowpackPhysicsResult,
    compute_batch_snowpack_physics,
    compute_cell_snowpack_physics,
    compute_grid_snowpack_physics,
)


# G9: Mock all network calls to prevent thread-pool hang in test environment
@pytest.fixture(autouse=True)
def mock_network():
    with patch('requests.get', side_effect=Exception('network disabled in test')):
        yield


@pytest.fixture
def as_of():
    return datetime(2024, 1, 15, 6, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def small_coordinates():
    return [
        (32.5, 77.0, 3500.0),
        (32.51, 77.01, 3600.0),
        (32.52, 77.02, 3700.0),
    ]


@pytest.fixture
def large_coordinates():
    return [
        (32.5 + i * 0.01, 77.0 + j * 0.01, 3000.0 + i * 50)
        for i in range(20)
        for j in range(20)
    ]


@pytest.fixture
def large_grid_cells():
    return [
        {
            'cell_id': f'cell_{i}_{j}',
            'lat': 32.5 + i * 0.01,
            'lng': 77.0 + j * 0.01,
            'elevation_m': 3000.0 + i * 50,
            'zone_type': 'pir_panjal' if i < 10 else 'great_himalaya',
        }
        for i in range(20)
        for j in range(20)
    ]


class TestComputeBatchSnowpackPhysics:
    _mock_weather = staticmethod(lambda lat, lng: {'temperature_2m': -5.0, 'precipitation': 0.0, 'windspeed_10m': 10.0})
    _mock_terrain = staticmethod(lambda lat, lng: {'elevation_m': 3500.0, 'slope_deg': 30.0, 'aspect_deg': 180.0})

    def test_sequential_small_batch(self, small_coordinates, as_of):
        results = compute_batch_snowpack_physics(
            coordinates=small_coordinates,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            max_workers=1,
        )
        assert len(results) == 3
        for r in results:
            assert isinstance(r, SnowpackPhysicsBatchResult)
            assert r.status == 'ok'
            assert r.result is not None

    def test_parallel_small_batch(self, small_coordinates, as_of):
        results = compute_batch_snowpack_physics(
            coordinates=small_coordinates,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            max_workers=2,
        )
        assert len(results) == 3
        for r in results:
            assert r.status == 'ok'
            assert r.result is not None

    def test_parallel_matches_sequential(self, small_coordinates, as_of):
        seq_results = compute_batch_snowpack_physics(
            coordinates=small_coordinates,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            max_workers=1,
        )
        par_results = compute_batch_snowpack_physics(
            coordinates=small_coordinates,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            max_workers=4,
        )
        assert len(seq_results) == len(par_results)
        for s, p in zip(seq_results, par_results):
            assert s.status == p.status
            if s.result and p.result:
                assert s.result.weak_layer_grain_type == p.result.weak_layer_grain_type
                assert abs(s.result.snow_height_m - p.result.snow_height_m) < 1e-5

    def test_empty_coordinates(self, as_of):
        results = compute_batch_snowpack_physics(
            coordinates=[],
            as_of=as_of,
        )
        assert len(results) == 0

    def test_progress_callback(self, small_coordinates, as_of):
        progress_calls: list[tuple[int, int]] = []
        compute_batch_snowpack_physics(
            coordinates=small_coordinates,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            max_workers=1,
            progress_callback=lambda completed, total: progress_calls.append((completed, total)),
        )
        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)

    def test_zone_type_passed_through(self, small_coordinates, as_of):
        results = compute_batch_snowpack_physics(
            coordinates=small_coordinates,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            zone_type='pir_panjal',
            max_workers=1,
        )
        assert len(results) == 3
        for r in results:
            assert r.status == 'ok'

    def test_error_in_one_cell_doesnt_crash(self, as_of):
        coords = [
            (32.5, 77.0, 3500.0),
            (999.0, 999.0, -99999.0),  # extreme values
            (32.52, 77.02, 3700.0),
        ]
        results = compute_batch_snowpack_physics(
            coordinates=coords,
            as_of=as_of,
            weather_inputs_fn=self._mock_weather,
            terrain_inputs_fn=self._mock_terrain,
            max_workers=1,
        )
        assert len(results) == 3
        # At least the valid cells should have results
        ok_count = sum(1 for r in results if r.status == 'ok')
        assert ok_count >= 2


class TestComputeGridSnowpackPhysics:
    # G9: snowpack_physics.py is frozen (denylist); use max_workers=1 to avoid
    # ThreadPoolExecutor hang under pytest's thread-based timeout method.
    @pytest.mark.timeout(120)
    def test_grid_returns_dict_keyed_by_cell_id(self, large_grid_cells, as_of):
        mock_weather = lambda lat, lng: {'temperature_2m': -5.0, 'precipitation': 0.0, 'windspeed_10m': 10.0}
        mock_terrain = lambda lat, lng: {'elevation_m': 3500.0, 'slope_deg': 30.0, 'aspect_deg': 180.0}
        results = compute_grid_snowpack_physics(
            grid_cells=large_grid_cells,
            as_of=as_of,
            weather_inputs_fn=mock_weather,
            terrain_inputs_fn=mock_terrain,
            max_workers=1,
        )
        assert isinstance(results, dict)
        assert len(results) > 0
        for cell_id, result in results.items():
            assert isinstance(cell_id, str)
            assert isinstance(result, SnowpackPhysicsResult)

    @pytest.mark.timeout(120)
    def test_grid_groups_by_zone(self, large_grid_cells, as_of):
        mock_weather = lambda lat, lng: {'temperature_2m': -5.0, 'precipitation': 0.0, 'windspeed_10m': 10.0}
        mock_terrain = lambda lat, lng: {'elevation_m': 3500.0, 'slope_deg': 30.0, 'aspect_deg': 180.0}
        results = compute_grid_snowpack_physics(
            grid_cells=large_grid_cells,
            as_of=as_of,
            weather_inputs_fn=mock_weather,
            terrain_inputs_fn=mock_terrain,
            max_workers=1,
        )
        # All 400 cells should produce results (heuristic fallback)
        assert len(results) == 400

    def test_grid_empty(self, as_of):
        results = compute_grid_snowpack_physics(
            grid_cells=[],
            as_of=as_of,
        )
        assert results == {}

    @pytest.mark.timeout(120)
    def test_grid_progress_callback(self, large_grid_cells, as_of):
        mock_weather = lambda lat, lng: {'temperature_2m': -5.0, 'precipitation': 0.0, 'windspeed_10m': 10.0}
        mock_terrain = lambda lat, lng: {'elevation_m': 3500.0, 'slope_deg': 30.0, 'aspect_deg': 180.0}
        progress_calls: list[tuple[int, int]] = []
        compute_grid_snowpack_physics(
            grid_cells=large_grid_cells,
            as_of=as_of,
            weather_inputs_fn=mock_weather,
            terrain_inputs_fn=mock_terrain,
            max_workers=1,
            progress_callback=lambda completed, total: progress_calls.append((completed, total)),
        )
        assert len(progress_calls) == 400
        assert progress_calls[-1] == (400, 400)

    def test_grid_mixed_zones(self, as_of):
        mock_weather = lambda lat, lng: {'temperature_2m': -5.0, 'precipitation': 0.0, 'windspeed_10m': 10.0}
        mock_terrain = lambda lat, lng: {'elevation_m': 3500.0, 'slope_deg': 30.0, 'aspect_deg': 180.0}
        cells = [
            {'cell_id': 'a', 'lat': 32.5, 'lng': 77.0, 'elevation_m': 3500.0, 'zone_type': 'pir_panjal'},
            {'cell_id': 'b', 'lat': 33.0, 'lng': 77.0, 'elevation_m': 4000.0, 'zone_type': 'great_himalaya'},
            {'cell_id': 'c', 'lat': 34.0, 'lng': 77.0, 'elevation_m': 5000.0, 'zone_type': 'karakoram_ladakh'},
            {'cell_id': 'd', 'lat': 32.7, 'lng': 77.0, 'elevation_m': 3600.0, 'zone_type': None},
        ]
        results = compute_grid_snowpack_physics(
            grid_cells=cells,
            as_of=as_of,
            weather_inputs_fn=mock_weather,
            terrain_inputs_fn=mock_terrain,
            max_workers=2,
        )
        assert len(results) == 4
        assert 'a' in results
        assert 'b' in results
        assert 'c' in results
        assert 'd' in results

    def test_grid_execution_time_under_threshold(self, as_of):
        import time
        # Use 25 cells (5x5) with mock weather/terrain to avoid API calls
        cells = [
            {
                'cell_id': f'cell_{i}_{j}',
                'lat': 32.5 + i * 0.01,
                'lng': 77.0 + j * 0.01,
                'elevation_m': 3000.0 + i * 50,
                'zone_type': 'pir_panjal' if i < 3 else 'great_himalaya',
            }
            for i in range(5)
            for j in range(5)
        ]
        mock_weather = lambda lat, lng: {'temperature_2m': -5.0, 'precipitation': 0.0, 'windspeed_10m': 10.0}
        mock_terrain = lambda lat, lng: {'elevation_m': 3500.0, 'slope_deg': 30.0, 'aspect_deg': 180.0}
        start = time.perf_counter()
        compute_grid_snowpack_physics(
            grid_cells=cells,
            as_of=as_of,
            weather_inputs_fn=mock_weather,
            terrain_inputs_fn=mock_terrain,
            max_workers=4,
        )
        elapsed = time.perf_counter() - start
        # 25 cells should complete in heuristic mode under 30 seconds
        assert elapsed < 30.0, f'Grid execution took {elapsed:.1f}s, expected < 30s'
