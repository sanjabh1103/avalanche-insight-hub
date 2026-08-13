"""Partner observation assimilation configuration.

Env-driven config for station registry and assimilation thresholds.
All feeds are disabled-by-default — set env vars to enable.

Env flags:
  PARTNER_STATION_REGISTRY_PATH — JSON file with station list
  PARTNER_MAX_TEMPORAL_DELTA_HOURS — max obs age (default: 6)
  PARTNER_MAX_ELEVATION_DIFF_M — max elevation difference (default: 500)
  PARTNER_MAX_SPATIAL_RADIUS_DEG — max spatial radius in degrees (default: 0.5)
  PARTNER_REQUIRE_REVIEWED — reject unreviewed observations (default: false)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StationRecord:
    """Station metadata from the registry."""
    station_id: str
    latitude: float | None
    longitude: float | None
    elevation_m: float | None
    units: dict[str, str]


def get_station_registry_path() -> str:
    return os.getenv('PARTNER_STATION_REGISTRY_PATH', '')


def get_max_temporal_delta_hours() -> float:
    return float(os.getenv('PARTNER_MAX_TEMPORAL_DELTA_HOURS', '6'))


def get_max_elevation_diff_m() -> float:
    return float(os.getenv('PARTNER_MAX_ELEVATION_DIFF_M', '500'))


def get_max_spatial_radius_deg() -> float:
    return float(os.getenv('PARTNER_MAX_SPATIAL_RADIUS_DEG', '0.5'))


def get_require_reviewed() -> bool:
    return os.getenv('PARTNER_REQUIRE_REVIEWED', 'false').lower() not in {
        '0', 'false', 'off', 'no',
    }


def load_station_registry(path: str | None = None) -> set[str] | None:
    """Load station registry from JSON file.

    Returns a set of station IDs, or None if no path is configured.
    Raises on malformed JSON (fail closed, not silent None).
    """
    registry_path = path or get_station_registry_path()
    if not registry_path:
        return None

    p = Path(registry_path)
    if not p.exists():
        raise FileNotFoundError(f'Station registry file not found: {registry_path}')

    with open(p) as f:
        data = json.load(f)

    if not isinstance(data, dict) or 'stations' not in data:
        raise ValueError(f'Station registry must have a "stations" key: {registry_path}')

    stations = data['stations']
    if not isinstance(stations, list):
        raise ValueError(f'"stations" must be a list: {registry_path}')

    return {s['station_id'] for s in stations if isinstance(s, dict) and 'station_id' in s}


def load_station_registry_with_metadata(path: str | None = None) -> dict[str, StationRecord] | None:
    """Load station registry with full metadata (coordinates, elevation, units).

    Returns a dict mapping station_id to StationRecord, or None if no path is configured.
    Raises on malformed JSON (fail closed, not silent None).
    """
    registry_path = path or get_station_registry_path()
    if not registry_path:
        return None

    p = Path(registry_path)
    if not p.exists():
        raise FileNotFoundError(f'Station registry file not found: {registry_path}')

    with open(p) as f:
        data = json.load(f)

    if not isinstance(data, dict) or 'stations' not in data:
        raise ValueError(f'Station registry must have a "stations" key: {registry_path}')

    stations = data['stations']
    if not isinstance(stations, list):
        raise ValueError(f'"stations" must be a list: {registry_path}')

    result: dict[str, StationRecord] = {}
    for s in stations:
        if not isinstance(s, dict) or 'station_id' not in s:
            continue
        sid = s['station_id']
        result[sid] = StationRecord(
            station_id=sid,
            latitude=float(s['latitude']) if 'latitude' in s and s['latitude'] is not None else None,
            longitude=float(s['longitude']) if 'longitude' in s and s['longitude'] is not None else None,
            elevation_m=float(s['elevation_m']) if 'elevation_m' in s and s['elevation_m'] is not None else None,
            units=s.get('units', {}) if isinstance(s.get('units'), dict) else {},
        )
    return result
