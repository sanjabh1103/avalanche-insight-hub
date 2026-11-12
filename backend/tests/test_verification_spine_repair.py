"""Focused acceptance tests for the evidence-gated verification repair."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.common.observation_contract import (
    ObservationContract,
    QUALITY_VERIFIED,
)


class TestObservationContract(unittest.TestCase):
    def test_serializes_naive_time_as_utc(self) -> None:
        observation = ObservationContract(
            region_key='great_himalaya',
            cell_id='cell_1',
            sensor='weather',
            variable='snow_depth',
            value=1.25,
            unit='m',
            uncertainty=0.2,
            acquisition_time=datetime(2026, 1, 15, 6, 0),
            freshness_hours=3.0,
            quality_state=QUALITY_VERIFIED,
            lineage={'verified': True, 'evidence_ref': 'openmeteo:cell_1'},
        )
        row = observation.to_dict()
        self.assertEqual(row['acquisition_time'], '2026-01-15T06:00:00+00:00')
        self.assertEqual(row['unit'], 'm')
        self.assertTrue(observation.lineage_verified)

    def test_rejects_invalid_numeric_quality_and_identity_fields(self) -> None:
        base = {
            'region_key': 'r',
            'cell_id': 'c',
            'sensor': 'weather',
            'variable': 'snow_depth',
            'value': 1.0,
            'unit': 'm',
            'uncertainty': 0.1,
            'acquisition_time': '2026-01-15T00:00:00Z',
            'freshness_hours': 1.0,
        }
        with self.assertRaises(ValueError):
            ObservationContract(**{**base, 'uncertainty': -1.0})
        with self.assertRaises(ValueError):
            ObservationContract(**{**base, 'freshness_hours': -1.0})
        with self.assertRaises(ValueError):
            ObservationContract(**{**base, 'quality_state': 'unknown'})
        with self.assertRaises(ValueError):
            ObservationContract(**{**base, 'unit': ''})


class TestDailyInferenceEvidenceGates(unittest.TestCase):
    def _packet(self, **overrides):
        packet = {
            'cell_id': 'cell_1',
            'evidence_refs': ['openmeteo:great_himalaya:cell_1'],
            'source_freshness_hours': {'weather': 3.0},
            'has_synthetic_evidence': False,
            'lineage': {
                'verified': True,
                'source_lineage': {
                    'weather': {
                        'reference': 'openmeteo:great_himalaya:cell_1',
                        'verified': True,
                    },
                },
            },
            'data_quality': {
                'lineage_verified': True,
                'freshness_complete': True,
            },
        }
        packet.update(overrides)
        return packet

    def test_cap_gate_allows_complete_real_lineage(self) -> None:
        import backend.daily_inference as daily

        with patch.object(daily, 'VERIFICATION_SPINE_ENABLED', True):
            allowed, reason = daily._evaluate_verification_cap_gate([
                {'verification_packet': self._packet()},
            ])
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_cap_gate_blocks_missing_packet_and_synthetic_evidence(self) -> None:
        import backend.daily_inference as daily

        with patch.object(daily, 'VERIFICATION_SPINE_ENABLED', True):
            allowed_missing, reason_missing = daily._evaluate_verification_cap_gate([])
            allowed_synthetic, reason_synthetic = daily._evaluate_verification_cap_gate([
                {'verification_packet': self._packet(has_synthetic_evidence=True)},
            ])
        self.assertFalse(allowed_missing)
        self.assertIn('lineage', reason_missing or '')
        self.assertFalse(allowed_synthetic)
        self.assertIn('synthetic', reason_synthetic or '')

    def test_cap_gate_labels_disabled_spine_as_legacy_compatibility(self) -> None:
        import backend.daily_inference as daily

        with patch.object(daily, 'VERIFICATION_SPINE_ENABLED', False):
            allowed, reason = daily._evaluate_verification_cap_gate([])
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_observation_persistence_uses_append_table_and_legacy_cache(self) -> None:
        import backend.daily_inference as daily

        cell = {
            'cell_id': 'cell_1',
            'weather_inputs': {'snow_depth_cm': 125.0},
            'verification_packet': {
                'packet_version': 'v1',
                'has_synthetic_evidence': False,
                'source_freshness_hours': {'weather': 3.0},
                'data_quality': {'observation_kind': 'advisory_cover_event_evidence'},
                'lineage': {
                    'source_lineage': {
                        'weather': {
                            'reference': 'openmeteo:great_himalaya:cell_1',
                            'verified': True,
                        },
                    },
                    'source_observations': [{
                        'sensor': 'weather',
                        'variable': 'snow_depth',
                        'value': 1.25,
                        'unit': 'm',
                        'uncertainty': 0.2,
                        'acquisition_time': '2026-01-15T06:00:00Z',
                    }],
                },
            },
        }
        with patch.object(daily, 'VERIFICATION_SPINE_ENABLED', True), \
             patch.object(daily, 'has_supabase_credentials', return_value=True), \
             patch.object(daily, 'rest_insert', return_value=[]) as insert, \
             patch.object(daily, 'rest_upsert', return_value=[]) as upsert:
            daily._persist_sensor_observations(
                region_key='great_himalaya',
                cells=[cell],
                run_timestamp=datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc),
            )

        insert.assert_called_once()
        self.assertEqual(insert.call_args.args[0], 'verification_observations')
        self.assertEqual(insert.call_args.kwargs['returning'], 'minimal')
        inserted_row = insert.call_args.args[1][0]
        self.assertEqual(inserted_row['quality_state'], 'verified')
        self.assertEqual(inserted_row['lineage']['evidence_ref'], 'openmeteo:great_himalaya:cell_1')
        upsert.assert_called_once()
        self.assertEqual(upsert.call_args.args[0], 'verification_baselines')

    def test_physics_callbacks_use_cached_forcing_and_terrain(self) -> None:
        import backend.daily_inference as daily

        forcing = daily._build_cached_physics_forcing(
            weather_profile={
                'sample': SimpleNamespace(values={
                    'snowfall_24h_cm': 12.0,
                    'windspeed_10m': 30.0,
                    'temp_gradient': 0.3,
                }),
            },
            history_profile={
                'samples': [SimpleNamespace(
                    values={'temperature_2m': -8.0},
                    timestamp='2026-01-14T00:00:00+00:00',
                )],
            },
            terrain_by_coord={(35.5, 76.75): {
                'elevation_m': 4200.0,
                'slope_angle_deg': 38.0,
                'aspect_deg': 180.0,
            }},
            forecast_time=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(forcing['status'], 'cached_weather_history')
        self.assertEqual(len(forcing['weather_history_fn'](35.5, 76.75)), 1)
        self.assertEqual(forcing['weather_inputs_fn'](35.5, 76.75)['snowfall_24h'], 12.0)
        terrain = forcing['terrain_inputs_fn'](35.5, 76.75)
        self.assertEqual(terrain['slope_angle_deg'], 38.0)
        self.assertGreater(terrain['elevation'], 0.0)

    def test_cell_history_is_batched_once_per_region_and_keeps_legacy_fallback(self) -> None:
        import backend.daily_inference as daily

        daily._REGION_SENSOR_HISTORY_CACHE.clear()
        self.addCleanup(daily._REGION_SENSOR_HISTORY_CACHE.clear)

        observation_rows = [
            {
                'cell_id': 'cell_1',
                'acquisition_time': f'2026-01-{day:02d}T00:00:00Z',
                'value': 1.0 + day / 100.0,
                'unit': 'm',
            }
            for day in range(1, 6)
        ]

        def fake_rest_get(table, params=None):
            if table == 'verification_observations':
                return observation_rows
            if table == 'forecast_grids':
                return [{
                    'forecast_date': '2026-01-01',
                    'cells': [{
                        'cell_id': 'cell_2',
                        'weather_inputs': {'snow_depth_cm': 150.0},
                    }],
                }]
            raise AssertionError(f'unexpected table: {table}')

        with patch.object(daily, 'has_supabase_credentials', return_value=True), \
             patch.object(daily, 'rest_get', side_effect=fake_rest_get) as rest:
            cell_1_history = daily._fetch_cell_sensor_history('region_a', 'cell_1', 'weather')
            cell_2_history = daily._fetch_cell_sensor_history('region_a', 'cell_2', 'weather')
            daily._fetch_cell_sensor_history('region_a', 'cell_1', 'weather')

        self.assertEqual(len(cell_1_history), 5)
        self.assertEqual(cell_1_history[0][1], 1.01)
        self.assertEqual(cell_2_history, [(datetime(2026, 1, 1), 1.5)])
        self.assertEqual(rest.call_count, 2)


class TestRepairMigrationAndLineage(unittest.TestCase):
    def test_malformed_gee_scene_time_is_skipped_per_scene(self) -> None:
        import backend.gee_extractor as gee

        self.assertIsNone(gee._normalise_scene_acquisition_time('not-a-time'))
        self.assertEqual(
            gee._normalise_scene_acquisition_time(1768435200000),
            '2026-01-15T00:00:00+00:00',
        )

    def test_migration_is_append_only_and_queue_reads_are_scientist_only(self) -> None:
        migration = Path(__file__).resolve().parents[2] / 'supabase/migrations/20260713160000_verification_spine_repair.sql'
        sql = migration.read_text(encoding='utf-8').lower()
        self.assertIn('create table if not exists public.verification_observations', sql)
        self.assertIn('before update or delete on public.verification_observations', sql)
        self.assertIn('uq_verification_review_queue_region_cell', sql)
        self.assertIn('using (public.is_scientist_or_admin())', sql)
        self.assertIn('create policy "service role insert verification observations"', sql)
        self.assertNotIn('create policy "anyone can view verification review queue"', sql)

    def test_gee_scene_lineage_is_batched_with_conflict_key(self) -> None:
        import backend.gee_extractor as gee

        with patch.object(gee, 'has_supabase_credentials', return_value=True), \
             patch.object(gee, 'rest_upsert', return_value=[{'scene_id': 'S1'}]) as upsert:
            rows = gee._persist_scene_lineage(
                region_key='great_himalaya',
                sensor='sentinel1_gee',
                scene_ids=['S1', 'S2'],
                orbits=['ASCENDING', 'DESCENDING'],
                acquisition_times=['2026-01-15T00:00:00+00:00', '2026-01-16T00:00:00+00:00'],
            )

        upsert.assert_called_once()
        self.assertEqual(upsert.call_args.args[0], 'remote_sensing_scenes')
        self.assertEqual(upsert.call_args.kwargs['on_conflict'], 'region_key,sensor,scene_id')
        self.assertEqual(len(upsert.call_args.args[1]), 2)
        self.assertTrue(all(row['metadata']['persisted'] for row in rows))

    def test_gee_scene_lineage_dry_run_does_not_mutate_remote_table(self) -> None:
        import backend.gee_extractor as gee

        with patch.object(gee, 'has_supabase_credentials', return_value=True), \
             patch.object(gee, 'rest_upsert') as upsert:
            rows = gee._persist_scene_lineage(
                region_key='himalayas_nepal',
                sensor='sentinel1_gee',
                scene_ids=['S1'],
                persist=False,
            )

        upsert.assert_not_called()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['metadata']['persisted'])
        self.assertEqual(rows[0]['metadata']['persistence_mode'], 'dry_run')

    def test_gee_scene_lineage_hash_is_deterministic_and_requires_times(self) -> None:
        import backend.gee_extractor as gee

        first = gee._scene_lineage_sha256(
            region_key='great_himalaya',
            scene_ids=['S1', 'S2'],
            acquisition_times=['2026-01-15T00:00:00+00:00', '2026-01-16T00:00:00+00:00'],
        )
        second = gee._scene_lineage_sha256(
            region_key='great_himalaya',
            scene_ids=['S1', 'S2'],
            acquisition_times=['2026-01-15T00:00:00+00:00', '2026-01-16T00:00:00+00:00'],
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertIsNone(gee._scene_lineage_sha256(
            region_key='great_himalaya', scene_ids=['S1'], acquisition_times=[],
        ))


class TestBoundedSatelliteIngestion(unittest.TestCase):
    def test_s2_batch_deduplicates_cells_and_reuses_session(self) -> None:
        import backend.common.sentinel2_snow_mapper as s2

        fake_session = object()
        mapped = []

        def fake_map(**kwargs):
            mapped.append(kwargs)
            return s2.S2SnowResult(cell_id=kwargs['cell_id'], scene_id='S2-SCENE')

        with patch.object(s2, 'S2_SNOW_ENABLED', True), \
             patch.object(s2, '_has_credentials', return_value=True), \
             patch.object(s2, '_get_gee_session', return_value=fake_session), \
             patch.object(s2, 'map_s2_snow_for_cell', side_effect=fake_map), \
             patch.object(s2, 'S2_MAX_CELLS', 2):
            results = s2.map_s2_snow_batch(
                cells=[
                    {'cell_id': 'c1', 'lat': 28.0, 'lng': 86.0},
                    {'cell_id': 'c1', 'lat': 28.0, 'lng': 86.0},
                    {'cell_id': 'c2', 'lat': 28.1, 'lng': 86.1},
                    {'cell_id': 'c3', 'lat': 28.2, 'lng': 86.2},
                ],
                target_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            )

        self.assertEqual(set(results), {'c1', 'c2'})
        self.assertEqual(len(mapped), 2)
        self.assertTrue(all(call['gee_session'] is fake_session for call in mapped))

    def test_s2_source_uses_official_probability_band(self) -> None:
        source = Path(__file__).resolve().parents[1] / 'common/sentinel2_snow_mapper.py'
        text = source.read_text(encoding='utf-8')
        self.assertIn("select('probability')", text)
        self.assertNotIn("select('cloud_probability')", text)
        self.assertIn("'cloud_mask_band': 'probability'", text)

    def test_gibs_batch_caches_duplicate_tile_requests(self) -> None:
        import backend.common.gibs_ingestion as gibs

        cached = gibs.GibsSnowCoverResult(
            lat=28.0,
            lng=86.0,
            date='2026-01-15',
            snow_cover_fraction=0.7,
            tile_url='https://example.test/tile.png',
        )
        with patch.object(gibs, 'GIBS_ENABLED', True), \
             patch.object(gibs, 'fetch_gibs_snow_cover', return_value=cached) as fetch:
            results = gibs.fetch_gibs_snow_cover_batch(
                [(28.0, 86.0), (28.0, 86.0), (34.0, 76.0)],
                target_date='2026-01-15',
            )
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[1].lat, 28.0)

    def test_gibs_reuses_successful_tile_across_batches(self) -> None:
        import backend.common.gibs_ingestion as gibs

        gibs._GIBS_TILE_CACHE.clear()
        self.addCleanup(gibs._GIBS_TILE_CACHE.clear)
        with patch.object(gibs, 'GIBS_ENABLED', True), \
             patch.object(gibs.urllib.request, 'urlopen', return_value=BytesIO(b'png')) as urlopen, \
             patch.object(gibs, '_compute_snow_fraction_from_tile', return_value=0.7):
            first = gibs.fetch_gibs_snow_cover_batch(
                [(28.0, 86.0)], target_date='2026-01-15'
            )
            second = gibs.fetch_gibs_snow_cover_batch(
                [(28.1, 86.1)], target_date='2026-01-15'
            )

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(first[0].snow_cover_fraction, 0.7)
        self.assertEqual(second[0].lat, 28.1)

    def test_advanced_outputs_are_shadow_only_without_promotion_evidence(self) -> None:
        from backend.common.shadow_promotion import evaluate_shadow_promotion

        status = evaluate_shadow_promotion('PINN', feature_enabled=True)
        self.assertTrue(status.shadow_only)
        self.assertIn('external_calibration_missing', status.reason)

    def test_promotion_requires_all_explicit_evidence_gates(self) -> None:
        from backend.common.shadow_promotion import evaluate_shadow_promotion

        blocked = evaluate_shadow_promotion(
            'NISAR',
            feature_enabled=True,
            external_calibrated=True,
            held_out_validated=True,
            promotion_gate_passed=False,
        )
        promoted = evaluate_shadow_promotion(
            'NISAR',
            feature_enabled=True,
            external_calibrated=True,
            held_out_validated=True,
            promotion_gate_passed=True,
        )
        self.assertTrue(blocked.shadow_only)
        self.assertFalse(promoted.shadow_only)

    def test_pinn_fusion_ignores_unpromoted_depth(self) -> None:
        import backend.common.snow_depth_fusion as fusion
        import backend.common.fusion_engine as engine

        with patch.object(fusion, 'SNOW_DEPTH_FUSION_ENABLED', True), \
             patch.object(engine, 'VERIFICATION_SPINE_ENABLED', True), \
             patch.object(fusion, 'PINN_ENABLED', False), \
             patch.object(fusion, 'PINN_EXTERNAL_CALIBRATED', False), \
             patch.object(fusion, 'PINN_HELD_OUT_VALIDATED', False), \
             patch.object(fusion, 'PINN_PROMOTION_GATE_PASSED', False):
            result = fusion.fuse_snow_depths(
                s1_depth_m=0.5,
                ml_depth_m=0.6,
                pinn_depth_m=4.0,
            )
        self.assertNotIn('pinn_snowpack', result.contributing_sensors)
        self.assertLess(result.snow_depth_m or 0.0, 1.0)


class TestWorkflowEntrypoints(unittest.TestCase):
    def test_cli_dry_run_entrypoints_are_dispatch_safe(self) -> None:
        from scripts.run_anomaly_check import main as anomaly_main
        from scripts.run_gibs_snow import main as gibs_main
        from scripts.run_s2_snow import main as s2_main

        self.assertEqual(gibs_main(['--dry-run', '--date', '2026-01-15', '--region-key', 'great_himalaya_nw_himalaya']), 0)
        self.assertEqual(s2_main(['--dry-run', '--date', '2026-01-15', '--region-key', 'great_himalaya_nw_himalaya']), 0)
        self.assertEqual(anomaly_main(['--dry-run']), 0)

    def test_anomaly_entrypoint_accepts_configured_input_bundle(self) -> None:
        from scripts.run_anomaly_check import main as anomaly_main

        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / 'observations.json'
            input_path.write_text(json.dumps({'cells': []}), encoding='utf-8')
            with patch('scripts.run_anomaly_check.has_supabase_credentials', return_value=False):
                self.assertEqual(anomaly_main(['--input', str(input_path)]), 0)

    def test_anomaly_workflow_uses_safe_variable_path_validation(self) -> None:
        workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/ml_pipeline.yml').read_text(encoding='utf-8')
        self.assertIn('vars.ANOMALY_INPUT_PATH', workflow)
        self.assertIn("ANOMALY_INPUT_PATH must be a relative repository path", workflow)
        self.assertIn("scripts/run_anomaly_check.py --dry-run", workflow)

    def test_workflow_dispatch_uses_real_entrypoint_scripts(self) -> None:
        workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/ml_pipeline.yml').read_text(encoding='utf-8')
        manual_workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/ml_pipeline_manual.yml').read_text(encoding='utf-8')
        self.assertIn("mode == 'gibs'", manual_workflow)
        self.assertIn("scripts/run_gibs_snow.py", manual_workflow)
        self.assertIn("mode == 's2_snow'", workflow)
        self.assertIn("scripts/run_s2_snow.py", workflow)
        self.assertIn("mode == 'anomaly_check'", workflow)
        self.assertIn("scripts/run_anomaly_check.py", workflow)


if __name__ == '__main__':
    unittest.main()
