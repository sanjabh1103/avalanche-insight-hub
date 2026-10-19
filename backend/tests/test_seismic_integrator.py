"""Tests for F1 Seismic Cascade Integrator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.common.seismic_integrator import (
    HIMALAYAN_BBOX,
    SEISMIC_AMPLIFICATION_W1,
    SEISMIC_AMPLIFICATION_W2,
    SEISMIC_FLOOR,
    SEISMIC_WINDOW_1_HOURS,
    SEISMIC_WINDOW_2_HOURS,
    ActiveWindow,
    SeismicAmplification,
    SeismicEvent,
    _distance_attenuation,
    _haversine_km,
    apply_seismic_amplification,
    check_active_windows,
    compute_seismic_amplification,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(
    magnitude: float = 5.0,
    lat: float = 34.5,
    lng: float = 76.0,
    hours_ago: float = 5.0,
) -> SeismicEvent:
    return SeismicEvent(
        id='test-001',
        magnitude=magnitude,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        lat=lat,
        lng=lng,
        depth_km=10.0,
        place='Test location',
    )


# ---------------------------------------------------------------------------
# Temporal window tests
# ---------------------------------------------------------------------------


class TestCheckActiveWindows:
    def test_window1_active_at_5h(self):
        event = _make_event(hours_ago=5.0)
        windows = check_active_windows(event)
        assert len(windows) == 1
        assert windows[0].window_phase == 1
        assert windows[0].factor == SEISMIC_AMPLIFICATION_W1

    def test_window1_active_at_boundary_start(self):
        now = datetime.now(timezone.utc)
        event = SeismicEvent(
            id='test-boundary-start',
            magnitude=5.0,
            timestamp=now - timedelta(hours=SEISMIC_WINDOW_1_HOURS[0]),
            lat=34.5,
            lng=76.0,
            depth_km=10.0,
            place='Test',
        )
        windows = check_active_windows(event, now=now)
        assert len(windows) == 1
        assert windows[0].window_phase == 1

    def test_window1_active_at_boundary_end(self):
        now = datetime.now(timezone.utc)
        event = SeismicEvent(
            id='test-boundary',
            magnitude=5.0,
            timestamp=now - timedelta(hours=SEISMIC_WINDOW_1_HOURS[1]),
            lat=34.5,
            lng=76.0,
            depth_km=10.0,
            place='Test',
        )
        windows = check_active_windows(event, now=now)
        assert len(windows) == 1
        assert windows[0].window_phase == 1

    def test_window2_active_at_50h(self):
        event = _make_event(hours_ago=50.0)
        windows = check_active_windows(event)
        assert len(windows) == 1
        assert windows[0].window_phase == 2
        assert windows[0].factor == SEISMIC_AMPLIFICATION_W2

    def test_no_active_window_at_20h(self):
        event = _make_event(hours_ago=20.0)
        windows = check_active_windows(event)
        assert len(windows) == 0

    def test_no_active_window_before_event(self):
        event = _make_event(hours_ago=-1.0)
        windows = check_active_windows(event)
        assert len(windows) == 0

    def test_both_windows_cannot_be_active_simultaneously(self):
        """Windows 1 (2-15h) and 2 (38-76h) don't overlap."""
        for hours in [5, 10, 50, 60]:
            event = _make_event(hours_ago=hours)
            windows = check_active_windows(event)
            assert len(windows) <= 1, f"Two windows active at {hours}h"


# ---------------------------------------------------------------------------
# Distance attenuation tests
# ---------------------------------------------------------------------------


class TestDistanceAttenuation:
    def test_zero_distance_full_factor(self):
        assert _distance_attenuation(0.0, 5.0) == 1.0

    def test_beyond_max_radius_zero(self):
        assert _distance_attenuation(200.0, 5.0) == 0.0

    def test_at_max_radius_zero(self):
        assert _distance_attenuation(150.0, 5.0) == 0.0

    def test_linear_decay(self):
        # At 75km with M5 (max_radius=150km), factor should be 0.5
        assert abs(_distance_attenuation(75.0, 5.0) - 0.5) < 1e-6

    def test_zero_magnitude_zero_factor(self):
        assert _distance_attenuation(10.0, 0.0) == 0.0


class TestHaversine:
    def test_same_point_zero_distance(self):
        assert _haversine_km(34.0, 76.0, 34.0, 76.0) == 0.0

    def test_known_distance(self):
        # Delhi to Chandigarh ~240km
        dist = _haversine_km(28.6139, 77.2090, 30.7333, 76.7794)
        assert 200 < dist < 280


# ---------------------------------------------------------------------------
# Amplification computation tests
# ---------------------------------------------------------------------------


class TestComputeSeismicAmplification:
    def test_no_events_returns_none(self):
        result = compute_seismic_amplification(34.0, 76.0, [])
        assert result is None

    def test_no_active_windows_returns_none(self):
        event = _make_event(hours_ago=20.0)  # Between windows
        result = compute_seismic_amplification(34.0, 76.0, [event])
        assert result is None

    def test_active_window1_near_epicenter(self):
        event = _make_event(magnitude=5.0, lat=34.0, lng=76.0, hours_ago=5.0)
        result = compute_seismic_amplification(34.0, 76.0, [event])
        assert result is not None
        assert result.window_phase == 1
        assert result.factor > 0.0
        assert result.magnitude == 5.0
        assert result.epicenter_distance_km == 0.0

    def test_distance_attenuation_applied(self):
        event = _make_event(magnitude=5.0, lat=34.0, lng=76.0, hours_ago=5.0)
        # Cell 75km away → attenuation = 0.5, factor = 1.3 * 0.5 = 0.65
        result = compute_seismic_amplification(34.0, 76.0 + 0.7, [event])
        assert result is not None
        assert result.factor < SEISMIC_AMPLIFICATION_W1

    def test_picks_highest_factor_event(self):
        near_event = _make_event(magnitude=5.0, lat=34.0, lng=76.0, hours_ago=5.0)
        far_event = _make_event(magnitude=4.5, lat=35.0, lng=77.0, hours_ago=5.0)
        result = compute_seismic_amplification(34.0, 76.0, [far_event, near_event])
        assert result is not None
        assert result.magnitude == 5.0  # Near event wins

    def test_epicenter_coordinates_propagated(self):
        event = _make_event(magnitude=5.0, lat=34.5, lng=76.2, hours_ago=5.0)
        result = compute_seismic_amplification(34.0, 76.0, [event])
        assert result is not None
        assert result.epicenter_lat == 34.5
        assert result.epicenter_lng == 76.2


# ---------------------------------------------------------------------------
# Amplification application tests
# ---------------------------------------------------------------------------


class TestApplySeismicAmplification:
    def test_multiplicative_scaling(self):
        amp = SeismicAmplification(
            factor=1.3,
            window_phase=1,
            hours_since_event=5.0,
            magnitude=5.0,
            epicenter_distance_km=0.0,
            epicenter_lat=34.5,
            epicenter_lng=76.0,
        )
        result = apply_seismic_amplification(0.5, amp)
        assert result == pytest.approx(min(0.5 * 1.3, 1.0))

    def test_floor_applied(self):
        amp = SeismicAmplification(
            factor=0.1,  # Very low factor
            window_phase=1,
            hours_since_event=5.0,
            magnitude=5.0,
            epicenter_distance_km=100.0,
            epicenter_lat=34.5,
            epicenter_lng=76.0,
        )
        result = apply_seismic_amplification(0.3, amp)
        assert result >= 0.3 + SEISMIC_FLOOR

    def test_capped_at_1(self):
        amp = SeismicAmplification(
            factor=10.0,
            window_phase=1,
            hours_since_event=5.0,
            magnitude=8.0,
            epicenter_distance_km=0.0,
            epicenter_lat=34.5,
            epicenter_lng=76.0,
        )
        result = apply_seismic_amplification(0.9, amp)
        assert result == 1.0

    def test_zero_base_risk_with_floor(self):
        amp = SeismicAmplification(
            factor=0.0,
            window_phase=1,
            hours_since_event=5.0,
            magnitude=5.0,
            epicenter_distance_km=200.0,
            epicenter_lat=34.5,
            epicenter_lng=76.0,
        )
        result = apply_seismic_amplification(0.0, amp)
        assert result == pytest.approx(SEISMIC_FLOOR)


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_himalayan_bbox_values(self):
        assert HIMALAYAN_BBOX == (33.0, 73.5, 36.5, 79.0)

    def test_window1_hours(self):
        assert SEISMIC_WINDOW_1_HOURS == (1.97, 14.57)

    def test_window2_hours(self):
        assert SEISMIC_WINDOW_2_HOURS == (38.32, 76.32)

    def test_default_amplification_factors(self):
        assert SEISMIC_AMPLIFICATION_W1 == 1.3
        assert SEISMIC_AMPLIFICATION_W2 == 1.15
