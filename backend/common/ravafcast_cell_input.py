"""RAvaFcast per-cell input contract — PartnerCellInputContract.

Defines the typed contract for per-cell forecast inputs including identity,
spatial, weather, snow, terrain, provenance, and window fields.

This is a contract module only — no ML logic, no network calls, no DB access.
The contract enforces:
- Required fields are present
- Latitude/longitude are in valid range
- window_type is one of the approved enum values
- training_eligible defaults to False (no automatic historical-event training)
- Missing data in validated lane fails closed; technical-reference records fallback
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


VALID_WINDOW_TYPES = ("instantaneous", "six_hour_aggregate", "twenty_four_hour_rolling")


def _validate_iso_timestamp(value: str, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label}: timestamp must include UTC offset")


def normalize_weather_sample(
    sample: dict[str, Any],
    *,
    fallback_timestamp: str,
    source_id: str = 'open-meteo',
) -> dict[str, Any]:
    """Map an hourly source sample into the canonical Partner weather schema.

    Open-Meteo uses source-specific names (for example ``temperature_2m``),
    while the Partner contract is deliberately source-neutral. Missing required
    values are marked ``partial`` instead of being presented as complete data;
    the validation lane can then fail closed before model scoring.
    """
    aliases = {
        'air_temp_c': ('air_temp_c', 'temperature_2m'),
        'relative_humidity': ('relative_humidity', 'relativehumidity_2m', 'relative_humidity_2m'),
        'pressure_hpa': ('pressure_hpa', 'pressure_msl', 'surface_pressure'),
        'precip_mm': ('precip_mm', 'precipitation', 'precipitation_24h', 'precipitation_24h_mm'),
        'wind_speed_ms': ('wind_speed_ms', 'windspeed_10m'),
        'wind_dir_deg': ('wind_dir_deg', 'winddirection_10m'),
        'wind_gust_ms': ('wind_gust_ms', 'windgusts_10m'),
        'shortwave_radiation': ('shortwave_radiation', 'shortwave_radiation_instant'),
    }
    normalized: dict[str, Any] = {}
    missing: list[str] = []
    for canonical, candidates in aliases.items():
        value = next((sample.get(key) for key in candidates if sample.get(key) is not None), None)
        if value is None:
            missing.append(canonical)
            value = 0.0
        normalized[canonical] = value
    normalized.update({
        'source_id': str(sample.get('source_id') or source_id),
        'source_timestamp': str(sample.get('time') or sample.get('timestamp') or fallback_timestamp),
        'retrieval_time': str(sample.get('retrieval_time') or fallback_timestamp),
        'missingness': 'partial' if missing else 'complete',
        'missing_fields': missing,
        'fallback': bool(sample.get('fallback', False)),
    })
    return normalized


def to_feature_weather_sample(
    normalized: dict[str, Any],
    *,
    original: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt a validated Partner sample to the existing feature-builder schema.

    The model feature builder intentionally retains its Open-Meteo-compatible
    field names.  This adapter makes the Partner contract authoritative without
    changing that legacy feature API: canonical values are copied into the
    exact keys consumed by ``build_real_feature_row`` and lineage fields are
    retained for replay/audit.  ``original`` is copied only for optional
    pressure-level and snow fields that are not part of the minimum contract.
    """
    feature_sample: dict[str, Any] = dict(original or {})
    aliases = {
        'air_temp_c': 'temperature_2m',
        'relative_humidity': 'relativehumidity_2m',
        'pressure_hpa': 'surface_pressure',
        'precip_mm': 'precipitation_24h',
        'wind_speed_ms': 'windspeed_10m',
        'wind_dir_deg': 'winddirection_10m',
        'wind_gust_ms': 'windgusts_10m',
        'shortwave_radiation': 'shortwave_radiation',
    }
    for canonical, feature_key in aliases.items():
        if canonical in normalized:
            feature_sample[feature_key] = normalized[canonical]
    for key in (
        'source_id', 'source_timestamp', 'retrieval_time', 'missingness',
        'missing_fields', 'fallback',
    ):
        if key in normalized:
            feature_sample[key] = normalized[key]
    return feature_sample


@dataclass(frozen=True)
class PartnerCellInputContract:
    """Typed contract for a single cell's forecast input."""

    # Identity
    region_key: str
    pixel_id: str
    row: int
    col: int
    timestamp: str  # ISO 8601
    issue_slot: str  # e.g. "06"

    # Spatial
    latitude: float
    longitude: float
    elevation_m: float
    crs: str  # e.g. "EPSG:4326"

    # Weather (required)
    air_temp_c: float
    relative_humidity: float
    pressure_hpa: float
    precip_mm: float
    wind_speed_ms: float
    wind_dir_deg: float
    wind_gust_ms: float
    shortwave_radiation: float

    # Snow (optional — None when not supplied)
    snow_depth_m: float | None = None
    swe_mm: float | None = None
    snow_temp_c: float | None = None

    # Terrain
    slope_deg: float = 0.0
    aspect_deg: float = 0.0

    # Provenance
    source_id: str = "unknown"
    source_timestamp: str = ""  # ISO 8601
    retrieval_time: str = ""  # ISO 8601
    schema_hash: str = ""
    missingness: str = "complete"  # "complete" | "partial" | "missing"
    fallback: bool = False
    training_eligible: bool = False  # ALWAYS False by default

    # Windows
    window_type: str = "instantaneous"
    window_start: str = ""  # ISO 8601
    window_end: str = ""  # ISO 8601
    grid_manifest_hash: str = ""

    # Optional spatial fields
    pixel_footprint: dict[str, Any] | None = None
    curvature: float | None = None
    roughness: float | None = None

    def validate(self) -> None:
        """Validate the cell input contract. Raises ValueError on invalid input."""
        # Identity
        if not self.region_key:
            raise ValueError("region_key must not be empty")
        if not self.pixel_id:
            raise ValueError("pixel_id must not be empty")
        if self.row < 0 or self.col < 0:
            raise ValueError(f"row/col must be >= 0, got row={self.row}, col={self.col}")
        if not self.issue_slot:
            raise ValueError("issue_slot must not be empty")

        # Spatial
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(f"latitude out of range: {self.latitude}")
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(f"longitude out of range: {self.longitude}")
        if not (-500.0 <= self.elevation_m <= 9000.0):
            raise ValueError(f"elevation_m out of range: {self.elevation_m}")
        if not self.crs:
            raise ValueError("crs must not be empty")
        if not self.crs.startswith("EPSG:"):
            raise ValueError(f"crs must start with 'EPSG:', got '{self.crs}'")

        # Window type
        if self.window_type not in VALID_WINDOW_TYPES:
            raise ValueError(
                f"window_type '{self.window_type}' not in {VALID_WINDOW_TYPES}"
            )

        # Training eligibility — must default to False
        if self.training_eligible:
            raise ValueError(
                "training_eligible must be False by default — "
                "no automatic historical-event training"
            )

        # Missingness
        if self.missingness not in ("complete", "partial", "missing"):
            raise ValueError(f"invalid missingness: {self.missingness}")

        # Weather fields — reject NaN and infinite values
        import math
        for _field_name in (
            'air_temp_c', 'relative_humidity', 'pressure_hpa', 'precip_mm',
            'wind_speed_ms', 'wind_dir_deg', 'wind_gust_ms', 'shortwave_radiation',
        ):
            _val = getattr(self, _field_name)
            if math.isnan(_val) or math.isinf(_val):
                raise ValueError(f"{_field_name} must be a finite number, got {_val}")

        # Provenance — source_timestamp must be non-empty ISO 8601
        if not self.source_timestamp:
            raise ValueError("source_timestamp must not be empty")
        if self.retrieval_time:
            _validate_iso_timestamp(self.retrieval_time, "PartnerCellInputContract")
        _validate_iso_timestamp(self.source_timestamp, "PartnerCellInputContract")
        _validate_iso_timestamp(self.timestamp, "PartnerCellInputContract")
        if self.window_start:
            _validate_iso_timestamp(self.window_start, "PartnerCellInputContract")
        if self.window_end:
            _validate_iso_timestamp(self.window_end, "PartnerCellInputContract")

        # Schema hash must be a 64-char hex string
        if not self.schema_hash:
            raise ValueError("schema_hash must not be empty")
        if len(self.schema_hash) != 64:
            raise ValueError(f"schema_hash must be 64 chars, got {len(self.schema_hash)}")
        try:
            int(self.schema_hash, 16)
        except ValueError:
            raise ValueError("schema_hash must be a valid hex string")

    def as_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


def compute_schema_hash(payload: dict[str, Any]) -> str:
    """Compute SHA-256 hash of a sorted-JSON-serialized payload.

    This provides a deterministic provenance hash for cell inputs.
    """
    sorted_json = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(sorted_json.encode("utf-8")).hexdigest()


def build_cell_inputs(
    region_grid: list[dict[str, float]],
    weather_profiles: list[dict[str, Any]],
    issue_slot: str,
    timestamp: str,
    region_key: str = "unknown",
    window_type: str = "instantaneous",
    window_start: str = "",
    window_end: str = "",
) -> list[PartnerCellInputContract]:
    """Build a list of PartnerCellInputContract from a region grid and weather profiles.

    This is a pure function — no network calls, no DB access.
    Weather profiles must be aligned 1:1 with grid cells.

    Args:
        region_grid: List of cell dicts with 'lat', 'lng', 'row', 'col'.
        weather_profiles: List of weather dicts aligned to region_grid.
        issue_slot: Issue slot string, e.g. "06".
        timestamp: ISO 8601 timestamp of the forecast issue.
        region_key: Region identifier.
        window_type: One of VALID_WINDOW_TYPES.
        window_start: ISO 8601 start of the aggregation window.
        window_end: ISO 8601 end of the aggregation window.

    Returns:
        List of PartnerCellInputContract instances.

    Raises:
        ValueError: If grid and profiles length mismatch.
    """
    if len(region_grid) != len(weather_profiles):
        raise ValueError(
            f"Grid ({len(region_grid)}) and weather profiles ({len(weather_profiles)}) "
            f"length mismatch"
        )

    contracts: list[PartnerCellInputContract] = []
    for idx, (cell, weather) in enumerate(zip(region_grid, weather_profiles)):
        pixel_id = str(cell.get('pixel_id') or f"{region_key}_{cell.get('row', 0)}_{cell.get('col', 0)}")
        elevation = cell.get('elevation_m', 0.0)

        contract = PartnerCellInputContract(
            region_key=region_key,
            pixel_id=pixel_id,
            row=int(cell.get('row', 0)),
            col=int(cell.get('col', 0)),
            timestamp=timestamp,
            issue_slot=issue_slot,
            latitude=float(cell['lat']),
            longitude=float(cell['lng']),
            elevation_m=float(elevation),
            crs=str(cell.get('crs') or 'EPSG:4326'),
            air_temp_c=float(weather['air_temp_c']),
            relative_humidity=float(weather['relative_humidity']),
            pressure_hpa=float(weather['pressure_hpa']),
            precip_mm=float(weather['precip_mm']),
            wind_speed_ms=float(weather['wind_speed_ms']),
            wind_dir_deg=float(weather['wind_dir_deg']),
            wind_gust_ms=float(weather['wind_gust_ms']),
            shortwave_radiation=float(weather['shortwave_radiation']),
            slope_deg=float(cell.get('slope_deg', 0.0)),
            aspect_deg=float(cell.get('aspect_deg', 0.0)),
            source_id=str(weather.get('source_id', 'open-meteo')),
            source_timestamp=str(weather.get('source_timestamp', '')),
            retrieval_time=str(weather.get('retrieval_time', timestamp)),
            schema_hash=compute_schema_hash({
                'pixel_id': pixel_id,
                'lat': cell['lat'],
                'lng': cell['lng'],
                'timestamp': timestamp,
                'source_timestamp': weather.get('source_timestamp'),
                'grid_manifest_hash': cell.get('grid_manifest_hash'),
            }),
            missingness=str(weather.get('missingness', 'complete')),
            fallback=bool(weather.get('fallback', False)),
            training_eligible=False,
            window_type=window_type,
            window_start=window_start,
            window_end=window_end,
            grid_manifest_hash=str(cell.get('grid_manifest_hash') or ''),
        )
        contracts.append(contract)

    return contracts
