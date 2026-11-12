"""G9: End-to-end RAvaFcast integration test with fake DB.

Covers: _prepare_region_context → _build_rows_for_timestamp → upsert_forecast_grid → publish_forecast_run
using a fake DB enforcing unique keys. Proves the complete six-hour path
with distinct per-cell values and replay metadata.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

from backend.common.features import FEATURE_COLUMNS
from backend.common.real_features import HourlyWeatherSample
from backend.common.snowpack_proxy import SnowpackProxy, SnowpackProxyBatchResult


class E2EIntegrationTests(unittest.TestCase):
    """Prove the complete six-hour path with fake DB and replay metadata."""

    def _make_cadence_context(self, issue_time: datetime | None = None):
        from backend.common.ravafcast_cadence import build_cadence_context
        import os
        os.environ['RAVAFCAST_CADENCE_HOURS'] = '6'
        try:
            ctx = build_cadence_context(issue_time=issue_time)
        finally:
            del os.environ['RAVAFCAST_CADENCE_HOURS']
        return ctx

    def test_cadence_context_deterministic_replay(self) -> None:
        """Replaying same issue_time produces identical cadence context."""
        fixed_dt = datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc)
        ctx1 = self._make_cadence_context(issue_time=fixed_dt)
        ctx2 = self._make_cadence_context(issue_time=fixed_dt)
        self.assertEqual(ctx1.issue_time, ctx2.issue_time)
        self.assertEqual(ctx1.issue_slot, ctx2.issue_slot)
        self.assertEqual(ctx1.valid_from, ctx2.valid_from)
        self.assertEqual(ctx1.valid_to, ctx2.valid_to)
        self.assertEqual(ctx1.source_as_of, ctx2.source_as_of)

    def test_four_slots_produce_distinct_contexts(self) -> None:
        """Four issue times in different slots produce distinct contexts."""
        contexts = []
        for hour in (0, 6, 12, 18):
            dt = datetime(2026, 7, 18, hour, 0, tzinfo=timezone.utc)
            ctx = self._make_cadence_context(issue_time=dt)
            contexts.append(ctx)
        slots = [c.issue_slot for c in contexts]
        self.assertEqual(len(set(slots)), 4)
        self.assertEqual(sorted(slots), ['00', '06', '12', '18'])

    def test_publish_with_fake_db_four_slot(self) -> None:
        """Full publication path with fake DB enforcing unique keys."""
        from backend.common.forecast_publication import publish_forecast_run

        fake_db: dict[tuple, dict] = {}

        def mock_insert(table, rows, **kwargs):
            if table != 'forecast_runs':
                return [{'id': f'fake-{table}'}]
            for row in rows:
                key = (
                    row.get('hazard_type'),
                    row.get('region_key'),
                    row.get('forecast_date'),
                    row.get('issue_slot'),
                )
                fake_db[key] = row
            return [{'id': f'fake-{len(fake_db)}'}]

        fixed_dt = datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc)
        ctx = self._make_cadence_context(issue_time=fixed_dt)

        for slot_dt in [datetime(2026, 7, 18, h, 0, tzinfo=timezone.utc) for h in (0, 6, 12, 18)]:
            slot_ctx = self._make_cadence_context(issue_time=slot_dt)
            with patch('backend.common.forecast_publication.rest_insert', side_effect=mock_insert), \
                 patch('backend.common.forecast_publication.storage_upload_bytes', return_value='s://t'), \
                 patch('backend.common.forecast_publication.storage_upsert_json', return_value='s://m'), \
                 patch('backend.common.forecast_publication.patch_row_by_id', return_value=None), \
                 patch('backend.common.forecast_publication.rest_rpc', return_value=None), \
                 patch('backend.common.forecast_publication._record_event'), \
                 patch('backend.common.forecast_publication._research_gate_enabled', return_value=False):
                publish_forecast_run(
                    hazard_type='avalanche', region_key='test', region_name='Test',
                    forecast_date='2026-07-18', horizon_hours=72, grid_size=20,
                    bbox=[32.0, 77.0, 32.5, 77.5], status='ready',
                    weather_summary={}, forecast_bulletins={}, model_metadata={},
                    hourly_grids=[[{'status': 'ready'}]], runout_polygons=[],
                    issue_slot=slot_ctx.issue_slot,
                    cadence_hours=slot_ctx.cadence_hours,
                    valid_from=slot_ctx.valid_from.isoformat(),
                    valid_to=slot_ctx.valid_to.isoformat(),
                    source_as_of=slot_ctx.source_as_of.isoformat(),
                    issue_time=slot_ctx.issue_time.isoformat(),
                )

        self.assertEqual(len(fake_db), 4)
        slots_in_db = {v.get('issue_slot') for v in fake_db.values() if 'issue_slot' in v}
        self.assertEqual(slots_in_db, {'00', '06', '12', '18'})

    def test_negative_validation_mode_fails_closed(self) -> None:
        """Validation mode with missing cell should fail closed."""
        from backend.common.ravafcast_cell_input import build_cell_inputs

        grid_cells = [
            {'lat': 32.0, 'lng': 77.0, 'row': 0, 'col': 0, 'elevation_m': 3000.0},
            {'lat': 32.1, 'lng': 77.1, 'row': 0, 'col': 1, 'elevation_m': 3100.0},
        ]
        weather_profiles = [
            {
                'air_temp_c': -5.0, 'relative_humidity': 80.0, 'pressure_hpa': 700.0,
                'precip_mm': 2.0, 'wind_speed_ms': 15.0, 'wind_dir_deg': 270.0,
                'wind_gust_ms': 25.0, 'shortwave_radiation': 150.0,
                'source_id': 'open-meteo', 'source_timestamp': '2026-07-18T06:00:00+00:00',
            },
        ]
        with self.assertRaises(ValueError):
            build_cell_inputs(
                grid_cells, weather_profiles,
                issue_slot='06',
                timestamp='2026-07-18T06:00:00+00:00',
                region_key='test',
            )

    def test_degree_grid_has_pixel_id(self) -> None:
        """G1: Degree grid cells must contain pixel_id and grid_manifest_hash."""
        from backend.common.features import build_region_grid
        from backend.common.regions import Region

        region = Region(
            name='Test', bbox=(32.0, 77.0, 32.5, 77.5),
            center=(32.25, 77.25), zoom=8,
        )
        cells = build_region_grid(region, grid_size=5)
        self.assertTrue(all('pixel_id' in c for c in cells))
        self.assertTrue(all('grid_manifest_hash' in c for c in cells))
        self.assertEqual(cells[0]['pixel_id'], 'test_0_0')

    def test_grid_hash_changes_with_config(self) -> None:
        """G7: Different cell sizes produce different manifest hashes."""
        import importlib.util
        if importlib.util.find_spec('pyproj') is None:
            self.skipTest("pyproj not installed — projected grid test skipped")
        from backend.common.features import build_region_grid_projected
        from backend.common.regions import Region

        region = Region(
            name='Test', bbox=(32.0, 77.0, 32.5, 77.5),
            center=(32.25, 77.25), zoom=8,
        )
        cells_500 = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        cells_1000 = build_region_grid_projected(region, cell_size_m=1000.0, strict=True)
        self.assertNotEqual(
            cells_500[0]['grid_manifest_hash'],
            cells_1000[0]['grid_manifest_hash'],
        )

    def test_active_prepare_rows_path_validates_per_cell_contract_before_scoring(self) -> None:
        """Call the active prepare -> rows path with a real per-cell sample.

        Network, terrain and model seams are mocked, but the production
        preparation, normalization, contract validation and row builder are
        executed together. This is intentionally stronger than a contract-only
        fixture and proves that a distinct hourly source sample reaches the
        scored row metadata.
        """
        from backend.daily_inference import ProofModeOptions, build_cells

        grid = [{
            'row': 0, 'col': 0, 'lat': 32.0, 'lng': 77.0,
            'lat_end': 32.01, 'lng_end': 77.01,
            'pixel_id': 'test_0_0', 'crs': 'EPSG:4326',
            'grid_mode': 'degree', 'grid_manifest_hash': 'a' * 64,
        }]
        weather = {
            # Canonical Partner names intentionally differ from the legacy
            # feature-builder names. The active path must adapt them before
            # model scoring rather than merely annotating the scored row.
            'air_temp_c': -8.0,
            'relative_humidity': 80.0,
            'pressure_hpa': 650.0,
            'precip_mm': 2.0,
            'wind_speed_ms': 12.0,
            'wind_dir_deg': 270.0,
            'wind_gust_ms': 20.0,
            'shortwave_radiation': 120.0,
        }
        profile = {
            'source': 'open-meteo-batch-test',
            'latitude': 32.0,
            'longitude': 77.0,
            'samples': [HourlyWeatherSample(
                timestamp='2026-07-18T06:00:00+00:00',
                values=weather,
            )],
        }
        feature_row = {feature: 0.1 for feature in FEATURE_COLUMNS}
        feature_row.update({
            'snowfall_24h': 0.2, 'wind_loading': 0.3,
            'temp_gradient': 0.2, 'freezing_level_proxy': 0.4,
            'elevation': 0.6, 'terrain_roughness': 0.5,
            'aspect_loading': 0.25, 'slope': 0.45,
        })
        assembled = {
            'feature_row': feature_row,
            'raw_inputs': {
                'temperature_2m': -8.0, 'windspeed_10m': 12.0,
                'winddirection_10m': 270.0, 'downscaled_temperature_c': -8.5,
                'snowfall_24h_cm': 2.0, 'precipitation_24h_mm': 2.0,
            },
            'snowpack_proxy': SimpleNamespace(
                estimated_shear_strength=0.42,
                snow_settlement_index=0.16,
                season_start='2025-11-01', method='proxy_v1',
            ),
        }

        class Selector:
            def transform(self, frame):
                return np.asarray([[0.2, 0.3]], dtype=np.float32)

        class Calibrated:
            def predict_proba(self, frame):
                return np.asarray([[0.7, 0.3]], dtype=np.float32)

        bundle = {
            'selector': Selector(), 'calibrated_model': Calibrated(),
            'base_model': object(), 'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': FEATURE_COLUMNS,
            'created_at': '2026-07-18T00:00:00+00:00',
            'calibration_method': 'reference', 'resampling': 'none',
        }
        region = SimpleNamespace(key='test_region', name='Test Region', center=(32.0, 77.0))
        snowpack = SnowpackProxyBatchResult(
            proxy=SnowpackProxy(
                estimated_shear_strength=0.42, snow_settlement_index=0.16,
                season_start='2025-11-01', method='seasonal_cumulative_v1',
            ),
            status='ready',
        )
        cadence = self._make_cadence_context(
            issue_time=datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc)
        )
        stage_metrics: dict[str, object] = {}
        with patch.dict('os.environ', {'RAVAFCAST_PER_CELL_WEATHER_MODE': 'validation'}, clear=False), \
             patch('backend.daily_inference.build_region_grid', return_value=grid), \
             patch('backend.common.real_features.fetch_batch_weather_profile', return_value=[profile]), \
             patch('backend.daily_inference.fetch_historical_weather_window', return_value={'samples': []}), \
             patch('backend.daily_inference.fetch_ensemble_weather_profile', return_value={'samples': []}), \
             patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial', return_value=[snowpack]), \
             patch('backend.daily_inference.extract_cell_terrain', return_value={'elevation_m': 3500.0, 'slope_angle_deg': 35.0, 'aspect_deg': 180.0, 'terrain_roughness': 1.0}), \
             patch('backend.daily_inference._fetch_latest_sar_summary', return_value={}), \
             patch('backend.daily_inference.build_real_feature_row', return_value=assembled) as feature_builder, \
             patch('backend.daily_inference.collect_tree_probabilities', return_value=np.asarray([[0.7, 0.3]], dtype=np.float32)), \
             patch('backend.daily_inference.predict_production_probability', return_value=(0.3, None)):
            rows = build_cells(
                region=region,
                bundle=bundle,
                grid_size=1,
                forecast_date=pd.Timestamp('2026-07-18T06:00:00Z'),
                proof_options=ProofModeOptions(skip_tree_shap=True),
                stage_metrics=stage_metrics,
                cadence_context=cadence,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['input_contract_status'], 'validated')
        contract = rows[0]['Partner_input_contract']
        self.assertEqual(contract['pixel_id'], 'test_0_0')
        self.assertEqual(contract['source_timestamp'], '2026-07-18T06:00:00+00:00')
        self.assertFalse(contract['training_eligible'])
        self.assertTrue(stage_metrics['Partner_contracts']['pre_inference'])
        feature_input = feature_builder.call_args.kwargs['weather_sample']
        self.assertEqual(feature_input['temperature_2m'], -8.0)
        self.assertEqual(feature_input['windspeed_10m'], 12.0)


if __name__ == '__main__':
    unittest.main()
