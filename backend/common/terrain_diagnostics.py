"""Explain terrain-stage losses without changing terrain extraction policy."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from backend.common.real_features import TerrainUnavailableError


TERRAIN_DIAGNOSTICS_VERSION = "terrain_diagnostics_v2"
MAX_TERRAIN_LOSS_RATE = 0.02


def classify_terrain_failure(exc: BaseException) -> str:
    """Map a terrain exception to a stable, non-sensitive reason code."""
    message = str(exc).lower()
    exception_name = type(exc).__name__.lower()
    if isinstance(exc, TerrainUnavailableError) or "valid 3x3 dem window" in message:
        return "invalid_or_nodata_window"
    if any(token in message or token in exception_name for token in (
        "no such file",
        "not recognized as a supported file format",
        "rasterioioerror",
        "dem file",
    )):
        return "dem_read_error"
    if any(token in message or token in exception_name for token in (
        "crs",
        "transform",
        "coordinate",
        "projection",
    )):
        return "coordinate_transform_error"
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "terrain_value_error"
    return "unknown_terrain_error"


def count_runtime_terrain_failure_reasons(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Count specific terrain failure codes emitted by runtime grid rows.

    ``availability_reason`` remains the coarse compatibility field.  A
    missing specific code is deliberately counted as ``unknown_terrain_error``
    so older or hand-built rows cannot make terrain loss appear explained.
    """
    counts: Counter[str] = Counter()
    for row in rows:
        if row.get("availability_reason") != "unavailable_terrain":
            continue
        reason = str(row.get("terrain_failure_reason") or "unknown_terrain_error")
        counts[reason] += 1
    return dict(sorted(counts.items()))


def _count(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and value >= 0 else 0


def _int_value(mapping: Mapping[str, Any], key: str) -> int:
    return _count(mapping.get(key, 0))


def _nested_counts(mapping: Any) -> dict[str, dict[str, int]]:
    if not isinstance(mapping, Mapping):
        return {}
    result: dict[str, dict[str, int]] = {}
    for region, values in mapping.items():
        if not isinstance(values, Mapping):
            continue
        result[str(region)] = {
            str(reason): _count(value)
            for reason, value in values.items()
            if _count(value) > 0
        }
    return result


def _scalar_counts(mapping: Any) -> dict[str, int]:
    if not isinstance(mapping, Mapping):
        return {}
    return {
        str(key): _count(value)
        for key, value in mapping.items()
        if _count(value) > 0
    }


def _dimension_loss_breakdown(
    candidates: Any,
    missing_dem: Any,
    failed: Any,
    success: Any,
) -> dict[str, dict[str, Any]]:
    """Build comparable loss counts for a source or season dimension."""

    candidate_counts = _scalar_counts(candidates)
    missing_counts = _scalar_counts(missing_dem)
    failed_counts = _scalar_counts(failed)
    success_counts = _scalar_counts(success)
    keys = sorted(
        set(candidate_counts)
        | set(missing_counts)
        | set(failed_counts)
        | set(success_counts)
    )
    result: dict[str, dict[str, Any]] = {}
    for key in keys:
        candidate_rows = candidate_counts.get(key, 0)
        missing = missing_counts.get(key, 0)
        failed_rows = failed_counts.get(key, 0)
        loss_count = missing + failed_rows
        result[key] = {
            "candidate_rows": candidate_rows,
            "missing_dem": missing,
            "failed": failed_rows,
            "success": success_counts.get(key, 0),
            "loss_count": loss_count,
            "loss_rate": round(loss_count / candidate_rows, 6) if candidate_rows else None,
        }
    return result


def build_terrain_loss_report(debug_stats: Mapping[str, Any]) -> dict[str, Any]:
    """Return stage/source/season loss rates and stable reason counts."""
    raw_rows = _int_value(debug_stats, "raw_rows")
    candidate_rows = max(
        0,
        raw_rows
        - _int_value(debug_stats, "no_point")
        - _int_value(debug_stats, "no_timestamp")
        - _int_value(debug_stats, "no_region"),
    )
    missing_dem = _int_value(debug_stats, "no_dem")
    failed = _int_value(debug_stats, "terrain_failed")
    success = _int_value(debug_stats, "terrain_success")
    if not success:
        success = max(0, candidate_rows - missing_dem - failed)
    loss_count = missing_dem + failed
    loss_rate = round(loss_count / candidate_rows, 6) if candidate_rows else None
    assembled_ok = _int_value(debug_stats, "assembled_ok")
    post_terrain_loss = max(0, success - assembled_ok)

    candidates_by_region = {
        str(key): _count(value)
        for key, value in (debug_stats.get("terrain_candidates_by_region") or {}).items()
        if isinstance(value, (int, float)) and value >= 0
    }
    missing_by_region = {
        str(key): _count(value)
        for key, value in (debug_stats.get("terrain_missing_dem_by_region") or {}).items()
        if isinstance(value, (int, float)) and value >= 0
    }
    failed_by_region = {
        str(key): _count(value)
        for key, value in (debug_stats.get("terrain_failed_by_region") or {}).items()
        if isinstance(value, (int, float)) and value >= 0
    }
    success_by_region = {
        str(key): _count(value)
        for key, value in (debug_stats.get("terrain_success_by_region") or {}).items()
        if isinstance(value, (int, float)) and value >= 0
    }
    terrain_loss_by_region: dict[str, dict[str, Any]] = {}
    for region in sorted(
        set(candidates_by_region)
        | set(missing_by_region)
        | set(failed_by_region)
        | set(success_by_region)
    ):
        region_candidates = candidates_by_region.get(region, 0)
        region_loss = missing_by_region.get(region, 0) + failed_by_region.get(region, 0)
        terrain_loss_by_region[region] = {
            "candidate_rows": region_candidates,
            "missing_dem": missing_by_region.get(region, 0),
            "failed": failed_by_region.get(region, 0),
            "success": success_by_region.get(region, 0),
            "loss_count": region_loss,
            "loss_rate": round(region_loss / region_candidates, 6) if region_candidates else None,
        }

    terrain_loss_by_source = _dimension_loss_breakdown(
        debug_stats.get("terrain_candidates_by_source"),
        debug_stats.get("terrain_missing_dem_by_source"),
        debug_stats.get("terrain_failed_by_source"),
        debug_stats.get("terrain_success_by_source"),
    )
    terrain_loss_by_season = _dimension_loss_breakdown(
        debug_stats.get("terrain_candidates_by_season"),
        debug_stats.get("terrain_missing_dem_by_season"),
        debug_stats.get("terrain_failed_by_season"),
        debug_stats.get("terrain_success_by_season"),
    )

    return {
        "version": TERRAIN_DIAGNOSTICS_VERSION,
        "candidate_rows": candidate_rows,
        "terrain_success": success,
        "missing_dem": missing_dem,
        "terrain_failed": failed,
        "terrain_loss_count": loss_count,
        "terrain_loss_rate": loss_rate,
        "post_terrain_weather_or_governance_loss": post_terrain_loss,
        "failure_reasons": _scalar_counts(debug_stats.get("terrain_failure_reasons")),
        "failure_reasons_by_region": _nested_counts(debug_stats.get("terrain_failure_reasons_by_region")),
        "failure_reasons_by_source": _nested_counts(debug_stats.get("terrain_failure_reasons_by_source")),
        "failure_reasons_by_season": _nested_counts(debug_stats.get("terrain_failure_reasons_by_season")),
        "by_region": terrain_loss_by_region,
        "by_source": terrain_loss_by_source,
        "by_season": terrain_loss_by_season,
        "by_stage": {
            "terrain_assembly": {
                "candidate_rows": candidate_rows,
                "success": success,
                "loss_count": loss_count,
                "loss_rate": loss_rate,
            },
            "post_terrain_weather_or_governance": {
                "candidate_rows": success,
                "success": assembled_ok,
                "loss_count": post_terrain_loss,
                "loss_rate": round(post_terrain_loss / success, 6) if success else None,
            },
        },
    }


def validate_terrain_gate(report: Mapping[str, Any] | None) -> list[str]:
    """Return strict-training errors for missing or unexplained terrain loss."""
    if not isinstance(report, Mapping):
        return ["terrain_loss_report is missing"]
    errors: list[str] = []
    rate = report.get("terrain_loss_rate")
    if not isinstance(rate, (int, float)):
        errors.append("terrain_loss_rate is missing")
    elif float(rate) > MAX_TERRAIN_LOSS_RATE:
        errors.append(
            f"terrain loss rate {float(rate):.6f} exceeds {MAX_TERRAIN_LOSS_RATE:.6f}"
        )
    reasons = report.get("failure_reasons")
    if not isinstance(reasons, Mapping):
        errors.append("terrain failure reasons are missing")
    elif _count(reasons.get("unknown_terrain_error")):
        errors.append("terrain failure reasons include unknown_terrain_error")
    if not isinstance(report.get("by_region"), Mapping):
        errors.append("terrain per-region diagnostics are missing")
    return errors
