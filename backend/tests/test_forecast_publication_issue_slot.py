"""Tests for forecast_publication issue_slot and cadence field persistence.

G10 fix: mocks match real signatures (accepting **kwargs). No try/except: pass.
Assert successful return values and captured DB payloads.
"""
from __future__ import annotations

import unittest
import gzip
import json
from unittest.mock import patch
from datetime import datetime, timezone

from backend.common.ravafcast_cadence import (
    ForecastCadenceContext,
    build_cadence_context,
)


class ForecastPublicationIssueSlotTests(unittest.TestCase):

    def test_publish_forecast_run_accepts_issue_slot(self) -> None:
        from backend.common.forecast_publication import publish_forecast_run
        import inspect
        sig = inspect.signature(publish_forecast_run)
        self.assertIn('issue_slot', sig.parameters)
        self.assertIn('cadence_hours', sig.parameters)
        self.assertIn('valid_from', sig.parameters)
        self.assertIn('valid_to', sig.parameters)
        self.assertIn('source_as_of', sig.parameters)
        self.assertEqual(sig.parameters['issue_slot'].default, '06')
        self.assertEqual(sig.parameters['cadence_hours'].default, 24)

    def test_publish_forecast_run_passes_issue_slot_to_insert(self) -> None:
        from backend.common.forecast_publication import publish_forecast_run
        captured: list[dict] = []

        def mock_insert(table, rows, **kwargs):
            captured.extend(rows)
            return [{'id': 'test-uuid-123'}]

        with patch('backend.common.forecast_publication.rest_insert', side_effect=mock_insert), \
             patch('backend.common.forecast_publication.storage_upload_bytes', return_value='s://t'), \
             patch('backend.common.forecast_publication.storage_upsert_json', return_value='s://m'), \
             patch('backend.common.forecast_publication.patch_row_by_id', return_value=None), \
             patch('backend.common.forecast_publication.rest_rpc', return_value=None), \
             patch('backend.common.forecast_publication._record_event'), \
             patch('backend.common.forecast_publication._research_gate_enabled', return_value=False):
            result = publish_forecast_run(
                hazard_type='avalanche', region_key='pir_panjal', region_name='Pir Panjal',
                forecast_date='2026-07-18', horizon_hours=72, grid_size=20,
                bbox=[32.0, 77.0, 32.5, 77.5], status='ready',
                weather_summary={}, forecast_bulletins={}, model_metadata={},
                hourly_grids=[[{'status': 'ready'}]], runout_polygons=[],
                issue_slot='06', cadence_hours=24,
            )
        self.assertIsInstance(result, dict)
        self.assertTrue(captured)
        self.assertEqual(captured[0]['issue_slot'], '06')
        self.assertEqual(captured[0]['cadence_hours'], 24)
        self.assertEqual(captured[0]['valid_from'], '2026-07-18T06:00:00+00:00')
        self.assertEqual(captured[0]['valid_to'], '2026-07-21T06:00:00+00:00')
        self.assertEqual(captured[0]['source_as_of'], captured[0]['issue_time'])

    def test_six_hour_slot_persisted_correctly(self) -> None:
        from backend.common.forecast_publication import publish_forecast_run
        captured: list[dict] = []

        def mock_insert(table, rows, **kwargs):
            captured.extend(rows)
            return [{'id': 'test-uuid-456'}]

        with patch('backend.common.forecast_publication.rest_insert', side_effect=mock_insert), \
             patch('backend.common.forecast_publication.storage_upload_bytes', return_value='s://t'), \
             patch('backend.common.forecast_publication.storage_upsert_json', return_value='s://m'), \
             patch('backend.common.forecast_publication.patch_row_by_id', return_value=None), \
             patch('backend.common.forecast_publication.rest_rpc', return_value=None), \
             patch('backend.common.forecast_publication._record_event'), \
             patch('backend.common.forecast_publication._research_gate_enabled', return_value=False):
            result = publish_forecast_run(
                hazard_type='avalanche', region_key='pir_panjal', region_name='Pir Panjal',
                forecast_date='2026-07-18', horizon_hours=72, grid_size=20,
                bbox=[32.0, 77.0, 32.5, 77.5], status='ready',
                weather_summary={}, forecast_bulletins={}, model_metadata={},
                hourly_grids=[[{'status': 'ready'}]], runout_polygons=[],
                issue_slot='12', cadence_hours=6,
                valid_from='2026-07-18T12:00:00+00:00',
                valid_to='2026-07-21T12:00:00+00:00',
            )
        self.assertIsInstance(result, dict)
        self.assertTrue(captured)
        self.assertEqual(captured[0]['issue_slot'], '12')
        self.assertEqual(captured[0]['cadence_hours'], 6)
        self.assertEqual(captured[0]['valid_from'], '2026-07-18T12:00:00+00:00')
        self.assertEqual(captured[0]['valid_to'], '2026-07-21T12:00:00+00:00')

    def test_unsupported_cadence_is_rejected_before_db_write(self) -> None:
        from backend.common.forecast_publication import publish_forecast_run

        with self.assertRaises(ValueError):
            publish_forecast_run(
                hazard_type='avalanche', region_key='test', region_name='Test',
                forecast_date='2026-07-18', horizon_hours=72, grid_size=20,
                bbox=[32.0, 77.0, 32.5, 77.5], status='ready',
                weather_summary={}, forecast_bulletins={}, model_metadata={},
                hourly_grids=[[{'status': 'ready'}]], runout_polygons=[],
                cadence_hours=12,
            )

    def test_hour_valid_time_uses_valid_from_and_manifest_marks_inference(self) -> None:
        from backend.common.forecast_publication import publish_forecast_run
        uploaded: list[bytes] = []
        manifests: list[dict] = []

        def mock_insert(table, rows, **kwargs):
            return [{'id': 'test-valid-time'}]

        def mock_upload(*, payload, **kwargs):
            uploaded.append(payload)
            return 's://hour'

        def mock_manifest(*, payload, **kwargs):
            manifests.append(payload)
            return 's://manifest'

        with patch('backend.common.forecast_publication.rest_insert', side_effect=mock_insert), \
             patch('backend.common.forecast_publication.storage_upload_bytes', side_effect=mock_upload), \
             patch('backend.common.forecast_publication.storage_upsert_json', side_effect=mock_manifest), \
             patch('backend.common.forecast_publication.patch_row_by_id', return_value=None), \
             patch('backend.common.forecast_publication.rest_rpc', return_value=None), \
             patch('backend.common.forecast_publication._record_event'), \
             patch('backend.common.forecast_publication._research_gate_enabled', return_value=False):
            result = publish_forecast_run(
                hazard_type='avalanche', region_key='test', region_name='Test',
                forecast_date='2026-07-18', horizon_hours=72, grid_size=20,
                bbox=[32.0, 77.0, 32.5, 77.5], status='ready',
                weather_summary={}, forecast_bulletins={}, model_metadata={},
                hourly_grids=[[{'status': 'ready'}], [{'status': 'ready'}]], runout_polygons=[],
                issue_slot='06', cadence_hours=24,
                valid_from='2026-07-18T06:00:00+00:00',
                valid_to='2026-07-21T06:00:00+00:00',
                issue_time='2026-07-18T06:17:00+00:00',
            )

        self.assertIsInstance(result, dict)
        first_hour = json.loads(gzip.decompress(uploaded[0]).decode('utf-8'))
        second_hour = json.loads(gzip.decompress(uploaded[1]).decode('utf-8'))
        self.assertEqual(first_hour['valid_time'], '2026-07-18T06:00:00+00:00')
        self.assertEqual(second_hour['valid_time'], '2026-07-18T07:00:00+00:00')
        self.assertTrue(manifests)
        self.assertTrue(manifests[0]['sourceAsOfInferred'])


class ForecastCadenceContextTests(unittest.TestCase):

    def test_default_cadence_is_daily(self) -> None:
        ctx = build_cadence_context()
        self.assertEqual(ctx.cadence_hours, 24)
        self.assertEqual(ctx.issue_slot, '06')

    def test_six_hour_cadence(self) -> None:
        import os
        os.environ['RAVAFCAST_CADENCE_HOURS'] = '6'
        try:
            ctx = build_cadence_context()
            self.assertEqual(ctx.cadence_hours, 6)
            self.assertIn(ctx.issue_slot, ('00', '06', '12', '18'))
        finally:
            del os.environ['RAVAFCAST_CADENCE_HOURS']

    def test_invalid_cadence_rejected(self) -> None:
        import os
        os.environ['RAVAFCAST_CADENCE_HOURS'] = '12'
        try:
            with self.assertRaises(ValueError) as cm:
                build_cadence_context()
            self.assertIn('6 or 24', str(cm.exception))
        finally:
            del os.environ['RAVAFCAST_CADENCE_HOURS']

    def test_naive_issue_time_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_cadence_context(issue_time=datetime(2026, 7, 18, 12, 0, 0))

    def test_context_validate_passes(self) -> None:
        ctx = build_cadence_context()
        ctx.validate()

    def test_context_valid_to_after_valid_from(self) -> None:
        ctx = build_cadence_context()
        self.assertGreater(ctx.valid_to, ctx.valid_from)

    def test_deterministic_issue_time_from_context(self) -> None:
        """G4: Replaying same cadence context produces identical issue_time."""
        from datetime import timezone as _tz
        fixed_dt = datetime(2026, 7, 18, 6, 17, tzinfo=_tz.utc)
        ctx = build_cadence_context(issue_time=fixed_dt)
        self.assertEqual(ctx.issue_time, fixed_dt)
        self.assertEqual(ctx.source_as_of, fixed_dt)

    def test_publish_uses_context_issue_time(self) -> None:
        """G4: publish_forecast_run uses passed issue_time, not wall-clock."""
        from backend.common.forecast_publication import publish_forecast_run
        captured: list[dict] = []

        def mock_insert(table, rows, **kwargs):
            captured.extend(rows)
            return [{'id': 'test-uuid-replay'}]

        fixed_iso = '2026-07-18T06:17:00+00:00'
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
                issue_slot='06', cadence_hours=24,
                issue_time=fixed_iso,
            )
        self.assertEqual(captured[0]['issue_time'], fixed_iso)


if __name__ == '__main__':
    unittest.main()
