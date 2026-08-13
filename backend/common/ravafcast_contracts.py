"""RAvaFcast alignment contracts — fail-closed validation for candidate modules.

These contracts ensure that RAvaFcast candidate modules (soft prediction, GP
interpolation, elevation-band aggregation, refined thresholds) cannot operate
without approved Partner inputs. Every contract fails closed: invalid labels,
missing coordinates, or unsupported binary-to-multiclass conversions raise
ContractViolationError.

This module is additive and disabled by default. It does NOT modify any
denylisted file (risk_math.py, verification_exit_gates.py, label_governance.py,
snowpack_physics.py, backend/reproduction/).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class ContractViolationError(Exception):
    """Raised when a contract validation fails. All contracts fail closed."""


# ---------------------------------------------------------------------------
# 1. Label Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabelContract:
    """Approved danger-label dictionary for multiclass classification.

    Requires Partner to define the label mapping, missing-label policy, and
    valid forecast window. Without this contract, no soft prediction (d_avg)
    may be computed.
    """
    labels: tuple[int, ...]
    label_names: tuple[str, ...]
    missing_label_policy: str  # 'reject' | 'interpolate' | 'skip'
    forecast_window_hours: int
    approved_by: str
    approved_at: str  # ISO 8601

    def validate(self) -> None:
        if not self.labels or len(self.labels) < 2:
            raise ContractViolationError(
                "LabelContract: at least 2 danger labels required, got "
                f"{self.labels}"
            )
        if len(self.labels) != len(self.label_names):
            raise ContractViolationError(
                f"LabelContract: {len(self.labels)} labels but "
                f"{len(self.label_names)} names"
            )
        if len(set(self.labels)) != len(self.labels):
            raise ContractViolationError(
                f"LabelContract: labels must be unique, got {self.labels}"
            )
        if list(self.labels) != sorted(self.labels):
            raise ContractViolationError(
                f"LabelContract: labels must be ordered ascending, got {self.labels}"
            )
        if len(set(self.label_names)) != len(self.label_names):
            raise ContractViolationError(
                f"LabelContract: label_names must be unique, got {self.label_names}"
            )
        if self.missing_label_policy not in ("reject", "interpolate", "skip"):
            raise ContractViolationError(
                f"LabelContract: invalid missing_label_policy "
                f"'{self.missing_label_policy}'"
            )
        if self.forecast_window_hours <= 0:
            raise ContractViolationError(
                f"LabelContract: forecast_window_hours must be positive, "
                f"got {self.forecast_window_hours}"
            )
        if not self.approved_by:
            raise ContractViolationError(
                "LabelContract: approved_by is required (Partner scientist)"
            )
        if not self.approved_at:
            raise ContractViolationError(
                "LabelContract: approved_at is required (ISO 8601 timestamp)"
            )
        _validate_iso_timestamp(self.approved_at, "LabelContract")

    def validate_probability_vector(self, probs: list[float]) -> None:
        """Validate that a probability vector matches this contract's labels."""
        if len(probs) != len(self.labels):
            raise ContractViolationError(
                f"Probability vector length {len(probs)} != "
                f"label count {len(self.labels)}"
            )
        if any(not math.isfinite(p) for p in probs):
            raise ContractViolationError(
                "Probability vector contains non-finite values (inf/nan)"
            )
        total = sum(probs)
        if not (0.99 <= total <= 1.01):
            raise ContractViolationError(
                f"Probability vector does not sum to 1.0 (sum={total:.4f})"
            )
        if any(p < 0.0 for p in probs):
            raise ContractViolationError(
                "Probability vector contains negative values"
            )

    def reject_binary_risk_score(self, risk_score: float) -> None:
        """Explicitly reject binary risk_score → multiclass conversion.

        risk_score is an event-probability/hazard/impact composite, NOT a
        multiclass danger logit. Converting it via softmax or temperature
        scaling is scientifically unsafe and prohibited.
        """
        raise ContractViolationError(
            "Binary risk_score cannot be converted to multiclass danger "
            "probabilities. risk_score is an event-probability/hazard/impact "
            "composite, NOT a multiclass danger logit. Use a multiclass "
            "classifier trained on approved labels instead."
        )


# ---------------------------------------------------------------------------
# 2. Station Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StationContract:
    """Required fields for station-level observations."""
    required_fields: tuple[str, ...] = (
        "station_id", "latitude", "longitude", "elevation_m",
        "timestamp", "air_temp_c", "wind_speed_ms", "precip_mm",
    )
    optional_fields: tuple[str, ...] = (
        "snow_depth_cm", "snow_water_equivalent_mm", "relative_humidity_pct",
        "pressure_hpa", "provenance_hash",
    )
    units: dict[str, str] = field(default_factory=lambda: {
        "latitude": "degrees",
        "longitude": "degrees",
        "elevation_m": "meters",
        "air_temp_c": "celsius",
        "wind_speed_ms": "m/s",
        "precip_mm": "mm",
        "snow_depth_cm": "cm",
        "snow_water_equivalent_mm": "mm",
        "relative_humidity_pct": "percent",
        "pressure_hpa": "hPa",
    })

    def validate_station(self, station: dict[str, Any]) -> None:
        missing = [
            f for f in self.required_fields if f not in station or station[f] is None
        ]
        if missing:
            raise ContractViolationError(
                f"StationContract: missing required fields: {missing}"
            )
        lat = station["latitude"]
        lon = station["longitude"]
        elev = station["elevation_m"]
        for field_name, val in [("latitude", lat), ("longitude", lon), ("elevation_m", elev),
                                 ("air_temp_c", station.get("air_temp_c")),
                                 ("wind_speed_ms", station.get("wind_speed_ms")),
                                 ("precip_mm", station.get("precip_mm"))]:
            if val is not None and not math.isfinite(float(val)):
                raise ContractViolationError(
                    f"StationContract: {field_name} must be finite, got {val}"
                )
        if not (-90.0 <= lat <= 90.0):
            raise ContractViolationError(
                f"StationContract: latitude {lat} out of range [-90, 90]"
            )
        if not (-180.0 <= lon <= 180.0):
            raise ContractViolationError(
                f"StationContract: longitude {lon} out of range [-180, 180]"
            )
        if not (-500.0 <= elev <= 9000.0):
            raise ContractViolationError(
                f"StationContract: elevation_m {elev} out of reasonable range"
            )
        ts = station.get("timestamp")
        if ts is not None:
            if isinstance(ts, str):
                _validate_iso_timestamp(ts, "StationContract")
            elif not isinstance(ts, datetime):
                raise ContractViolationError(
                    f"StationContract: timestamp must be str or datetime, got {type(ts)}"
                )
        sid = station.get("station_id")
        if not sid or not str(sid).strip():
            raise ContractViolationError(
                "StationContract: station_id must be non-empty"
            )


# ---------------------------------------------------------------------------
# 3. Snowpack Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnowpackContract:
    """Schema for snow profile / stratigraphy data."""
    required_fields: tuple[str, ...] = (
        "layer_depth_m", "grain_type", "hardness",
        "temperature_c", "swe_mm",
    )
    optional_fields: tuple[str, ...] = (
        "stability_index", "ssi", "sk38", "pwl_flag",
        "provenance_hash", "observation_method",
    )
    missingness_policy: str = "reject"  # 'reject' | 'proxy' | 'skip'

    def validate_profile(self, profile: dict[str, Any]) -> None:
        if self.missingness_policy not in ("reject", "proxy", "skip"):
            raise ContractViolationError(
                f"SnowpackContract: invalid missingness_policy '{self.missingness_policy}'"
            )
        missing = [
            f for f in self.required_fields if f not in profile or profile[f] is None
        ]
        if missing:
            if self.missingness_policy == "reject":
                raise ContractViolationError(
                    f"SnowpackContract: missing required fields: {missing}"
                )
            elif self.missingness_policy == "skip":
                return
        depth = profile.get("layer_depth_m")
        if depth is not None:
            if not math.isfinite(float(depth)):
                raise ContractViolationError(
                    f"SnowpackContract: layer_depth_m must be finite, got {depth}"
                )
            if depth < 0:
                raise ContractViolationError(
                    f"SnowpackContract: layer_depth_m {depth} is negative"
                )
        temp = profile.get("temperature_c")
        if temp is not None and not math.isfinite(float(temp)):
            raise ContractViolationError(
                f"SnowpackContract: temperature_c must be finite, got {temp}"
            )
        swe = profile.get("swe_mm")
        if swe is not None and not math.isfinite(float(swe)):
            raise ContractViolationError(
                f"SnowpackContract: swe_mm must be finite, got {swe}"
            )
        obs_time = profile.get("observation_time")
        if obs_time is not None:
            _validate_iso_timestamp(str(obs_time), "SnowpackContract")
        is_proxy = profile.get("is_proxy")
        if is_proxy is not None and not isinstance(is_proxy, bool):
            raise ContractViolationError(
                f"SnowpackContract: is_proxy must be bool or absent, got {type(is_proxy)}"
            )


# ---------------------------------------------------------------------------
# 4. Grid/CRS Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridCRSContract:
    """Coordinate reference system and grid specification."""
    crs: str  # e.g., 'EPSG:4326' (degree) or 'EPSG:32644' (UTM 44N)
    dem_source: str  # e.g., 'COP30' or 'SRTM'
    cell_size_degrees: float | None = None  # for degree grids
    cell_size_meters: float | None = None  # for projected grids
    reprojection_allowed: bool = False

    def validate(self) -> None:
        if not self.crs:
            raise ContractViolationError("GridCRSContract: crs is required")
        if not self.dem_source:
            raise ContractViolationError("GridCRSContract: dem_source is required")
        if self.cell_size_degrees is None and self.cell_size_meters is None:
            raise ContractViolationError(
                "GridCRSContract: must specify cell_size_degrees or cell_size_meters"
            )
        if self.cell_size_degrees is not None and self.cell_size_meters is not None:
            raise ContractViolationError(
                "GridCRSContract: must specify exactly one of cell_size_degrees or cell_size_meters, not both"
            )
        if self.cell_size_degrees is not None:
            if not math.isfinite(self.cell_size_degrees) or self.cell_size_degrees <= 0:
                raise ContractViolationError(
                    f"GridCRSContract: cell_size_degrees must be positive finite, "
                    f"got {self.cell_size_degrees}"
                )
        if self.cell_size_meters is not None:
            if not math.isfinite(self.cell_size_meters) or self.cell_size_meters <= 0:
                raise ContractViolationError(
                    f"GridCRSContract: cell_size_meters must be positive finite, "
                    f"got {self.cell_size_meters}"
                )
        if self.cell_size_degrees is not None and not self.crs.upper().startswith("EPSG:4326"):
            raise ContractViolationError(
                f"GridCRSContract: cell_size_degrees requires geographic CRS (EPSG:4326), "
                f"got {self.crs}"
            )
        if self.cell_size_meters is not None and self.crs.upper().startswith("EPSG:4326"):
            raise ContractViolationError(
                f"GridCRSContract: cell_size_meters requires projected CRS, "
                f"got {self.crs}"
            )


# ---------------------------------------------------------------------------
# 5. Region/Elevation Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegionElevationContract:
    """Pilot polygons, district mapping, and elevation-band definitions."""
    pilot_region_id: str
    pilot_region_name: str
    elevation_bands_m: tuple[int, ...]
    district_mapping: dict[str, str] = field(default_factory=dict)
    approved_by: str = ""
    approved_at: str = ""

    def validate(self) -> None:
        if not self.pilot_region_id:
            raise ContractViolationError(
                "RegionElevationContract: pilot_region_id is required"
            )
        if not self.pilot_region_name or not self.pilot_region_name.strip():
            raise ContractViolationError(
                "RegionElevationContract: pilot_region_name is required"
            )
        if not self.elevation_bands_m or len(self.elevation_bands_m) < 1:
            raise ContractViolationError(
                "RegionElevationContract: at least 1 elevation band required"
            )
        bands = list(self.elevation_bands_m)
        if bands != sorted(bands):
            raise ContractViolationError(
                f"RegionElevationContract: elevation bands must be sorted, "
                f"got {self.elevation_bands_m}"
            )
        if len(set(bands)) != len(bands):
            raise ContractViolationError(
                f"RegionElevationContract: elevation bands must be unique, "
                f"got {self.elevation_bands_m}"
            )
        if not self.approved_by:
            raise ContractViolationError(
                "RegionElevationContract: approved_by is required (Partner)"
            )
        if not self.approved_at:
            raise ContractViolationError(
                "RegionElevationContract: approved_at is required (ISO 8601)"
            )
        _validate_iso_timestamp(self.approved_at, "RegionElevationContract")

    @property
    def is_Partner_approved(self) -> bool:
        return bool(self.approved_by and self.approved_at)


# ---------------------------------------------------------------------------
# 6. Evidence Case Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceCaseContract:
    """Provenance, reviewer ownership, and truth-set reference for validation."""
    provenance_hash: str
    reviewer: str
    valid_from: str  # ISO 8601
    valid_to: str  # ISO 8601
    truth_set_reference: str
    metrics: tuple[str, ...] = ("brier", "ece", "accuracy")
    holdout_reference: str = ""
    label_contract_reference: str = ""
    synthetic_input: bool = False
    decision: str = ""  # 'select' | 'refine' | 'decline' | '' (blank = pending)
    _ALLOWED_METRICS: tuple[str, ...] = ("brier", "ece", "accuracy", "pss", "f1", "roc_auc")
    _ALLOWED_DECISIONS: tuple[str, ...] = ("select", "refine", "decline", "")

    def validate(self) -> None:
        if not self.provenance_hash:
            raise ContractViolationError(
                "EvidenceCaseContract: provenance_hash is required"
            )
        if not re.match(r'^[0-9a-f]{64}$', self.provenance_hash):
            raise ContractViolationError(
                f"EvidenceCaseContract: provenance_hash must be SHA-256 (64 hex chars), "
                f"got {len(self.provenance_hash)} chars"
            )
        if not self.reviewer:
            raise ContractViolationError(
                "EvidenceCaseContract: reviewer is required (named Partner scientist)"
            )
        if not self.truth_set_reference:
            raise ContractViolationError(
                "EvidenceCaseContract: truth_set_reference is required"
            )
        _validate_iso_timestamp(self.valid_from, "EvidenceCaseContract")
        _validate_iso_timestamp(self.valid_to, "EvidenceCaseContract")
        from_dt = _parse_iso(self.valid_from)
        to_dt = _parse_iso(self.valid_to)
        if from_dt >= to_dt:
            raise ContractViolationError(
                f"EvidenceCaseContract: valid_from ({self.valid_from}) must be before "
                f"valid_to ({self.valid_to})"
            )
        for m in self.metrics:
            if m not in self._ALLOWED_METRICS:
                raise ContractViolationError(
                    f"EvidenceCaseContract: metric '{m}' not in allowed list "
                    f"{self._ALLOWED_METRICS}"
                )
        if self.decision not in self._ALLOWED_DECISIONS:
            raise ContractViolationError(
                f"EvidenceCaseContract: decision must be one of {self._ALLOWED_DECISIONS}, "
                f"got '{self.decision}'"
            )


# ---------------------------------------------------------------------------
# Utility: provenance hash
# ---------------------------------------------------------------------------

def compute_provenance_hash(payload: dict[str, Any]) -> str:
    """Compute SHA-256 provenance hash for a payload.

    Only JSON-serializable types are accepted (dict, list, str, int, float, bool, None).
    Arbitrary objects that require `default=str` are rejected to ensure stable hashes.
    """
    try:
        canonical = json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ContractViolationError(
            f"compute_provenance_hash: payload is not JSON-serializable without "
            f"lossy default=str conversion: {exc}"
        ) from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


_ISO_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
    r'(\.\d+)?'
    r'(Z|[+-]\d{2}:?\d{2})?$'
)


def _validate_iso_timestamp(ts: str, context: str) -> None:
    """Validate that a string is a valid ISO 8601 timestamp."""
    if not ts or not isinstance(ts, str):
        raise ContractViolationError(
            f"{context}: timestamp must be a non-empty string, got {ts!r}"
        )
    if not _ISO_RE.match(ts):
        raise ContractViolationError(
            f"{context}: timestamp '{ts}' is not valid ISO 8601 "
            f"(expected YYYY-MM-DDTHH:MM:SSZ or with timezone offset)"
        )


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a datetime object."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))
