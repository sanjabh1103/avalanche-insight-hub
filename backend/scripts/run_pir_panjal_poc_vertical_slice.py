#!/usr/bin/env python3
"""Run and package one candidate Pir Panjal native vertical slice.

This command is intentionally a candidate/evidence builder, not a release
promoter.  It consumes an already-built forcing package, starts SNOWPACK from
an explicit zero-layer candidate seed, parses the final native profile, and
optionally evaluates the existing RF comparison artifact on the same feature
row.  The resulting JSON remains ``pipeline-proof-only`` and records every
known limitation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import warnings
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.meteoio_openmeteo import (
    generate_snowpack_config,
    _last_smet_timestamp,
    parse_snowpack_pro,
    run_snowpack_native,
    write_snow_free_smet_profile,
)
from backend.common.pir_panjal_poc_case import (
    load_pir_panjal_poc_case,
    validate_pir_panjal_forcing_consistency,
)
from backend.common.real_features import build_real_feature_row
from backend.common.snowpack_physics import SnowpackPhysicsResult
from backend.common.snowpack_proxy import SnowpackProxy


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_ROOT = Path(__file__).resolve().parents[2]


class PirPanjalVerticalSliceError(RuntimeError):
    """Raised when the candidate slice cannot be built without guessing."""


def _sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PirPanjalVerticalSliceError(f"not a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PirPanjalVerticalSliceError(f"invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise PirPanjalVerticalSliceError(f"JSON root must be an object: {path}")
    return value


def _require_empty_output_dir(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise PirPanjalVerticalSliceError(f"output directory is symlinked: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise PirPanjalVerticalSliceError(
            f"output directory must be empty to prevent stale native artifacts: {path}"
        )


def _safe_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return _sha256_file(destination)


def _inventory(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        # A manifest cannot contain a stable hash of itself.  Keep the result
        # document outside this inventory rather than recording a stale
        # self-hash that would look authoritative to a later reader.
        if item.name == "candidate-result.json":
            continue
        records.append({
            "path": item.relative_to(path).as_posix(),
            "size_bytes": item.stat().st_size,
            "sha256": _sha256_file(item),
        })
    return records


def _native_runtime_warning_summary(output_dir: Path, log_path: str) -> dict[str, Any]:
    """Expose warnings from the native log without treating them as failures."""
    candidates: list[Path] = []
    if log_path:
        declared = Path(log_path)
        candidates.extend((declared, output_dir / declared.name))
    candidates.extend(sorted(output_dir.glob('*.log')))
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            lines = candidate.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        warnings_found = [line.strip() for line in lines if '[W]' in line]
        return {
            'status': 'recorded',
            'log_path': candidate.name,
            'warnings': warnings_found,
        }
    return {
        'status': 'unavailable',
        'log_path': '',
        'warnings': [],
    }


def _physics_result(parsed: dict[str, Any]) -> SnowpackPhysicsResult:
    return SnowpackPhysicsResult(
        weak_layer_depth_m=float(parsed["weak_layer_depth_m"]),
        weak_layer_grain_type=str(parsed["weak_layer_grain_type"]),
        weak_layer_shear_strength_kpa=float(parsed["weak_layer_shear_strength_kpa"]),
        snowpack_stability_index=float(parsed["snowpack_stability_index"]),
        temperature_gradient_per_m=float(parsed["temperature_gradient_per_m"]),
        liquid_water_content_pct=float(parsed["liquid_water_content_pct"]),
        layer_count=int(parsed["layer_count"]),
        snow_height_m=float(parsed["snow_height_m"]),
        bulk_density_kgm3=float(parsed["bulk_density_kgm3"]),
        method="snowpack_native",
        layers=list(parsed.get("layers") or []),
    )


def _build_rf_comparison(
    *,
    model_path: Path | None,
    forcing_dir: Path,
    site: dict[str, Any],
    physics: SnowpackPhysicsResult,
    as_of: datetime,
) -> dict[str, Any]:
    """Run the existing RF baseline, or explicitly record why it was not run."""
    if model_path is None:
        return {
            "status": "not_run",
            "reason": "no RF model artifact was supplied",
            "eligible_for_accuracy_claim": False,
        }
    if model_path.is_symlink() or not model_path.is_file():
        return {
            "status": "not_run",
            "reason": f"RF model artifact is not a regular file: {model_path}",
            "eligible_for_accuracy_claim": False,
        }

    corrected_path = forcing_dir / "corrected-samples.json"
    samples = json.loads(corrected_path.read_text(encoding="utf-8"))
    if not isinstance(samples, list) or not samples:
        raise PirPanjalVerticalSliceError("corrected forcing samples are unavailable for RF comparison")
    recent = [item for item in samples if isinstance(item, dict)][-25:]
    last = recent[-1]
    weather_sample = dict(last)
    weather_sample["windspeed_10m"] = weather_sample.pop("wind_speed_10m")
    weather_sample["winddirection_10m"] = weather_sample.pop("wind_direction_10m")
    weather_sample["precipitation_24h"] = sum(float(item.get("precipitation") or 0.0) for item in recent[:-1])
    weather_sample["snow_depth"] = physics.snow_height_m
    weather_sample["freezing_level_height"] = float(site["dem_elevation_m"]) + float(weather_sample.get("temperature_2m") or 0.0) / 0.0065

    direct_snowfall_available = any(
        any(key in item and item[key] is not None for key in ("snowfall_24h", "snowfall"))
        for item in recent
    )
    if direct_snowfall_available:
        if last.get("snowfall_24h") is not None:
            weather_sample["snowfall_24h"] = float(last["snowfall_24h"])
        else:
            weather_sample["snowfall_24h"] = sum(
                float(item.get("snowfall") or 0.0) for item in recent[-24:]
            )
    feature_quality = {
        "snowfall_24h": "available" if direct_snowfall_available else "unavailable",
    }
    if not direct_snowfall_available:
        return {
            "status": "not_run",
            "reason": "RF comparison withheld because direct snowfall is unavailable; no zero substitute was used",
            "missing_features": ["snowfall_24h"],
            "feature_quality": feature_quality,
            "eligible_for_accuracy_claim": False,
            "limitations": [
                "candidate forcing does not provide direct snowfall or defensible snowfall-derived features",
                "RF comparison was withheld rather than imputing an unknown snowfall value as zero",
            ],
        }

    # Keep the native candidate runnable in the slim local Docker image when
    # the comparison lane is correctly withheld.  Heavy RF dependencies are
    # needed only after direct snowfall has passed the explicit gate.
    import joblib
    import pandas as pd

    aspect = float(site["aspect_deg"])
    import math

    terrain = {
        "elevation_m": float(site["dem_elevation_m"]),
        "aspect_deg": aspect,
        "slope_angle_deg": float(site["slope_deg"]),
        "terrain_roughness": 20.0,
        "curvature_proxy": 0.0,
        "northness": (1.0 + math.cos(math.radians(aspect))) / 2.0,
        "eastness": (1.0 + math.sin(math.radians(aspect))) / 2.0,
    }
    proxy = SnowpackProxy(
        estimated_shear_strength=physics.weak_layer_shear_strength_kpa,
        snow_settlement_index=max(0.0, min(1.0, 1.0 - physics.bulk_density_kgm3 / 600.0)),
        season_start="2023-10-01",
        method="native_case_bridge",
        source_class="proxy",
        source="native_snowpack_profile",
        uncertainty=0.5,
        quality_flags=("candidate_only", "native_profile_bridge"),
        execution_status="fallback_proxy",
    )
    warning_messages: list[str] = []
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            bundle = joblib.load(model_path)
        except Exception as exc:
            return {
                "status": "not_run",
                "reason": f"RF model artifact could not be loaded: {exc}",
                "eligible_for_accuracy_claim": False,
            }
        warning_messages = list(dict.fromkeys(str(item.message) for item in captured))
    if not isinstance(bundle, dict):
        raise PirPanjalVerticalSliceError("RF model bundle must be a JSON-like mapping")
    required = ("feature_columns", "selected_features", "selector", "calibrated_model")
    missing = [key for key in required if key not in bundle]
    if missing:
        raise PirPanjalVerticalSliceError(f"RF model bundle is missing {missing}")

    assembled = build_real_feature_row(
        weather_sample=weather_sample,
        terrain=terrain,
        timestamp=as_of,
        lat=float(site["latitude"]),
        lng=float(site["longitude"]),
        snowpack_proxy_override=proxy,
        snowpack_physics_override=physics,
        history_samples=recent[:-1],
    )
    feature_frame = pd.DataFrame([assembled["feature_row"]], columns=bundle["feature_columns"])
    selected_frame = pd.DataFrame(
        bundle["selector"].transform(feature_frame),
        columns=bundle["selected_features"],
    )
    probability = float(bundle["calibrated_model"].predict_proba(selected_frame)[:, 1][0])
    return {
        "status": "completed_candidate_comparison",
        "role": "transparent_rf_comparison_baseline",
        "probability_positive": probability,
        "predicted_class_at_0_5": int(probability >= 0.5),
        "model_path": str(model_path),
        "model_sha256": _sha256_file(model_path),
        "model_version": str(bundle.get("surrogate_model_version") or bundle.get("created_at") or "unknown"),
        "selected_features": list(bundle["selected_features"]),
        "feature_quality": feature_quality,
        "scikit_learn_restore_warnings": warning_messages,
        "eligible_for_accuracy_claim": False,
        "limitations": [
            "model was not trained or independently validated for Pir Panjal",
            "candidate forcing lacks a direct snowfall variable; snowfall-derived features were marked unavailable",
            "this is a same-case comparison, not a skill score or operational forecast",
        ],
    }


def run_vertical_slice(
    *,
    case_path: Path,
    forcing_dir: Path,
    output_dir: Path,
    toolchain_manifest_path: Path,
    snowpack_home: Path,
    rf_model_path: Path | None = None,
    run_id: str = "pir-panjal-gulmarg-wd-2024-02-22-native-candidate",
) -> dict[str, Any]:
    case = load_pir_panjal_poc_case(case_path, repository_root=_ROOT, verify_files=True)
    case_record = json.loads(case.raw_bytes.decode("utf-8"))
    evaluation_window = case_record.get("evaluation_window")
    if not isinstance(evaluation_window, dict):
        raise PirPanjalVerticalSliceError("case manifest evaluation_window is missing")
    forcing_manifest_path = forcing_dir / "forcing-manifest.json"
    forcing_manifest = _read_json_object(forcing_manifest_path)
    validate_pir_panjal_forcing_consistency(case, forcing_manifest)
    if forcing_manifest.get("case_id") != case.case_id:
        raise PirPanjalVerticalSliceError("forcing manifest case_id does not match case manifest")
    if forcing_manifest.get("region_key") != case.region_key or forcing_manifest.get("elevation_band") != case.elevation_band:
        raise PirPanjalVerticalSliceError("forcing manifest scope does not match Pir Panjal case")
    if forcing_manifest.get("production_eligible") is not False:
        raise PirPanjalVerticalSliceError("candidate forcing must not be production eligible")
    smet_name = str((forcing_manifest.get("artifacts") or {}).get("smet", {}).get("path") or "")
    smet_path = forcing_dir / smet_name
    smet_sha256 = _sha256_file(smet_path)
    expected_smet_sha256 = str(forcing_manifest.get("smet_sha256") or "")
    if not _SHA256.fullmatch(expected_smet_sha256) or smet_sha256 != expected_smet_sha256:
        raise PirPanjalVerticalSliceError("forcing SMET hash does not match its manifest")
    toolchain_manifest = _read_json_object(toolchain_manifest_path)
    _require_empty_output_dir(output_dir)
    station_id = str(case.site["site_id"])
    seed_path = output_dir / f"{station_id}.sno"
    write_snow_free_smet_profile(
        output_path=seed_path,
        station_id=station_id,
        latitude=float(case.site["latitude"]),
        longitude=float(case.site["longitude"]),
        elevation=float(case.site["dem_elevation_m"]),
        profile_date=str(case.initial_state["start"]),
        slope_angle=float(case.site["slope_deg"]),
        aspect=float(case.site["aspect_deg"]),
    )
    config_path = output_dir / "snowpack.ini"
    generate_snowpack_config(
        output_path=config_path,
        season_start_date=str(case.initial_state["start"])[:10],
        end_date=str(evaluation_window.get("end") or "2024-02-24")[:10],
        station_id=station_id,
        latitude=float(case.site["latitude"]),
        longitude=float(case.site["longitude"]),
        meteo_path=forcing_dir,
        output_dir=output_dir,
        initial_state_path=seed_path,
        experiment="candidate",
    )
    native_end_date = _last_smet_timestamp(smet_path)
    if native_end_date is None:
        raise PirPanjalVerticalSliceError("forcing SMET has no valid final timestamp")

    prior_env = {key: os.environ.get(key) for key in (
        "SNOWPACK_HOME", "SNOWPACK_TOOLCHAIN_MANIFEST_PATH", "SNOWPACK_IMAGE_ID",
        "SNOWPACK_IMAGE_ARCHIVE_SHA256", "SNOWPACK_IMAGE_REPOSITORY_DIGEST",
    )}
    os.environ["SNOWPACK_HOME"] = str(snowpack_home)
    os.environ["SNOWPACK_TOOLCHAIN_MANIFEST_PATH"] = str(toolchain_manifest_path)
    for key, manifest_key in (
        ("SNOWPACK_IMAGE_ID", "image_id"),
        ("SNOWPACK_IMAGE_ARCHIVE_SHA256", "image_archive_sha256"),
        ("SNOWPACK_IMAGE_REPOSITORY_DIGEST", "image_repository_digest"),
    ):
        os.environ[key] = str(toolchain_manifest.get(manifest_key) or "")
    try:
        evidence = run_snowpack_native(
            smet_path=smet_path,
            output_dir=output_dir,
            config_path=config_path,
            begin_date=str(case.initial_state["start"]).replace("Z", "")[:16],
            end_date=native_end_date,
            timeout_s=120,
            run_id=run_id,
            toolchain_id=str(toolchain_manifest.get("toolchain_id") or ""),
        )
    finally:
        for key, value in prior_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if evidence is None or not evidence.success or not evidence.pro_path:
        raise PirPanjalVerticalSliceError("native SNOWPACK execution did not complete")
    parsed = parse_snowpack_pro(Path(evidence.pro_path))
    profile_date = str(parsed["profile_date"])
    try:
        as_of = datetime.fromisoformat(profile_date.replace("Z", "+00:00"))
    except ValueError:
        try:
            as_of = datetime.strptime(profile_date, "%d.%m.%Y %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise PirPanjalVerticalSliceError(
                f"unsupported native SNOWPACK profile date: {profile_date!r}"
            ) from exc
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    physics = _physics_result(parsed)
    copied_case_hash = _safe_copy(case_path, output_dir / "input-manifests" / case_path.name)
    copied_forcing_hash = _safe_copy(forcing_manifest_path, output_dir / "input-manifests" / forcing_manifest_path.name)
    copied_toolchain_hash = _safe_copy(toolchain_manifest_path, output_dir / "input-manifests" / toolchain_manifest_path.name)
    initial_state_manifest_relative = str(case.initial_state.get("manifest_path") or "")
    if not initial_state_manifest_relative:
        raise PirPanjalVerticalSliceError("case manifest does not bind an initial-state manifest")
    initial_state_manifest_path = _ROOT / initial_state_manifest_relative
    if not initial_state_manifest_path.is_file() or initial_state_manifest_path.is_symlink():
        raise PirPanjalVerticalSliceError(
            f"initial-state manifest is not a regular repository file: {initial_state_manifest_path}"
        )
    initial_state_manifest_hash = _sha256_file(initial_state_manifest_path)
    expected_initial_state_hash = str(case.initial_state.get("manifest_sha256") or "")
    if initial_state_manifest_hash != expected_initial_state_hash:
        raise PirPanjalVerticalSliceError(
            "initial-state manifest hash does not match the case manifest"
        )
    copied_initial_state_hash = _safe_copy(
        initial_state_manifest_path,
        output_dir / "input-manifests" / initial_state_manifest_path.name,
    )
    copied_input_hashes = {
        "case_manifest": copied_case_hash,
        "forcing_manifest": copied_forcing_hash,
        "initial_state_manifest": copied_initial_state_hash,
        "toolchain_manifest": copied_toolchain_hash,
    }
    if isinstance(evidence.toolchain_manifest, dict):
        attested_toolchain_path = output_dir / "input-manifests" / "toolchain-manifest-attested.json"
        attested_toolchain_path.write_bytes(
            json.dumps(evidence.toolchain_manifest, indent=2, sort_keys=True).encode("utf-8")
        )
        copied_input_hashes["toolchain_manifest_attested"] = _sha256_file(attested_toolchain_path)
    rf_comparison = _build_rf_comparison(
        model_path=rf_model_path,
        forcing_dir=forcing_dir,
        site=dict(case.site),
        physics=physics,
        as_of=as_of,
    )
    native_runtime_warnings = _native_runtime_warning_summary(
        output_dir,
        str(evidence.log_path),
    )
    limitations = [
        "native run used a local Docker image; it is not an approved hosted runtime",
        "forcing is a historical forecast replay and its source licence review is pending",
        "site geometry and snow-free initial state are candidate assumptions",
        "the 3 km value is a computational target; effective source information remains approximately 25 km",
        "direct snowfall is unavailable where the provider returned null; no zero substitute was used",
        "the associated regional event is not a site-specific accuracy label",
        "outputs are pipeline interpretation only, not Partner validation or an official warning",
    ]
    if native_runtime_warnings['warnings']:
        limitations.append(
            "native log contains a precipitation re-accumulation advisory; resolve it before hosted or scientific-validation use",
        )
    result = {
        "schema_version": "pir_panjal_poc_native_candidate_v1",
        "status": "candidate_native_completed",
        "evidence_class": "pipeline-proof-only",
        "case_id": case.case_id,
        "region_key": case.region_key,
        "elevation_band": case.elevation_band,
        "horizon_hours": case.horizon_hours,
        "ensemble_members": case.ensemble_members,
        "run_id": run_id,
        "site": dict(case.site),
        "evaluation_window": evaluation_window,
        "native_execution_end_date": native_end_date,
        "case_manifest_sha256": case.manifest_sha256,
        "forcing_manifest_sha256": _sha256_file(forcing_manifest_path),
        "copied_input_hashes": copied_input_hashes,
        "initial_state": {
            "strategy": "candidate_snow_free_zero_layer_seed",
            "declaration_manifest": str(case.initial_state.get("manifest_path") or ""),
            "manifest_sha256": expected_initial_state_hash,
            "seed_path": seed_path.relative_to(output_dir).as_posix(),
            "seed_sha256": _sha256_file(seed_path),
            "approval_state": "candidate_only",
            "scientific_validation_eligible": False,
        },
        "forcing": {
            "manifest_path": forcing_manifest_path.name,
            "smet_path": smet_path.name,
            "smet_sha256": smet_sha256,
            "source_id": forcing_manifest.get("source_id"),
            "model_id": forcing_manifest.get("model_id"),
            "forecast_role": forcing_manifest.get("forecast_role"),
            "license_review_status": forcing_manifest.get("license_review_status"),
            "resolution": forcing_manifest.get("resolution"),
            "input_quality": forcing_manifest.get("input_quality"),
        },
        "native_execution": asdict(evidence),
        "native_runtime_warnings": native_runtime_warnings,
        "profile_summary": parsed,
        "rf_comparison": rf_comparison,
        "native_identity_scope": "local_docker_candidate_image_id_and_archive",
        "official_warning_eligible": False,
        "scientific_validation_eligible": False,
        "publish_eligible": False,
        "limitations": limitations,
    }
    (output_dir / "candidate-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    result["artifacts"] = _inventory(output_dir)
    (output_dir / "candidate-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-manifest", type=Path, default=_ROOT / "docs/MVP4/00_governance/PIR_PANJAL_POC_CASE_MANIFEST.json")
    parser.add_argument("--forcing-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--toolchain-manifest", type=Path, required=True)
    parser.add_argument("--snowpack-home", type=Path, required=True)
    parser.add_argument("--rf-model", type=Path)
    parser.add_argument("--run-id", default="pir-panjal-gulmarg-wd-2024-02-22-native-candidate")
    args = parser.parse_args(argv)
    try:
        result = run_vertical_slice(
            case_path=args.case_manifest,
            forcing_dir=args.forcing_dir,
            output_dir=args.output_dir,
            toolchain_manifest_path=args.toolchain_manifest,
            snowpack_home=args.snowpack_home,
            rf_model_path=args.rf_model,
            run_id=args.run_id,
        )
    except (OSError, ValueError, KeyError, PirPanjalVerticalSliceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": result["status"],
        "case_id": result["case_id"],
        "run_id": result["run_id"],
        "native_format": result["profile_summary"].get("native_format"),
        "snow_height_m": result["profile_summary"].get("snow_height_m"),
        "snowpack_stability_index": result["profile_summary"].get("snowpack_stability_index"),
        "rf_status": result["rf_comparison"].get("status"),
        "official_warning_eligible": result["official_warning_eligible"],
        "publish_eligible": result["publish_eligible"],
        "output_dir": str(args.output_dir),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
