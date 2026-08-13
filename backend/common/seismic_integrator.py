"""Seismic Cascade Integrator — F1

Ingests seismic feeds (USGS FDSNWS API), applies Shekhar et al. 2026 (MAUSAM)
temporal windows for post-tremor avalanche risk amplification.

Two post-tremor risk windows identified by Partner/Partner/CSIO research:
  - Window 1 (acute):    1.97h – 14.57h post-tremor, amplification factor 1.3x
  - Window 2 (delayed): 38.32h – 76.32h post-tremor, amplification factor 1.15x

The amplification is applied as a hybrid multiplicative scaling + seismic floor
on top of the existing terrain-adjusted risk level (IPA-based):
  amplified = min(base_risk * effective_factor, 1.0)
  amplified = max(amplified, base_risk + SEISMIC_FLOOR)

Distance-based attenuation: effective_factor decays with epicenter distance.
  effective_factor = factor * max(0, 1 - distance_km / (magnitude * 30))

Configurable via environment variables:
  SEISMIC_MIN_MAGNITUDE       — minimum earthquake magnitude to query (default: 4.0)
  SEISMIC_AMPLIFICATION_W1    — window 1 multiplicative factor (default: 1.3)
  SEISMIC_AMPLIFICATION_W2    — window 2 multiplicative factor (default: 1.15)
  SEISMIC_FLOOR               — minimum additive risk floor (default: 0.05)
  SEISMIC_HOURS_BACK          — hours of history to query (default: 80)
  SEISMIC_API_TIMEOUT         — USGS API request timeout in seconds (default: 10)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEISMIC_MIN_MAGNITUDE = float(os.getenv('SEISMIC_MIN_MAGNITUDE', '4.0'))
SEISMIC_AMPLIFICATION_W1 = float(os.getenv('SEISMIC_AMPLIFICATION_W1', '1.3'))
SEISMIC_AMPLIFICATION_W2 = float(os.getenv('SEISMIC_AMPLIFICATION_W2', '1.15'))
SEISMIC_FLOOR = float(os.getenv('SEISMIC_FLOOR', '0.05'))
SEISMIC_HOURS_BACK = float(os.getenv('SEISMIC_HOURS_BACK', '80'))
SEISMIC_API_TIMEOUT = float(os.getenv('SEISMIC_API_TIMEOUT', '10'))
GEOPHONE_ENABLED = os.getenv('GEOPHONE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

# Shekhar et al. 2026 temporal windows (hours)
SEISMIC_WINDOW_1_HOURS: tuple[float, float] = (1.97, 14.57)
SEISMIC_WINDOW_2_HOURS: tuple[float, float] = (38.32, 76.32)

# Himalayan bbox — union of 4 F17 region bboxes
HIMALAYAN_BBOX: tuple[float, float, float, float] = (33.0, 73.5, 36.5, 79.0)

USGS_API_URL = 'https://earthquake.usgs.gov/fdsnws/event/1/query'


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeismicEvent:
    """Parsed earthquake event from USGS API."""
    id: str
    magnitude: float
    timestamp: datetime
    lat: float
    lng: float
    depth_km: float
    place: str


@dataclass(frozen=True)
class ActiveWindow:
    """An active post-tremor risk window for a specific event."""
    window_phase: int  # 1 or 2
    hours_since_event: float
    hours_remaining: float
    factor: float  # base amplification factor for this window
    event: SeismicEvent


@dataclass(frozen=True)
class SeismicAmplification:
    """Computed seismic amplification for a specific grid cell."""
    factor: float
    window_phase: int
    hours_since_event: float
    magnitude: float
    epicenter_distance_km: float
    epicenter_lat: float
    epicenter_lng: float
    geophone_spectral_features: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# USGS API client
# ---------------------------------------------------------------------------


def fetch_recent_earthquakes(
    bbox: tuple[float, float, float, float] = HIMALAYAN_BBOX,
    min_magnitude: float = SEISMIC_MIN_MAGNITUDE,
    hours_back: float = SEISMIC_HOURS_BACK,
    *,
    timeout: float = SEISMIC_API_TIMEOUT,
) -> list[SeismicEvent]:
    """Query USGS FDSNWS API for recent earthquakes within a bounding box.

    Args:
        bbox: (min_lat, min_lng, max_lat, max_lng)
        min_magnitude: Minimum earthquake magnitude
        hours_back: How many hours of history to query
        timeout: Request timeout in seconds

    Returns:
        List of parsed SeismicEvent objects. Empty list on error.
    """
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(hours=hours_back)).strftime('%Y-%m-%dT%H:%M:%S')
    end_time = now.strftime('%Y-%m-%dT%H:%M:%S')

    params = {
        'format': 'geojson',
        'starttime': start_time,
        'endtime': end_time,
        'minmagnitude': str(min_magnitude),
        'minlatitude': str(bbox[0]),
        'minlongitude': str(bbox[1]),
        'maxlatitude': str(bbox[2]),
        'maxlongitude': str(bbox[3]),
        'orderby': 'time-asc',
        'limit': '200',
    }

    try:
        response = requests.get(USGS_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f'[seismic] Warning: USGS API query failed: {exc}', file=sys.stderr)
        return []

    events: list[SeismicEvent] = []
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        geom = feature.get('geometry', {})
        coords = geom.get('coordinates', [0, 0, 0])
        if len(coords) < 2:
            continue
        mag = props.get('mag')
        if mag is None:
            continue
        event_time_ms = props.get('time')
        if event_time_ms is None:
            continue
        event_time = datetime.fromtimestamp(event_time_ms / 1000.0, tz=timezone.utc)
        events.append(SeismicEvent(
            id=str(feature.get('id', '')),
            magnitude=float(mag),
            timestamp=event_time,
            lat=float(coords[1]),
            lng=float(coords[0]),
            depth_km=float(coords[2]) if len(coords) > 2 else 0.0,
            place=str(props.get('place', '')),
        ))

    return events


# ---------------------------------------------------------------------------
# Temporal window logic
# ---------------------------------------------------------------------------


def check_active_windows(
    event: SeismicEvent,
    now: datetime | None = None,
) -> list[ActiveWindow]:
    """Check if an event has active post-tremor risk windows.

    Args:
        event: The seismic event to check
        now: Current time (defaults to UTC now)

    Returns:
        List of active windows (may be empty, 1, or 2)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    hours_since = (now - event.timestamp).total_seconds() / 3600.0
    if hours_since < 0:
        return []

    windows: list[ActiveWindow] = []

    # Window 1: acute (1.97 – 14.57h)
    if SEISMIC_WINDOW_1_HOURS[0] <= hours_since <= SEISMIC_WINDOW_1_HOURS[1]:
        hours_remaining = SEISMIC_WINDOW_1_HOURS[1] - hours_since
        windows.append(ActiveWindow(
            window_phase=1,
            hours_since_event=round(hours_since, 2),
            hours_remaining=round(hours_remaining, 2),
            factor=SEISMIC_AMPLIFICATION_W1,
            event=event,
        ))

    # Window 2: delayed (38.32 – 76.32h)
    if SEISMIC_WINDOW_2_HOURS[0] <= hours_since <= SEISMIC_WINDOW_2_HOURS[1]:
        hours_remaining = SEISMIC_WINDOW_2_HOURS[1] - hours_since
        windows.append(ActiveWindow(
            window_phase=2,
            hours_since_event=round(hours_since, 2),
            hours_remaining=round(hours_remaining, 2),
            factor=SEISMIC_AMPLIFICATION_W2,
            event=event,
        ))

    return windows


# ---------------------------------------------------------------------------
# Distance + amplification
# ---------------------------------------------------------------------------


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute great-circle distance in km between two points."""
    r = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance_attenuation(distance_km: float, magnitude: float) -> float:
    """Compute distance-based attenuation factor.

    effective_factor = max(0, 1 - distance / (magnitude * 30))
    A M5.0 event affects cells within 150km; a M7.0 within 210km.
    """
    max_radius = magnitude * 30.0
    if max_radius <= 0:
        return 0.0
    return max(0.0, 1.0 - distance_km / max_radius)


def compute_seismic_amplification(
    cell_lat: float,
    cell_lng: float,
    events: list[SeismicEvent],
    now: datetime | None = None,
) -> SeismicAmplification | None:
    """Compute the seismic amplification for a grid cell.

    Finds the nearest active event and computes the amplification factor
    with distance-based attenuation. If multiple events have active windows,
    the one with the highest effective factor is used.

    Args:
        cell_lat: Cell center latitude
        cell_lng: Cell center longitude
        events: List of recent seismic events
        now: Current time (defaults to UTC now)

    Returns:
        SeismicAmplification if an active window exists, None otherwise.
    """
    if not events:
        return None
    if now is None:
        now = datetime.now(timezone.utc)

    best: SeismicAmplification | None = None
    best_effective_factor = 0.0

    for event in events:
        windows = check_active_windows(event, now)
        if not windows:
            continue

        distance_km = _haversine_km(cell_lat, cell_lng, event.lat, event.lng)
        attenuation = _distance_attenuation(distance_km, event.magnitude)

        for window in windows:
            effective_factor = window.factor * attenuation
            if effective_factor > best_effective_factor:
                best_effective_factor = effective_factor
                best = SeismicAmplification(
                    factor=round(effective_factor, 4),
                    window_phase=window.window_phase,
                    hours_since_event=window.hours_since_event,
                    magnitude=event.magnitude,
                    epicenter_distance_km=round(distance_km, 2),
                    epicenter_lat=event.lat,
                    epicenter_lng=event.lng,
                )

    return best


def apply_seismic_amplification(
    base_risk: float,
    amplification: SeismicAmplification,
) -> float:
    """Apply seismic amplification to a base risk score.

    Hybrid approach:
    1. Multiplicative: amplified = min(base_risk * factor, 1.0)
    2. Seismic floor: amplified = max(amplified, base_risk + SEISMIC_FLOOR)

    The floor captures the physics that seismic events can trigger avalanches
    independent of pre-existing conditions.

    Args:
        base_risk: Base calibrated probability [0, 1]
        amplification: Computed seismic amplification

    Returns:
        Amplified risk score in [0, 1]
    """
    amplified = min(base_risk * amplification.factor, 1.0)
    amplified = max(amplified, base_risk + SEISMIC_FLOOR)
    return min(amplified, 1.0)


# ---------------------------------------------------------------------------
# CLI entry point for GitHub Actions seismic check
# ---------------------------------------------------------------------------


def integrate_geophone_data(
    amplification: SeismicAmplification,
    geophone_readings: list[dict[str, Any]] | None = None,
) -> SeismicAmplification:
    """F11: Integrate geophone spectral features with seismic amplification.

    Combines seismic cascade amplification with geophone spectral analysis
    for combined seismic + acoustic monitoring.

    Args:
        amplification: Existing SeismicAmplification from seismic integrator
        geophone_readings: List of geophone reading dicts with voltage_data, channel_id

    Returns:
        Updated SeismicAmplification with geophone_spectral_features populated
    """
    if not GEOPHONE_ENABLED or not geophone_readings:
        return amplification

    try:
        import numpy as np
        from backend.common.geophone_spectral import (
            GeophoneReading,
            GeophoneArray,
            GeophoneConfig,
            analyze_geophone_reading,
            detect_triangular_spectrum,
            extract_spectral_features,
        )
    except ImportError:
        return amplification

    array = GeophoneArray(GeophoneConfig())
    for reading_dict in geophone_readings:
        voltage = reading_dict.get('voltage_data')
        if voltage is None:
            continue
        voltage_arr = np.array(voltage, dtype=float)
        reading = GeophoneReading(
            timestamp=str(reading_dict.get('timestamp', '')),
            voltage_data=voltage_arr,
            channel_id=str(reading_dict.get('channel_id', 'unknown')),
            sample_rate_hz=float(reading_dict.get('sample_rate_hz', GEOPHONE_SAMPLE_RATE_HZ if 'GEOPHONE_SAMPLE_RATE_HZ' in globals() else 100.0)),
        )
        array.add_channel(reading)

    if not array.channels:
        return amplification

    # Analyze all channels
    spectral_results = array.analyze_all()
    triangular_results = array.detect_triangular_across_channels()

    # Aggregate features
    all_features: list[dict[str, Any]] = []
    any_triangular = False
    max_triangular_confidence = 0.0

    for channel_id, spectral in spectral_results.items():
        detected, confidence = triangular_results.get(channel_id, (False, 0.0))
        features = extract_spectral_features(
            spectral.freqs, spectral.psd,
            triangular_detected=detected,
            triangular_confidence=confidence,
        )
        all_features.append({
            'channel_id': channel_id,
            'dominant_freq': features.dominant_freq,
            'spectral_centroid': features.spectral_centroid,
            'spectral_spread': features.spectral_spread,
            'peak_amplitude': features.peak_amplitude,
            'triangular_detected': features.triangular_detected,
            'triangular_confidence': features.triangular_confidence,
            'freq_band_energies': features.freq_band_energies,
        })
        if detected:
            any_triangular = True
            max_triangular_confidence = max(max_triangular_confidence, confidence)

    # If triangular spectrum detected, boost amplification factor
    boosted_factor = amplification.factor
    if any_triangular:
        boost = 1.0 + max_triangular_confidence * 0.2  # Up to 20% boost
        boosted_factor = min(amplification.factor * boost, 1.0)

    return SeismicAmplification(
        factor=boosted_factor,
        window_phase=amplification.window_phase,
        hours_since_event=amplification.hours_since_event,
        magnitude=amplification.magnitude,
        epicenter_distance_km=amplification.epicenter_distance_km,
        epicenter_lat=amplification.epicenter_lat,
        epicenter_lng=amplification.epicenter_lng,
        geophone_spectral_features={
            'channels_analyzed': len(all_features),
            'triangular_detected': any_triangular,
            'max_triangular_confidence': max_triangular_confidence,
            'channel_features': all_features,
        },
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description='Check recent seismic activity for Himalayan regions')
    parser.add_argument('--check', action='store_true', help='Run check and output JSON trigger result')
    parser.add_argument('--bbox', type=str, default=None, help='Custom bbox as minlat,minlng,maxlat,maxlng')
    args = parser.parse_args()

    bbox = HIMALAYAN_BBOX
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(',')]
        if len(parts) == 4:
            bbox = (parts[0], parts[1], parts[2], parts[3])

    events = fetch_recent_earthquakes(bbox=bbox)

    if not events:
        if args.check:
            print(json.dumps({'trigger': False, 'events': 0, 'reason': 'no_recent_earthquakes'}))
        else:
            print(f'No recent earthquakes (M>={SEISMIC_MIN_MAGNITUDE}) found in Himalayan bbox.')
        return 0

    now = datetime.now(timezone.utc)
    active_count = 0
    for event in events:
        windows = check_active_windows(event, now)
        if windows:
            active_count += 1
            for w in windows:
                print(
                    f'[seismic] M{event.magnitude:.1f} at {event.timestamp.isoformat()}, '
                    f'window {w.window_phase} active ({w.hours_since_event}h since, '
                    f'{w.hours_remaining}h remaining), factor={w.factor}'
                )

    if args.check:
        trigger = active_count > 0
        print(json.dumps({
            'trigger': trigger,
            'events': len(events),
            'active_windows': active_count,
            'reason': 'active_seismic_window' if trigger else 'no_active_windows',
        }))

    return 0


if __name__ == '__main__':
    sys.exit(_main())
