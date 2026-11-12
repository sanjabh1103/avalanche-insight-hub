"""Tests for RAvaFcast cadence contract and issue slot computation."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone, date

from backend.common.ravafcast_cadence import (
    CadenceContract,
    DEFAULT_CADENCE,
    DEFAULT_RUNTIME_CADENCE,
    ForecastCadenceContext,
    build_cadence_context,
    compute_issue_slot,
    compute_valid_window,
    compute_forecast_date,
)


class CadenceContractTests(unittest.TestCase):
    def test_default_cadence_is_six_hour(self) -> None:
        self.assertEqual(DEFAULT_CADENCE.cadence_hours, 6)
        self.assertEqual(DEFAULT_CADENCE.issue_slots, ("00", "06", "12", "18"))
        self.assertEqual(DEFAULT_CADENCE.horizon_hours, 72)

    def test_validate_valid_cadence(self) -> None:
        c = CadenceContract(cadence_hours=6, issue_slots=("00", "06", "12", "18"))
        c.validate()

    def test_validate_invalid_cadence_hours_zero(self) -> None:
        with self.assertRaises(ValueError, msg="cadence_hours must be > 0"):
            CadenceContract(cadence_hours=0).validate()

    def test_validate_invalid_cadence_not_divisor(self) -> None:
        with self.assertRaises(ValueError, msg="must evenly divide 24"):
            CadenceContract(cadence_hours=7, issue_slots=("00",)).validate()

    def test_validate_slot_count_mismatch(self) -> None:
        with self.assertRaises(ValueError, msg="must equal 24 / cadence_hours"):
            CadenceContract(
                cadence_hours=6,
                issue_slots=("00", "06", "12"),
            ).validate()

    def test_validate_invalid_slot_format(self) -> None:
        with self.assertRaises(ValueError, msg="not a valid integer"):
            CadenceContract(
                cadence_hours=6,
                issue_slots=("00", "06", "12", "abc"),
            ).validate()

    def test_validate_slot_out_of_range(self) -> None:
        with self.assertRaises(ValueError, msg="out of range"):
            CadenceContract(
                cadence_hours=6,
                issue_slots=("00", "06", "12", "25"),
            ).validate()

    def test_validate_non_utc_timezone(self) -> None:
        with self.assertRaises(ValueError, msg="Only UTC"):
            CadenceContract(timezone="IST").validate()

    def test_validate_horizon_zero(self) -> None:
        with self.assertRaises(ValueError, msg="horizon_hours must be > 0"):
            CadenceContract(horizon_hours=0).validate()

    def test_runtime_default_is_daily_and_explicit(self) -> None:
        self.assertEqual(DEFAULT_RUNTIME_CADENCE.cadence_hours, 24)
        self.assertEqual(DEFAULT_RUNTIME_CADENCE.issue_slots, ('06',))
        ctx = build_cadence_context(
            issue_time=datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc),
        )
        self.assertEqual(ctx.cadence_hours, 24)
        self.assertEqual(ctx.issue_slot, '06')
        self.assertTrue(ctx.source_as_of_inferred)

    def test_context_rejects_wrong_slot_and_forecast_date(self) -> None:
        common = {
            'issue_time': datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc),
            'forecast_date': date(2026, 7, 18),
            'cadence_hours': 24,
            'valid_from': datetime(2026, 7, 18, 6, tzinfo=timezone.utc),
            'valid_to': datetime(2026, 7, 21, 6, tzinfo=timezone.utc),
            'source_as_of': datetime(2026, 7, 18, 6, tzinfo=timezone.utc),
        }
        with self.assertRaises(ValueError):
            ForecastCadenceContext(issue_slot='12', **common).validate()
        with self.assertRaises(ValueError):
            ForecastCadenceContext(
                issue_slot='06',
                **{**common, 'forecast_date': date(2026, 7, 19)},
            ).validate()

    def test_context_rejects_non_utc_and_inverted_window(self) -> None:
        with self.assertRaises(ValueError):
            build_cadence_context(
                issue_time=datetime(2026, 7, 18, 6, 17),
            )
        common = {
            'issue_time': datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc),
            'forecast_date': date(2026, 7, 18),
            'issue_slot': '06',
            'cadence_hours': 24,
            'valid_from': datetime(2026, 7, 18, 6, tzinfo=timezone.utc),
            'valid_to': datetime(2026, 7, 18, 5, tzinfo=timezone.utc),
            'source_as_of': datetime(2026, 7, 18, 6, tzinfo=timezone.utc),
        }
        with self.assertRaises(ValueError):
            ForecastCadenceContext(**common).validate()


class ComputeIssueSlotTests(unittest.TestCase):
    def test_slot_00_utc(self) -> None:
        dt = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(compute_issue_slot(dt), "00")

    def test_slot_06_at_0617_utc(self) -> None:
        dt = datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc)
        self.assertEqual(compute_issue_slot(dt), "06")

    def test_slot_12_at_1230_utc(self) -> None:
        dt = datetime(2026, 7, 18, 12, 30, tzinfo=timezone.utc)
        self.assertEqual(compute_issue_slot(dt), "12")

    def test_slot_18_at_1845_utc(self) -> None:
        dt = datetime(2026, 7, 18, 18, 45, tzinfo=timezone.utc)
        self.assertEqual(compute_issue_slot(dt), "18")

    def test_slot_18_at_2345_utc(self) -> None:
        dt = datetime(2026, 7, 18, 23, 45, tzinfo=timezone.utc)
        self.assertEqual(compute_issue_slot(dt), "18")

    def test_naive_datetime_rejected(self) -> None:
        dt = datetime(2026, 7, 18, 6, 17)
        with self.assertRaises(ValueError):
            compute_issue_slot(dt)

    def test_daily_cadence_single_slot(self) -> None:
        daily = CadenceContract(cadence_hours=24, issue_slots=("06",))
        dt = datetime(2026, 7, 18, 14, 0, tzinfo=timezone.utc)
        self.assertEqual(compute_issue_slot(dt, daily), "06")


class ComputeValidWindowTests(unittest.TestCase):
    def test_valid_window_for_slot_06(self) -> None:
        base = date(2026, 7, 18)
        valid_from, valid_to = compute_valid_window("06", base_date=base)
        self.assertEqual(valid_from, datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(valid_to, datetime(2026, 7, 21, 6, 0, tzinfo=timezone.utc))

    def test_valid_window_for_slot_00(self) -> None:
        base = date(2026, 7, 18)
        valid_from, valid_to = compute_valid_window("00", base_date=base)
        self.assertEqual(valid_from, datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(valid_to, datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc))

    def test_valid_window_for_slot_18(self) -> None:
        base = date(2026, 7, 18)
        valid_from, valid_to = compute_valid_window("18", base_date=base)
        self.assertEqual(valid_from, datetime(2026, 7, 18, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(valid_to, datetime(2026, 7, 21, 18, 0, tzinfo=timezone.utc))

    def test_valid_window_horizon_24(self) -> None:
        daily = CadenceContract(cadence_hours=24, issue_slots=("06",), horizon_hours=24)
        base = date(2026, 7, 18)
        valid_from, valid_to = compute_valid_window("06", cadence=daily, base_date=base)
        self.assertEqual(valid_to - valid_from, __import__("datetime").timedelta(hours=24))


class ComputeForecastDateTests(unittest.TestCase):
    def test_forecast_date_same_day(self) -> None:
        dt = datetime(2026, 7, 18, 6, 17, tzinfo=timezone.utc)
        self.assertEqual(compute_forecast_date(dt), date(2026, 7, 18))

    def test_forecast_date_midnight(self) -> None:
        dt = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(compute_forecast_date(dt), date(2026, 7, 18))

    def test_forecast_date_naive_rejected(self) -> None:
        dt = datetime(2026, 7, 18, 23, 59)
        with self.assertRaises(ValueError):
            compute_forecast_date(dt)


if __name__ == "__main__":
    unittest.main()
