"""Research-only Himalayan forcing adapter for the native SNOWPACK bridge.

This module connects the validated open-forcing source-point payload to the
existing strict SMET writer. It deliberately requires explicit site geometry,
source elevation, precipitation-phase thresholds, and source identity. The
result is a candidate forcing transform, not calibrated Himalayan truth.

The adapter preserves three distinct hashes:

* ``raw_payload_sha256`` — bytes returned by the source adapter;
* ``corrected_payload_sha256`` — canonical transformed site samples;
* ``smet_sha256`` — exact bytes written for SNOWPACK.

No source fetch, DEM interpolation, station calibration, or production
promotion is performed here.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import timezone
from pathlib import Path
from typing import Any

from backend.common.meteoio_openmeteo import write_smet_file

from .contracts import OpenForcingContractError, ensure_utc
from .downscaling import (
    EffectiveResolution,
    WindVector,
    downscale_shortwave_radiation,
    downscale_temperature_celsius,
    resolution_metadata,
    transform_wind_vector,
)
from .open_meteo_source import NativeSourcePointPayload


def _number(record: dict[str, Any], *names: str, required: bool = True) -> float | None:
    """Read one explicit source field without silently replacing missing data."""

    present = next((name for name in names if name in record), None)
    if present is None:
        if required:
            raise OpenForcingContractError(
                f"source record is missing required variable; accepted names={names}"
            )
        return None
    value = record[present]
    if value is None:
        if required:
            raise OpenForcingContractError(f"source variable {present!r} is null")
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise OpenForcingContractError(f"source variable {present!r} is not numeric") from exc
    if not math.isfinite(converted):
        raise OpenForcingContractError(f"source variable {present!r} is non-finite")
    return converted


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def precipitation_phase_fraction(
    temperature_c: float,
    *,
    snow_temperature_c: float,
    rain_temperature_c: float,
) -> float:
    """Return liquid precipitation fraction using explicit candidate thresholds.

    The thresholds are configuration inputs and are not claimed to be
    Himalayan-calibrated. A value of 0 is fully solid and 1 is fully liquid,
    matching SNOWPACK's documented ``PSUM_PH`` semantics.
    """

    temp = float(temperature_c)
    snow = float(snow_temperature_c)
    rain = float(rain_temperature_c)
    if not all(math.isfinite(value) for value in (temp, snow, rain)):
        raise OpenForcingContractError("precipitation-phase temperatures must be finite")
    if snow >= rain:
        raise OpenForcingContractError("snow_temperature_c must be below rain_temperature_c")
    return max(0.0, min(1.0, (temp - snow) / (rain - snow)))


@dataclass(frozen=True)
class HimalayanSiteSpec:
    """Explicit site transform inputs for one Himalayan SNOWPACK point."""

    site_id: str
    source_point_index: int
    source_snapshot_id: str
    source_id: str
    source_elevation_m: float
    target_elevation_m: float
    slope_deg: float
    aspect_deg: float
    native_resolution_m: float
    target_resolution_m: float
    snow_temperature_c: float
    rain_temperature_c: float
    exposure_factor: float = 1.0
    precipitation_scale: float = 1.0
    precipitation_scale_source: str = "none"
    apply_shortwave_terrain: bool = False

    def validate(self) -> None:
        if not self.site_id.strip() or not self.source_snapshot_id.strip() or not self.source_id.strip():
            raise OpenForcingContractError("site and source identities are required")
        if self.source_point_index < 0:
            raise OpenForcingContractError("source_point_index must be non-negative")
        for name in (
            "source_elevation_m", "target_elevation_m", "native_resolution_m",
            "target_resolution_m", "snow_temperature_c", "rain_temperature_c",
            "exposure_factor", "precipitation_scale",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise OpenForcingContractError(f"{name} must be finite")
        if not 0.0 <= self.slope_deg <= 90.0:
            raise OpenForcingContractError("slope_deg must be between 0 and 90")
        if not 0.0 <= self.aspect_deg <= 360.0:
            raise OpenForcingContractError("aspect_deg must be between 0 and 360")
        if self.native_resolution_m <= 0.0 or self.target_resolution_m <= 0.0:
            raise OpenForcingContractError("resolution values must be positive")
        if self.snow_temperature_c >= self.rain_temperature_c:
            raise OpenForcingContractError("snow_temperature_c must be below rain_temperature_c")
        if not 0.0 < self.exposure_factor <= 4.0:
            raise OpenForcingContractError("exposure_factor must be greater than 0 and no more than 4")
        if not 0.0 < self.precipitation_scale <= 10.0:
            raise OpenForcingContractError("precipitation_scale must be greater than 0 and no more than 10")
        if self.precipitation_scale != 1.0 and (
            not self.precipitation_scale_source.strip()
            or self.precipitation_scale_source.strip().lower() == "none"
        ):
            raise OpenForcingContractError(
                "precipitation_scale_source is required for a non-neutral correction"
            )


@dataclass(frozen=True)
class HimalayanSnowpackForcing:
    """Hash-linked candidate forcing ready for strict SMET serialization."""

    site: HimalayanSiteSpec
    model_id: str
    source_run_id: str
    raw_payload_sha256: str
    corrected_payload_sha256: str
    samples: tuple[dict[str, Any], ...]
    resolution_metadata: tuple[EffectiveResolution, ...]
    derived_fields: tuple[str, ...] = ("TSG", "TSS", "PSUM_PH")
    smet_sha256: str = ""
    research_only: bool = True

    def validate(self) -> None:
        self.site.validate()
        if not self.model_id.strip() or not self.source_run_id.strip():
            raise OpenForcingContractError("model_id and source_run_id are required")
        for name in ("raw_payload_sha256", "corrected_payload_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value.lower()
            ):
                raise OpenForcingContractError(f"{name} must be a SHA-256 digest")
        if self.smet_sha256 and (
            len(self.smet_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.smet_sha256.lower())
        ):
            raise OpenForcingContractError("smet_sha256 must be empty or a SHA-256 digest")
        if not self.samples:
            raise OpenForcingContractError("candidate forcing must contain at least one sample")
        if not self.resolution_metadata:
            raise OpenForcingContractError("candidate forcing requires resolution metadata")
        for metadata in self.resolution_metadata:
            metadata.validate()
        if not self.research_only:
            raise OpenForcingContractError("Himalayan open-forcing output must remain research_only")


def _wind_direction_from_vector(vector: WindVector) -> float:
    """Convert east/north vector to meteorological direction-from degrees."""

    return math.degrees(math.atan2(-vector.u_ms, -vector.v_ms)) % 360.0


def build_himalayan_snowpack_forcing(
    payload: NativeSourcePointPayload,
    site: HimalayanSiteSpec,
) -> HimalayanSnowpackForcing:
    """Transform one validated source point into candidate SNOWPACK samples."""

    payload.validate()
    site.validate()
    if site.source_point_index >= len(payload.points):
        raise OpenForcingContractError("source_point_index is outside the source payload")

    point = payload.points[site.source_point_index]
    samples: list[dict[str, Any]] = []
    metadata: list[EffectiveResolution] = []
    for timestamp, record in zip(point.times, point.records):
        utc_time = ensure_utc(timestamp)
        temp_c = _number(record, "temperature_2m")
        rh = _number(record, "relative_humidity_2m")
        speed = _number(record, "wind_speed_10m", "windspeed_10m")
        direction = _number(record, "wind_direction_10m", "winddirection_10m")
        shortwave = _number(record, "shortwave_radiation")
        # Open-Meteo's terrestrial_radiation is top-of-atmosphere solar
        # radiation, not incoming longwave radiation. Keep it as provenance,
        # but only accept an explicitly named longwave field for ILWR.
        source_terrestrial_radiation = _number(record, "terrestrial_radiation", required=False)
        longwave = _number(record, "longwave_radiation", required=False)
        cloud = _number(record, "cloud_cover", required=False)
        precipitation = _number(record, "precipitation", required=False)
        snowfall = _number(record, "snowfall", required=False)
        snow_depth = _number(record, "snow_depth", required=False)

        adjusted_temp_c, temp_metadata = downscale_temperature_celsius(
            temp_c,
            source_elevation_m=site.source_elevation_m,
            target_elevation_m=site.target_elevation_m,
            source_id=site.source_id,
            native_resolution_m=site.native_resolution_m,
            target_resolution_m=site.target_resolution_m,
        )
        metadata.append(temp_metadata)

        wind_rad = math.radians(float(direction) % 360.0)
        source_vector = WindVector(
            -float(speed) * math.sin(wind_rad),
            -float(speed) * math.cos(wind_rad),
        )
        adjusted_wind, wind_metadata = transform_wind_vector(
            source_vector.u_ms,
            source_vector.v_ms,
            exposure_factor=site.exposure_factor,
            source_id=site.source_id,
            native_resolution_m=site.native_resolution_m,
            target_resolution_m=site.target_resolution_m,
        )
        metadata.append(wind_metadata)

        adjusted_shortwave = float(shortwave)
        if site.apply_shortwave_terrain:
            solar_zenith = _number(record, "solar_zenith")
            solar_azimuth = _number(record, "solar_azimuth")
            adjusted_shortwave, radiation_metadata = downscale_shortwave_radiation(
                adjusted_shortwave,
                slope_deg=site.slope_deg,
                aspect_deg=site.aspect_deg,
                solar_zenith_deg=solar_zenith,
                solar_azimuth_deg=solar_azimuth,
                source_id=site.source_id,
                native_resolution_m=site.native_resolution_m,
                target_resolution_m=site.target_resolution_m,
            )
            metadata.append(radiation_metadata)
        else:
            metadata.append(resolution_metadata(
                source_id=site.source_id,
                native_resolution_m=site.native_resolution_m,
                target_resolution_m=site.target_resolution_m,
                method="shortwave_source_value_no_terrain_adjustment",
            ))

        phase = precipitation_phase_fraction(
            adjusted_temp_c,
            snow_temperature_c=site.snow_temperature_c,
            rain_temperature_c=site.rain_temperature_c,
        )
        sample: dict[str, Any] = {
            "time": utc_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "temperature_2m": adjusted_temp_c,
            "relative_humidity_2m": rh,
            "windspeed_10m": adjusted_wind.speed_ms,
            "winddirection_10m": _wind_direction_from_vector(adjusted_wind),
            "shortwave_radiation": max(0.0, adjusted_shortwave),
            "precipitation_phase": phase,
            # Preserve direct snowfall availability for provenance and RF
            # eligibility checks.  A null source value remains null.
            "snowfall": snowfall,
        }
        if source_terrestrial_radiation is not None:
            sample["source_terrestrial_radiation"] = source_terrestrial_radiation
        if longwave is not None:
            sample["longwave_radiation"] = longwave
        elif cloud is not None:
            sample["cloud_cover"] = cloud
        else:
            raise OpenForcingContractError(
                "each source record requires longwave_radiation or cloud_cover"
            )
        if precipitation is not None:
            sample["precipitation"] = max(0.0, precipitation * site.precipitation_scale)
        elif snow_depth is not None:
            # Snow depth is retained as source QA only.  It is deliberately
            # not promoted to SNOWPACK HS without an explicit assimilation
            # decision; PSUM remains the candidate input path.
            sample["source_snow_depth"] = max(0.0, snow_depth)
        else:
            raise OpenForcingContractError(
                "each source record requires precipitation or snow_depth"
            )
        if snow_depth is not None:
            sample["source_snow_depth"] = max(0.0, snow_depth)
        samples.append(sample)

    result = HimalayanSnowpackForcing(
        site=site,
        model_id=payload.request.model_id,
        source_run_id=payload.request.run_id,
        raw_payload_sha256=payload.raw_payload_sha256,
        corrected_payload_sha256=_sha256_json(samples),
        samples=tuple(samples),
        resolution_metadata=tuple(metadata),
    )
    result.validate()
    return result


def write_himalayan_smet(
    forcing: HimalayanSnowpackForcing,
    *,
    output_path: Path,
    station_id: str,
    latitude: float,
    longitude: float,
) -> HimalayanSnowpackForcing:
    """Write and hash exact candidate SMET bytes with PSUM_PH enabled."""

    forcing.validate()
    write_smet_file(
        output_path=output_path,
        station_id=station_id,
        latitude=latitude,
        longitude=longitude,
        elevation=forcing.site.target_elevation_m,
        samples=list(forcing.samples),
        slope_angle=forcing.site.slope_deg,
        aspect=forcing.site.aspect_deg,
        strict=True,
        expected_cadence_hours=1.0,
        include_precipitation_phase=True,
    )
    result = replace(
        forcing,
        smet_sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
    )
    result.validate()
    return result
