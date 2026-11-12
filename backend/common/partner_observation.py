"""Normalized partner observation interface.

Provides a unified dataclass for AWS station observations and Partner SNOWPACK
proxies, with quality control, provenance hashing, and review status tracking.
Used to feed pilot data into the inference pipeline with lineage preservation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.common.snowpack_proxy import SnowpackProxy


@dataclass(frozen=True)
class PartnerObservation:
    """A normalized observation from a partner data source.

    Attributes:
        station_id: Identifier for the source station.
        observed_at: ISO timestamp of the observation.
        latitude: Station latitude in decimal degrees.
        longitude: Station longitude in decimal degrees.
        elevation_m: Station elevation in meters.
        values: Measured values keyed by parameter name.
        units: Unit strings keyed by parameter name.
        qc_status: Quality control status ('pass', 'fail', 'unchecked').
        source_hash: SHA-256 hash of station_id + observed_at + values.
        review_status: Scientist review status ('reviewed', 'unreviewed', 'not_required').
        source: Data source identifier ('aws_live_feed', 'Partner_snowpack_1d', etc.).
    """
    station_id: str
    observed_at: str
    latitude: float | None
    longitude: float | None
    elevation_m: float | None
    values: dict[str, float]
    units: dict[str, str]
    qc_status: str
    source_hash: str
    review_status: str
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def station_identity(self) -> dict[str, Any]:
        """Return station identity metadata for downstream traceability."""
        return {
            'station_id': self.station_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'elevation_m': self.elevation_m,
        }


def _compute_source_hash(station_id: str, observed_at: str, values: dict[str, float]) -> str:
    """Compute a deterministic SHA-256 hash for an observation."""
    payload = json.dumps({
        'station_id': station_id,
        'observed_at': observed_at,
        'values': dict(sorted(values.items())),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def normalize_aws_record(raw: dict[str, Any]) -> PartnerObservation | None:
    """Normalize a raw AWS station feed record into a PartnerObservation.

    Returns None if required fields are missing or numeric values are invalid.
    Does NOT default missing numeric fields to 0 — rejects them.
    """
    station_id = str(raw.get('station_id') or '').strip()
    observed_at = str(raw.get('observed_at') or '').strip()
    if not station_id or not observed_at:
        return None

    numeric_fields = {
        'air_temp_c': raw.get('air_temp_c'),
        'snow_depth_cm': raw.get('snow_depth_cm'),
        'snowfall_cm': raw.get('snowfall_cm'),
        'wind_speed_ms': raw.get('wind_speed_ms'),
        'wind_dir_deg': raw.get('wind_dir_deg'),
        'precipitation_mm': raw.get('precipitation_mm'),
    }

    values: dict[str, float] = {}
    for key, raw_val in numeric_fields.items():
        if raw_val is None or raw_val == '':
            continue
        try:
            values[key] = float(raw_val)
        except (TypeError, ValueError):
            return None

    if not values:
        return None

    latitude = None
    longitude = None
    elevation_m = None
    try:
        latitude = float(raw['latitude']) if raw.get('latitude') not in (None, '') else None
    except (TypeError, ValueError, KeyError):
        latitude = None
    try:
        longitude = float(raw['longitude']) if raw.get('longitude') not in (None, '') else None
    except (TypeError, ValueError, KeyError):
        longitude = None
    try:
        elevation_m = float(raw['elevation_m']) if raw.get('elevation_m') not in (None, '') else None
    except (TypeError, ValueError, KeyError):
        elevation_m = None

    units = {
        'air_temp_c': 'celsius',
        'snow_depth_cm': 'cm',
        'snowfall_cm': 'cm',
        'wind_speed_ms': 'm/s',
        'wind_dir_deg': 'degrees',
        'precipitation_mm': 'mm',
    }

    source_hash = _compute_source_hash(station_id, observed_at, values)

    return PartnerObservation(
        station_id=station_id,
        observed_at=observed_at,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        values=values,
        units={k: units.get(k, '') for k in values},
        qc_status='unchecked',
        source_hash=source_hash,
        review_status='unreviewed',
        source='aws_live_feed',
    )


def normalize_snowpack_proxy(
    proxy: SnowpackProxy,
    station_id: str,
    observed_at: str = '',
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    elevation_m: float | None = None,
) -> PartnerObservation | None:
    """Normalize a Partner SNOWPACK proxy into a PartnerObservation.

    Returns None if the proxy has no valid values.
    """
    if not station_id:
        return None

    values: dict[str, float] = {}
    if proxy.estimated_shear_strength is not None:
        try:
            values['estimated_shear_strength_kpa'] = float(proxy.estimated_shear_strength)
        except (TypeError, ValueError):
            pass
    if proxy.snow_settlement_index is not None:
        try:
            values['snow_settlement_index'] = float(proxy.snow_settlement_index)
        except (TypeError, ValueError):
            pass

    if not values:
        return None

    if not observed_at:
        observed_at = proxy.season_start or ''

    source_hash = _compute_source_hash(station_id, observed_at, values)

    return PartnerObservation(
        station_id=station_id,
        observed_at=observed_at,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        values=values,
        units={
            'estimated_shear_strength_kpa': 'kPa',
            'snow_settlement_index': 'unitless',
        },
        qc_status='unchecked',
        source_hash=source_hash,
        review_status='unreviewed',
        source='Partner_snowpack_1d',
    )


def validate_partner_observation(obs: PartnerObservation) -> list[str]:
    """Validate a PartnerObservation for required station metadata.

    Returns a list of validation error strings (empty = valid).
    """
    errors: list[str] = []
    if obs.latitude is None:
        errors.append(f'Station {obs.station_id}: latitude missing')
    if obs.longitude is None:
        errors.append(f'Station {obs.station_id}: longitude missing')
    if obs.elevation_m is None:
        errors.append(f'Station {obs.station_id}: elevation_m missing')
    if not obs.values:
        errors.append(f'Station {obs.station_id}: no measurement values')
    return errors


def validate_observation_against_registry(
    obs: PartnerObservation,
    registry: dict[str, Any] | None,
) -> list[str]:
    """G-06: Validate observation against station registry metadata.

    Checks that:
    - Station ID exists in the registry
    - Observation coordinates match registry coordinates (within spatial radius)
    - Observation elevation matches registry elevation (within tolerance)
    - Observation units are consistent with registry units

    Returns a list of validation error strings (empty = valid).
    If registry is None, returns error (fail-closed — no registry means no validation possible).
    """
    if registry is None:
        return ['Station registry is not configured — observations cannot be validated']

    errors: list[str] = []

    if obs.station_id not in registry:
        errors.append(f'Station {obs.station_id}: not in station registry')
        return errors

    station = registry[obs.station_id]

    # Coordinate check
    if station.latitude is not None and obs.latitude is not None:
        lat_diff = abs(obs.latitude - station.latitude)
        if lat_diff > 1.0:
            errors.append(
                f'Station {obs.station_id}: latitude {obs.latitude} differs from registry {station.latitude} by {lat_diff:.4f}'
            )
    if station.longitude is not None and obs.longitude is not None:
        lon_diff = abs(obs.longitude - station.longitude)
        if lon_diff > 1.0:
            errors.append(
                f'Station {obs.station_id}: longitude {obs.longitude} differs from registry {station.longitude} by {lon_diff:.4f}'
            )

    # Elevation check
    if station.elevation_m is not None and obs.elevation_m is not None:
        elev_diff = abs(obs.elevation_m - station.elevation_m)
        if elev_diff > 500.0:
            errors.append(
                f'Station {obs.station_id}: elevation {obs.elevation_m}m differs from registry {station.elevation_m}m by {elev_diff:.0f}m'
            )

    # Unit consistency check
    if station.units:
        for param, expected_unit in station.units.items():
            if param in obs.units and obs.units[param] != expected_unit:
                errors.append(
                    f'Station {obs.station_id}: unit mismatch for {param} — obs has {obs.units[param]}, registry expects {expected_unit}'
                )

    return errors
