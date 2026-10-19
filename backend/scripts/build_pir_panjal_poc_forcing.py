#!/usr/bin/env python3
"""Build a candidate winter Pir Panjal forcing package.

The package uses Open-Meteo's historical forecast replay at one source point,
normalizes explicit units, applies the existing candidate Himalayan adapter,
and writes raw, corrected, and strict SMET artifacts with separate hashes.
It is deliberately research-only: a replayed forecast is not a live forecast,
the source licence remains pending, and the result cannot unlock a native
release or scientific validation gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.pir_panjal_poc_case import load_pir_panjal_poc_case
from backend.common.pir_panjal_geometry import derive_hgt_terrain
from backend.open_forcing.open_meteo_source import (
    OpenMeteoRunRequest,
    parse_open_meteo_single_run,
)
from backend.open_forcing.snowpack_adapter import (
    HimalayanSiteSpec,
    HimalayanSnowpackForcing,
    build_himalayan_snowpack_forcing,
    write_himalayan_smet,
)


_UTC = timezone.utc
_MODEL = "gfs_seamless"
_SOURCE_ID = "open_meteo_historical_forecast"
_TARGET_RESOLUTION_M = 3000.0
_SOURCE_NATIVE_RESOLUTION_M = 13000.0
_EFFECTIVE_INFORMATION_SCALE_M = 25000.0
_HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
    "shortwave_radiation",
    "cloud_cover",
    "precipitation",
    "snowfall",
    "snow_depth",
    "terrestrial_radiation",
)
_RAW_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "windspeed_10m",
    "winddirection_10m",
    "surface_pressure",
    "shortwave_radiation",
    "precipitation",
    "snowfall",
    "snow_depth",
    "cloud_cover",
    "terrestrial_radiation",
)
_OPTIONAL_RAW_VARIABLES = frozenset({"snowfall", "snow_depth", "terrestrial_radiation"})
_CORE_RAW_VARIABLES = tuple(variable for variable in _RAW_VARIABLES if variable not in _OPTIONAL_RAW_VARIABLES)
_NORMALIZED_FIELD_NAMES = {
    "windspeed_10m": "wind_speed_10m",
    "winddirection_10m": "wind_direction_10m",
}
_CHUNK_HOURS = 384


class PirPanjalForcingBuildError(RuntimeError):
    """Raised when the candidate forcing cannot be built without defaults."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _load_contract_file(path: Path, *, label: str) -> tuple[dict[str, Any], bytes, str]:
    """Load a repository-bound JSON contract and return its exact bytes/hash."""
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PirPanjalForcingBuildError(f"{label} contract is unavailable or invalid: {path}") from exc
    if not isinstance(value, dict):
        raise PirPanjalForcingBuildError(f"{label} contract must be a JSON object: {path}")
    return value, raw, _sha256_bytes(raw)


def _iso(value: datetime) -> str:
    return value.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != _UTC.utcoffset(parsed):
        raise PirPanjalForcingBuildError(f"timestamp must be timezone-aware UTC: {value!r}")
    return parsed.astimezone(_UTC)


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PirPanjalForcingBuildError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PirPanjalForcingBuildError(f"{field} must be finite")
    return result


def _fetch(url: str) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "avalanche-insight-hub-pir-panjal-poc/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise PirPanjalForcingBuildError(f"historical forcing request failed: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PirPanjalForcingBuildError("historical forcing response is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PirPanjalForcingBuildError("historical forcing response must be an object")
    return raw, value


def _url(*, latitude: float, longitude: float, start: datetime, end_exclusive: datetime) -> str:
    end_inclusive = end_exclusive - timedelta(hours=1)
    query = {
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "start_date": start.date().isoformat(),
        "end_date": end_inclusive.date().isoformat(),
        "hourly": ",".join(_RAW_VARIABLES),
        "models": _MODEL,
        "timezone": "UTC",
    }
    return "https://historical-forecast-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(query)


def _normalize_response(
    response: dict[str, Any],
    *,
    start: datetime,
    end_exclusive: datetime,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    hourly = response.get("hourly")
    units = response.get("hourly_units")
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise PirPanjalForcingBuildError("historical response lacks hourly data or units")
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise PirPanjalForcingBuildError("historical response has no hourly timeline")
    columns: dict[str, list[Any]] = {}
    for variable in _RAW_VARIABLES:
        values = hourly.get(variable)
        if variable in _OPTIONAL_RAW_VARIABLES and values is None:
            values = [None] * len(times)
        if not isinstance(values, list) or len(values) != len(times):
            raise PirPanjalForcingBuildError(f"historical response is missing {variable}")
        columns[variable] = values
    normalized: list[dict[str, Any]] = []
    previous: datetime | None = None
    for index, raw_time in enumerate(times):
        if not isinstance(raw_time, str):
            raise PirPanjalForcingBuildError(f"hourly time {index} is not a string")
        try:
            current = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PirPanjalForcingBuildError(f"hourly time is not ISO-8601: {raw_time!r}") from exc
        # The request explicitly sets timezone=UTC. Open-Meteo returns the
        # corresponding hourly strings without an offset, so this is a source
        # contract normalization rather than an inferred local timezone.
        if current.tzinfo is None:
            current = current.replace(tzinfo=_UTC)
        current = current.astimezone(_UTC)
        if current < start or current >= end_exclusive:
            raise PirPanjalForcingBuildError("historical response falls outside requested window")
        if previous is not None and current - previous != timedelta(hours=1):
            raise PirPanjalForcingBuildError("historical response is not contiguous hourly data")
        previous = current
        record: dict[str, Any] = {"time": _iso(current)}
        for variable in _RAW_VARIABLES:
            value = columns[variable][index]
            if value is None:
                if variable not in _OPTIONAL_RAW_VARIABLES:
                    raise PirPanjalForcingBuildError(
                        f"historical response contains missing {variable} at {raw_time}; no default is allowed"
                    )
                record[variable] = None
                continue
            record[variable] = _finite(value, f"{variable}[{index}]")
        # Open-Meteo reports windspeed in km/h. The existing candidate adapter
        # consumes wind_speed_10m in m/s, so the unit conversion is explicit
        # and retained in the manifest below.
        record["wind_speed_10m"] = record.pop("windspeed_10m") / 3.6
        record["wind_direction_10m"] = record.pop("winddirection_10m")
        normalized.append(record)
    expected_count = int((end_exclusive - start).total_seconds() // 3600)
    if len(normalized) != expected_count:
        raise PirPanjalForcingBuildError(
            f"historical response has {len(normalized)} samples; expected {expected_count}"
        )
    response_metadata: dict[str, Any] = {}
    for source_key, metadata_key in (
        ("latitude", "provider_latitude"),
        ("longitude", "provider_longitude"),
        ("elevation", "provider_elevation_m"),
        ("generationtime_ms", "generationtime_ms"),
    ):
        value = response.get(source_key)
        if value is not None:
            response_metadata[metadata_key] = _finite(value, source_key)
    if isinstance(response.get("model"), str):
        response_metadata["provider_model"] = response["model"]
    return normalized, {str(key): str(value) for key, value in units.items()}, response_metadata


def _chunk_response(records: list[dict[str, Any]], start: int, end: int, *, latitude: float, longitude: float) -> dict[str, Any]:
    chunk = records[start:end]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": {
            "time": [record["time"] for record in chunk],
            **{variable: [record[variable] for record in chunk] for variable in _HOURLY_VARIABLES},
        },
    }


def build_candidate_forcing(*, case_path: Path, output_dir: Path) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[2]
    if not case_path.is_absolute():
        case_path = repository_root / case_path
    case = load_pir_panjal_poc_case(case_path, repository_root=repository_root, verify_files=True)
    site_data = case.site
    case_record = json.loads(case.raw_bytes.decode("utf-8"))
    dem_path = repository_root / case_record["file_bindings"]["dem_tile"]["path"]
    geometry = derive_hgt_terrain(
        dem_path=dem_path,
        latitude=float(site_data["latitude"]),
        longitude=float(site_data["longitude"]),
    )
    for field, geometry_key in (
        ("dem_elevation_m", "elevation_m"),
        ("slope_deg", "slope_deg"),
        ("aspect_deg", "aspect_deg"),
    ):
        if not math.isclose(
            float(site_data[field]),
            float(geometry[geometry_key]),
            rel_tol=0.0,
            abs_tol=1e-5,
        ):
            raise PirPanjalForcingBuildError(
                f"case geometry does not match deterministic DEM derivation for {field}"
            )
    simulation_start = _parse_utc(case.initial_state["start"])
    # MeteoIO's hourly PSUM accumulation needs real preceding source data and
    # the native runner keeps a 1.1-day prebuffer. This two-day boundary is
    # provider data, not a synthetic zero, and remains outside the simulation
    # window as an explicit warm-up buffer.
    source_start = simulation_start - timedelta(days=2)
    end_exclusive = _parse_utc("2024-02-24T00:00:00Z")
    latitude = _finite(site_data["latitude"], "latitude")
    longitude = _finite(site_data["longitude"], "longitude")
    source_url = _url(latitude=latitude, longitude=longitude, start=source_start, end_exclusive=end_exclusive)
    raw_bytes, response = _fetch(source_url)
    records, units, provider_metadata = _normalize_response(
        response, start=source_start, end_exclusive=end_exclusive
    )
    source_elevation = provider_metadata.get("provider_elevation_m")
    if source_elevation is None:
        raise PirPanjalForcingBuildError(
            "historical response does not expose provider-resolved elevation"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_contract, mapping_bytes, mapping_sha256 = _load_contract_file(
        repository_root / "config/snowpack_poc/ravafcast-snowpack-mapping.json",
        label="RAvaFcast/SNOWPACK mapping",
    )
    interpolation_contract, interpolation_bytes, interpolation_sha256 = _load_contract_file(
        repository_root / "config/snowpack_poc/meteoio-interpolation-policy.json",
        label="MeteoIO interpolation policy",
    )
    mapping_contract_path = output_dir / "ravafcast-snowpack-mapping.json"
    mapping_contract_path.write_bytes(mapping_bytes)
    interpolation_contract_path = output_dir / "meteoio-interpolation-policy.json"
    interpolation_contract_path.write_bytes(interpolation_bytes)
    raw_path = output_dir / "raw-source.json"
    raw_path.write_bytes(raw_bytes)
    corrected_path = output_dir / "corrected-samples.json"
    corrected_path.write_bytes(_canonical_bytes(records))
    raw_sha256 = _sha256_bytes(raw_bytes)
    corrected_sha256 = _sha256_bytes(corrected_path.read_bytes())

    site = HimalayanSiteSpec(
        site_id=site_data["site_id"],
        source_point_index=0,
        source_snapshot_id=f"historical-forecast-{_MODEL}-{source_start.date()}-{end_exclusive.date()}",
        source_id=_SOURCE_ID,
        source_elevation_m=float(source_elevation),
        target_elevation_m=float(site_data["dem_elevation_m"]),
        slope_deg=float(site_data["slope_deg"]),
        aspect_deg=float(site_data["aspect_deg"]),
        native_resolution_m=_SOURCE_NATIVE_RESOLUTION_M,
        target_resolution_m=_TARGET_RESOLUTION_M,
        snow_temperature_c=-2.0,
        rain_temperature_c=2.0,
        exposure_factor=1.0,
        precipitation_scale=1.0,
        precipitation_scale_source="candidate_neutral_correction",
        apply_shortwave_terrain=False,
    )
    transformed_samples: list[dict[str, Any]] = []
    metadata: list[Any] = []
    for offset in range(0, len(records), _CHUNK_HOURS):
        chunk_end = min(offset + _CHUNK_HOURS, len(records))
        chunk = _chunk_response(records, offset, chunk_end, latitude=latitude, longitude=longitude)
        request = OpenMeteoRunRequest(
            latitudes=(latitude,),
            longitudes=(longitude,),
            model_id=_MODEL,
            run_id=source_start.strftime("%Y-%m-%dT%H:%M"),
            forecast_hours=chunk_end - offset,
            hourly_variables=_HOURLY_VARIABLES,
        )
        payload = parse_open_meteo_single_run(chunk, request, raw_payload=_canonical_bytes(chunk))
        transformed = build_himalayan_snowpack_forcing(payload, site)
        transformed_samples.extend(transformed.samples)
        metadata.extend(transformed.resolution_metadata)

    combined = HimalayanSnowpackForcing(
        site=site,
        model_id=_MODEL,
        source_run_id=f"historical_forecast_replay:{simulation_start.date()}:{end_exclusive.date()}",
        raw_payload_sha256=raw_sha256,
        corrected_payload_sha256=corrected_sha256,
        samples=tuple(transformed_samples),
        resolution_metadata=tuple(metadata),
    )
    combined.validate()
    transformed_path = output_dir / "transformed-samples.json"
    transformed_path.write_bytes(_canonical_bytes(list(transformed_samples)))
    transformed_sha256 = _sha256_bytes(transformed_path.read_bytes())
    # MeteoIO's SMET plugin resolves a station's forcing from the station ID
    # and expects the corresponding <station_id>.smet filename.
    smet_path = output_dir / f"{site_data['site_id']}.smet"
    written = write_himalayan_smet(
        combined,
        output_path=smet_path,
        station_id=site_data["site_id"],
        latitude=float(site_data["latitude"]),
        longitude=float(site_data["longitude"]),
    )
    manifest = {
        "schema_version": "pir_panjal_poc_forcing_candidate_v1",
        "case_id": case.case_id,
        "region_key": case.region_key,
        "elevation_band": case.elevation_band,
        "horizon_hours": case.horizon_hours,
        "ensemble_members": case.ensemble_members,
        "source_id": _SOURCE_ID,
        "model_id": _MODEL,
        "forecast_role": "historical_forecast_replay_not_operational_forecast",
        "source_url": source_url,
        "source_point": {
            "latitude": latitude,
            "longitude": longitude,
            "requested_elevation_m": site_data["source_elevation_m"],
            **provider_metadata,
        },
        "target_site": dict(site_data),
        "valid_from": _iso(simulation_start),
        "valid_to": _iso(end_exclusive),
        "sample_count": int((end_exclusive - simulation_start).total_seconds() // 3600),
        "source_window": {
            "start": _iso(source_start),
            "end": _iso(end_exclusive),
        },
        "warmup_hours": int((simulation_start - source_start).total_seconds() // 3600),
        "source_sample_count": len(transformed_samples),
        "units_from_source": units,
        "target_resolution_m": _TARGET_RESOLUTION_M,
        "source_native_resolution_m": _SOURCE_NATIVE_RESOLUTION_M,
        "effective_information_scale_m": _EFFECTIVE_INFORMATION_SCALE_M,
        "no_3km_skill_claim": True,
        "unit_transforms": {
            "windspeed_10m": "km/h to m/s by division by 3.6",
            "snowfall": "provider centimetres; preserved as source metadata and null when unavailable",
            "snow_depth": "provider metres; source QA only, not assimilated as SNOWPACK HS",
            "terrestrial_radiation": "provider top-of-atmosphere solar radiation; retained as provenance only and never mapped to SNOWPACK ILWR",
        },
        "ravafcast_mapping_contract": {
            "path": mapping_contract_path.name,
            "sha256": mapping_sha256,
            "status": mapping_contract.get("status", "unresolved"),
        },
        "geometry": geometry,
        "resolution": {
            "target_grid_m": _TARGET_RESOLUTION_M,
            "source_native_resolution_m": _SOURCE_NATIVE_RESOLUTION_M,
            "effective_information_scale_m": _EFFECTIVE_INFORMATION_SCALE_M,
            "source_resolution_basis": "Open-Meteo documents approximately 13 km GFS surface scale; the complete bundle is conservatively bounded by approximately 25 km fields",
            "no_3km_skill_claim": True,
        },
        "input_quality": {
            "core_variables": list(_CORE_RAW_VARIABLES),
            "optional_variables": sorted(_OPTIONAL_RAW_VARIABLES),
            "null_counts": {
                variable: sum(
                    record.get(_NORMALIZED_FIELD_NAMES.get(variable, variable)) is None
                    for record in records
                )
                for variable in _RAW_VARIABLES
            },
            "direct_snowfall_available_samples": sum(
                record.get("snowfall") is not None for record in records
            ),
            "source_snow_depth_available_samples": sum(
                record.get("snow_depth") is not None for record in records
            ),
            "core_missing_action": "abort_before_native_run",
            "optional_missing_action": "preserve_null_or_source_qa_only",
        },
        "raw_payload_sha256": raw_sha256,
        "corrected_payload_sha256": corrected_sha256,
        "smet_sha256": written.smet_sha256,
        "artifacts": {
            "raw_source": {"path": raw_path.name, "sha256": raw_sha256},
            "corrected_samples": {"path": corrected_path.name, "sha256": corrected_sha256},
            "transformed_samples": {"path": transformed_path.name, "sha256": transformed_sha256},
            "smet": {"path": smet_path.name, "sha256": written.smet_sha256},
            "ravafcast_mapping": {"path": mapping_contract_path.name, "sha256": mapping_sha256},
            "meteoio_policy_contract": {"path": interpolation_contract_path.name, "sha256": interpolation_sha256},
            "meteoio_policy": {"path": "meteoio-policy.json"},
        },
        "meteoio_policy": {
            **interpolation_contract,
            "mode": "explicit_upstream_input_qa",
            "cadence_hours": 1,
            "precipitation_resampling": "PSUM::resample=accumulate over 3600 seconds",
            "warmup_boundary": "two provider-sourced days before simulation_start; excluded from the case sample_count",
            "core_missing_action": "abort_before_native_run",
            "optional_snowfall": "preserve_null; no zero substitution",
            "optional_snow_depth": "source_qa_only; not assimilated as HS",
            "interpolation_or_generator_events": 0,
            "contract_sha256": interpolation_sha256,
            "note": "The candidate source is validated hourly before MeteoIO; undocumented MeteoIO defaults are not used to repair material gaps.",
        },
        "initial_state_manifest_sha256": case.initial_state["manifest_sha256"],
        "license_review_status": "pending",
        "research_only": True,
        "training_eligible": False,
        "production_eligible": False,
        "can_enter_forcing_pipeline": False,
        "site_specific_validation": False,
        "native_execution_ready": False,
        "limitations": [
            "historical forecast replay is not a live or as-issued 48-hour forecast run",
            "source licence review is pending",
            "candidate terrain and precipitation-phase parameters are not Himalayan calibrated",
            "GFS target grid is 3 km metadata only; effective source information is coarser",
            "direct snowfall is unavailable when the provider returns null; RF snowfall-derived features are withheld",
            "source snow depth is retained for QA and is not assimilated as SNOWPACK HS",
            "the associated HiAVAL event is regional context, not a site-specific accuracy label",
        ],
    }
    policy_path = output_dir / "meteoio-policy.json"
    policy_path.write_bytes(_canonical_bytes(manifest["meteoio_policy"]))
    policy_sha256 = _sha256_bytes(policy_path.read_bytes())
    manifest["artifacts"]["meteoio_policy"]["sha256"] = policy_sha256
    manifest["meteoio_policy_sha256"] = policy_sha256
    manifest_path = output_dir / "forcing-manifest.json"
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))
    manifest_sha256 = _sha256_bytes(manifest_path.read_bytes())
    (output_dir / "forcing-manifest.json.sha256").write_text(
        f"{manifest_sha256}  {manifest_path.name}\n", encoding="ascii"
    )
    manifest["manifest_sha256"] = manifest_sha256
    manifest["manifest_sha256_path"] = "forcing-manifest.json.sha256"
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-manifest",
        type=Path,
        default=Path("docs/MVP4/00_governance/PIR_PANJAL_POC_CASE_MANIFEST.json"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = build_candidate_forcing(case_path=args.case_manifest, output_dir=args.output_dir)
    except (PirPanjalForcingBuildError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "candidate_forcing_built",
        "case_id": manifest["case_id"],
        "sample_count": manifest["sample_count"],
        "valid_from": manifest["valid_from"],
        "valid_to": manifest["valid_to"],
        "raw_payload_sha256": manifest["raw_payload_sha256"],
        "corrected_payload_sha256": manifest["corrected_payload_sha256"],
        "smet_sha256": manifest["smet_sha256"],
        "research_only": manifest["research_only"],
        "native_execution_ready": manifest["native_execution_ready"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
