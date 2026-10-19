"""Variable-specific terrain transformations for the open-forcing lane.

These functions are deterministic research transforms, not a claim that a
coarse open source product contains fine-scale Himalayan truth. Every result
must carry an effective information scale. Temperature uses an explicit lapse
rate, precipitation is redistributed conservatively over a supplied support
mask, radiation uses a terrain-incidence factor, and wind remains a vector
unless an explicit exposure factor is supplied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .contracts import OpenForcingContractError


def _finite(value: float, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise OpenForcingContractError(f"{name} must be finite")
    return converted


@dataclass(frozen=True)
class EffectiveResolution:
    """Information-scale metadata for a target-grid result.

    ``target_resolution_m`` describes the requested output grid. It is not a
    claim of information content. ``effective_information_scale_m`` is never
    allowed to be finer than that target and is normally the larger of the
    source native scale and the requested output scale.
    """

    source_id: str
    native_resolution_m: float
    target_resolution_m: float
    effective_information_scale_m: float
    method: str
    support_fraction: float = 1.0

    def validate(self) -> None:
        if not self.source_id.strip() or not self.method.strip():
            raise OpenForcingContractError("resolution metadata requires source_id and method")
        for name, value in (
            ("native_resolution_m", self.native_resolution_m),
            ("target_resolution_m", self.target_resolution_m),
            ("effective_information_scale_m", self.effective_information_scale_m),
        ):
            if _finite(value, name) <= 0:
                raise OpenForcingContractError(f"{name} must be positive")
        support = _finite(self.support_fraction, "support_fraction")
        if not 0.0 <= support <= 1.0:
            raise OpenForcingContractError("support_fraction must be between 0 and 1")
        if self.effective_information_scale_m < self.target_resolution_m:
            raise OpenForcingContractError(
                "effective information scale cannot be finer than target resolution"
            )


def resolution_metadata(
    *,
    source_id: str,
    native_resolution_m: float,
    target_resolution_m: float,
    method: str,
    support_fraction: float = 1.0,
) -> EffectiveResolution:
    """Construct conservative resolution metadata for one transform."""

    metadata = EffectiveResolution(
        source_id=source_id,
        native_resolution_m=float(native_resolution_m),
        target_resolution_m=float(target_resolution_m),
        effective_information_scale_m=max(float(native_resolution_m), float(target_resolution_m)),
        method=method,
        support_fraction=float(support_fraction),
    )
    metadata.validate()
    return metadata


def downscale_temperature_celsius(
    temperature_c: float,
    *,
    source_elevation_m: float,
    target_elevation_m: float,
    source_id: str,
    native_resolution_m: float,
    target_resolution_m: float,
    lapse_rate_k_per_km: float = 6.5,
    max_abs_adjustment_k: float = 20.0,
) -> tuple[float, EffectiveResolution]:
    """Apply a bounded elevation lapse correction to Celsius temperature."""

    base = _finite(temperature_c, "temperature_c")
    source_elevation = _finite(source_elevation_m, "source_elevation_m")
    target_elevation = _finite(target_elevation_m, "target_elevation_m")
    lapse = _finite(lapse_rate_k_per_km, "lapse_rate_k_per_km")
    limit = _finite(max_abs_adjustment_k, "max_abs_adjustment_k")
    if lapse < 0.0 or lapse > 15.0 or limit <= 0.0:
        raise OpenForcingContractError("lapse-rate configuration is outside safe bounds")

    adjustment = -lapse * (target_elevation - source_elevation) / 1000.0
    adjustment = max(-limit, min(limit, adjustment))
    metadata = resolution_metadata(
        source_id=source_id,
        native_resolution_m=native_resolution_m,
        target_resolution_m=target_resolution_m,
        method="elevation_lapse_correction",
    )
    return base + adjustment, metadata


def redistribute_precipitation_mm(
    total_mm: float,
    weights: Sequence[float],
    *,
    source_id: str,
    native_resolution_m: float,
    target_resolution_m: float,
    support_fraction: float = 1.0,
) -> tuple[np.ndarray, EffectiveResolution]:
    """Redistribute an area-total precipitation amount conservatively.

    ``weights`` must describe the caller's explicitly chosen target support;
    this function does not infer precipitation from elevation or imagery.
    The returned values sum to ``total_mm`` (up to floating-point precision).
    """

    total = _finite(total_mm, "total_mm")
    if total < 0.0:
        raise OpenForcingContractError("total_mm cannot be negative")
    values = np.asarray(tuple(weights), dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise OpenForcingContractError("weights must be a non-empty one-dimensional sequence")
    if not np.isfinite(values).all() or (values < 0.0).any():
        raise OpenForcingContractError("weights must be finite and non-negative")
    weight_sum = float(values.sum())
    if weight_sum <= 0.0:
        raise OpenForcingContractError("at least one precipitation weight must be positive")
    result = total * values / weight_sum
    if result.size > 1:
        result[-1] = total - float(result[:-1].sum())
    metadata = resolution_metadata(
        source_id=source_id,
        native_resolution_m=native_resolution_m,
        target_resolution_m=target_resolution_m,
        method="conservative_area_weighted_redistribution",
        support_fraction=support_fraction,
    )
    return result, metadata


def terrain_radiation_factor(
    *,
    slope_deg: float,
    aspect_deg: float,
    solar_zenith_deg: float,
    solar_azimuth_deg: float,
    max_factor: float = 3.0,
) -> float:
    """Return a bounded terrain-incidence factor for shortwave radiation."""

    slope = _finite(slope_deg, "slope_deg")
    aspect = _finite(aspect_deg, "aspect_deg")
    zenith = _finite(solar_zenith_deg, "solar_zenith_deg")
    azimuth = _finite(solar_azimuth_deg, "solar_azimuth_deg")
    limit = _finite(max_factor, "max_factor")
    if not 0.0 <= slope <= 90.0 or not 0.0 <= zenith <= 90.0 or limit <= 0.0:
        raise OpenForcingContractError("terrain angles or max_factor are outside valid bounds")

    slope_rad = math.radians(slope)
    zenith_rad = math.radians(zenith)
    relative_azimuth = math.radians(aspect - azimuth)
    incidence = (
        math.cos(zenith_rad) * math.cos(slope_rad)
        + math.sin(zenith_rad) * math.sin(slope_rad) * math.cos(relative_azimuth)
    )
    reference = max(math.cos(zenith_rad), 1e-6)
    return max(0.0, min(limit, incidence / reference))


def downscale_shortwave_radiation(
    shortwave_wm2: float,
    *,
    slope_deg: float,
    aspect_deg: float,
    solar_zenith_deg: float,
    solar_azimuth_deg: float,
    source_id: str,
    native_resolution_m: float,
    target_resolution_m: float,
) -> tuple[float, EffectiveResolution]:
    """Apply terrain incidence to a non-negative shortwave input."""

    base = _finite(shortwave_wm2, "shortwave_wm2")
    if base < 0.0:
        raise OpenForcingContractError("shortwave_wm2 cannot be negative")
    factor = terrain_radiation_factor(
        slope_deg=slope_deg,
        aspect_deg=aspect_deg,
        solar_zenith_deg=solar_zenith_deg,
        solar_azimuth_deg=solar_azimuth_deg,
    )
    metadata = resolution_metadata(
        source_id=source_id,
        native_resolution_m=native_resolution_m,
        target_resolution_m=target_resolution_m,
        method="terrain_incidence_shortwave_adjustment",
    )
    return base * factor, metadata


@dataclass(frozen=True)
class WindVector:
    """Horizontal wind components; scalar-speed interpolation is prohibited."""

    u_ms: float
    v_ms: float

    def validate(self) -> None:
        u = _finite(self.u_ms, "u_ms")
        v = _finite(self.v_ms, "v_ms")
        if math.hypot(u, v) > 150.0:
            raise OpenForcingContractError("wind vector speed exceeds safe input bound")

    @property
    def speed_ms(self) -> float:
        self.validate()
        return math.hypot(self.u_ms, self.v_ms)


def transform_wind_vector(
    u_ms: float,
    v_ms: float,
    *,
    exposure_factor: float = 1.0,
    source_id: str,
    native_resolution_m: float,
    target_resolution_m: float,
) -> tuple[WindVector, EffectiveResolution]:
    """Preserve wind direction; apply only an explicit bounded exposure factor."""

    vector = WindVector(float(u_ms), float(v_ms))
    vector.validate()
    factor = _finite(exposure_factor, "exposure_factor")
    if factor <= 0.0 or factor > 4.0:
        raise OpenForcingContractError("exposure_factor must be greater than 0 and no more than 4")
    transformed = WindVector(vector.u_ms * factor, vector.v_ms * factor)
    transformed.validate()
    metadata = resolution_metadata(
        source_id=source_id,
        native_resolution_m=native_resolution_m,
        target_resolution_m=target_resolution_m,
        method="vector_preserving_wind_exposure_adjustment",
    )
    return transformed, metadata
