from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: object) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coverage_state(row: dict[str, object]) -> str:
    direct = row.get('sar_coverage_state')
    if isinstance(direct, str) and direct.strip():
        return direct
    coverage_flags = _as_dict(row.get('coverage_flags'))
    nested = coverage_flags.get('sar_coverage_state')
    if isinstance(nested, str) and nested.strip():
        return nested
    return 'unknown'


def _snowpack_proxy_available(row: dict[str, object]) -> bool:
    proxy = _as_dict(row.get('snowpack_proxy'))
    return any(
        _coerce_float(proxy.get(key)) is not None
        for key in ('estimated_shear_strength', 'snow_settlement_index')
    )


def _weather_freshness_hours(generated_at: object) -> float | None:
    if isinstance(generated_at, str) and generated_at.strip():
        parsed = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        return max(0.0, round(delta.total_seconds() / 3600, 3))
    return None


def build_source_health_summary(
    *,
    rows: list[dict[str, object]],
    weather_inputs: list[dict[str, object]],
    sar_evidence: dict[str, Any] | None,
    region_status: str,
    generated_at: object,
    evidence_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ready_rows = [row for row in rows if row.get('status') == 'ready']
    coverage_states = [_coverage_state(row) for row in ready_rows]
    low_sar_count = sum(1 for state in coverage_states if state not in {'full_coverage', 'not_applicable'})
    if not coverage_states:
        sar_coverage_mode = 'unknown'
    else:
        unique_states = {state for state in coverage_states}
        sar_coverage_mode = unique_states.pop() if len(unique_states) == 1 else 'mixed'
    snowpack_proxy_ready_count = sum(1 for row in ready_rows if _snowpack_proxy_available(row))
    weather_available = bool(weather_inputs)
    terrain_available = any(row.get('availability_reason') != 'unavailable_terrain' for row in rows) if rows else False
    recent_activity_backing = _coerce_int(_as_dict(evidence_summary).get('positive_count'))
    recent_activity_available = recent_activity_backing > 0
    completeness_signals = [
        weather_available,
        terrain_available,
        snowpack_proxy_ready_count > 0,
        recent_activity_available,
    ]
    overall_completeness = round(sum(1 for signal in completeness_signals if signal) / len(completeness_signals), 3)
    missing_features: list[str] = []
    if not weather_available:
        missing_features.append('weather_inputs')
    if not terrain_available:
        missing_features.append('terrain_inputs')
    if snowpack_proxy_ready_count == 0:
        missing_features.append('snowpack_proxy')
    if not recent_activity_available:
        missing_features.append('recent_activity_context')
    sar_masks = _as_list(_as_dict(sar_evidence).get('mask_asset_refs'))
    sar_geometries = _as_list(_as_dict(sar_evidence).get('sar_event_geometries'))
    return {
        'summary_version': 'source_health_v1',
        'region_status': region_status,
        'weather_available': weather_available,
        'weather_source': 'open_meteo_forecast_downscaled_v1' if weather_available else None,
        'weather_freshness_hours': _weather_freshness_hours(generated_at),
        'terrain_available': terrain_available,
        'snowpack_proxy_available': snowpack_proxy_ready_count > 0,
        'snowpack_proxy_ready_cell_count': snowpack_proxy_ready_count,
        'snowpack_proxy_ready_cell_share': round(snowpack_proxy_ready_count / len(ready_rows), 3) if ready_rows else 0.0,
        'sar_coverage_mode': sar_coverage_mode,
        'low_sar_coverage_ready_cell_count': low_sar_count,
        'low_sar_coverage_ready_cell_share': round(low_sar_count / len(ready_rows), 3) if ready_rows else 0.0,
        'sar_mask_asset_count': len(sar_masks),
        'sar_event_geometry_count': len(sar_geometries),
        'recent_activity_available': recent_activity_available,
        'field_event_backing_count': _coerce_int(_as_dict(evidence_summary).get('manual_positive_count')),
        'autonomous_event_backing_count': _coerce_int(_as_dict(evidence_summary).get('autonomous_positive_count')),
        'overall_completeness': overall_completeness,
        'missing_features': missing_features,
        'support_status': 'complete' if overall_completeness >= 0.75 else 'partial' if overall_completeness > 0 else 'degraded',
    }


def build_feature_completeness_row(
    *,
    source_health: dict[str, Any],
    forecast_id: str | None = None,
    forecast_grid_id: str | None = None,
    forecast_run_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'overall_completeness': float(source_health.get('overall_completeness') or 0.0),
        'weather_available': bool(source_health.get('weather_available')),
        'weather_source': source_health.get('weather_source'),
        'weather_freshness_hours': _coerce_int(source_health.get('weather_freshness_hours')),
        'snow_cover_available': False,
        'snow_cover_snapshot_id': None,
        'snow_cover_age_hours': None,
        'recent_activity_available': bool(source_health.get('recent_activity_available')),
        'recent_activity_feature_id': None,
        'recent_activity_window_days': 7 if source_health.get('recent_activity_available') else None,
        'terrain_available': bool(source_health.get('terrain_available')),
        'missing_features': [str(item) for item in _as_list(source_health.get('missing_features'))],
    }
    if forecast_id:
        payload['forecast_id'] = forecast_id
    if forecast_grid_id:
        payload['forecast_grid_id'] = forecast_grid_id
    if forecast_run_id:
        payload['forecast_run_id'] = forecast_run_id
    return payload


def build_decision_provenance(
    *,
    threshold_profile: str,
    calibration_profile_version: str | None,
    calibration_method: str | None,
    frequency_threshold_profile: str | None,
    derived_from: dict[str, Any] | None,
    explainability_mode: str,
    selected_feature_count: int,
) -> dict[str, Any]:
    threshold_origin = 'heuristic_seeded' if threshold_profile.startswith('heuristic') else 'evaluation_derived'
    frequency_policy = frequency_threshold_profile or 'implicit_frequency_policy'
    dominant_mapping = (
        'heuristic_thresholds_and_frequency'
        if threshold_origin == 'heuristic_seeded'
        else 'model_calibrated_thresholds'
    )
    return {
        'summary_version': 'decision_provenance_v1',
        'threshold_profile': threshold_profile,
        'threshold_profile_origin': threshold_origin,
        'calibration_profile_version': calibration_profile_version,
        'calibration_method': calibration_method,
        'frequency_threshold_profile': frequency_policy,
        'aggregation_policy': _as_dict(derived_from).get('aggregation'),
        'frequency_basis': _as_dict(derived_from).get('frequency_basis'),
        'dominant_mapping': dominant_mapping,
        'explainability_mode': explainability_mode,
        'selected_feature_count': int(selected_feature_count),
    }


def build_latest_benchmark_summary(
    *,
    benchmark_kind: str,
    phase_breakdown_seconds: dict[str, float],
    input_context: dict[str, Any],
    status: str,
    artifact_ref: str | None = None,
) -> dict[str, Any]:
    total_seconds = round(sum(float(value) for value in phase_breakdown_seconds.values()), 3)
    return {
        'summary_version': 'runtime_benchmark_v1',
        'benchmark_kind': benchmark_kind,
        'status': status,
        'total_seconds': total_seconds,
        'phase_breakdown_seconds': {
            key: round(float(value), 3)
            for key, value in phase_breakdown_seconds.items()
        },
        'input_context': input_context,
        'artifact_ref': artifact_ref,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
    }


def load_benchmark_summary_from_artifact(artifact_path: Path) -> dict[str, Any] | None:
    if not artifact_path.exists():
        return None
    payload = artifact_path.read_text(encoding='utf-8')
    try:
        import json

        parsed = json.loads(payload)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def mean_feature_overlap(feature_sets: Iterable[set[str]]) -> float:
    normalized = [feature_set for feature_set in feature_sets if feature_set]
    if len(normalized) < 2:
        return 1.0 if normalized else 0.0
    overlaps: list[float] = []
    for idx, left in enumerate(normalized):
        for right in normalized[idx + 1:]:
            union = left | right
            overlaps.append(len(left & right) / len(union) if union else 1.0)
    return round(mean(overlaps), 6) if overlaps else 0.0
