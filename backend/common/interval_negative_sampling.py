"""Deterministic exclusion policy for interval-censored negative candidates.

This module defines the safety boundary for future interval-negative sampling;
it does not sample a model dataset or activate the timestamp-only training
path. Candidates are rejected when they are spatially close to a positive
interval and their half-open time windows overlap after the explicit temporal
buffer is applied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


INTERVAL_NEGATIVE_SAMPLING_VERSION = "interval_negative_sampling_policy_v1"


class IntervalNegativeSamplingError(ValueError):
    """Raised when interval negative-sampling inputs violate the contract."""


@dataclass(frozen=True)
class IntervalNegativeSamplingPolicy:
    """Conservative, explicit exclusion values for interval candidates."""

    spatial_exclusion_m: float = 5000.0
    temporal_buffer_before_hours: float = 24.0
    temporal_buffer_after_hours: float = 24.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.spatial_exclusion_m) or self.spatial_exclusion_m < 0:
            raise ValueError("spatial_exclusion_m must be finite and non-negative")
        if (
            not math.isfinite(self.temporal_buffer_before_hours)
            or self.temporal_buffer_before_hours < 0
        ):
            raise ValueError("temporal_buffer_before_hours must be finite and non-negative")
        if (
            not math.isfinite(self.temporal_buffer_after_hours)
            or self.temporal_buffer_after_hours < 0
        ):
            raise ValueError("temporal_buffer_after_hours must be finite and non-negative")


def _timestamp(value: Any, *, field: str, row_id: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise IntervalNegativeSamplingError(f"{row_id}: missing {field}")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntervalNegativeSamplingError(f"{row_id}: invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntervalNegativeSamplingError(f"{row_id}: {field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _coordinate(value: Any, *, field: str, row_id: str, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise IntervalNegativeSamplingError(f"{row_id}: invalid {field}") from exc
    if not math.isfinite(parsed) or not lower <= parsed <= upper:
        raise IntervalNegativeSamplingError(f"{row_id}: invalid {field}")
    return parsed


def _interval(row: Mapping[str, Any], *, row_id: str, label: str) -> tuple[datetime, datetime, float, float, str]:
    if not isinstance(row, Mapping):
        raise IntervalNegativeSamplingError(f"{label} {row_id}: row must be an object")
    for point_field in ("event_time", "timestamp"):
        if row.get(point_field) not in (None, ""):
            raise IntervalNegativeSamplingError(
                f"{label} {row_id}: point-time fields are forbidden in interval sampling"
            )
    precision = str(row.get("timestamp_precision") or row.get("precision") or "").strip().lower()
    if precision not in {"day", "interval", "bounded_12_day_detection_interval"}:
        raise IntervalNegativeSamplingError(
            f"{label} {row_id}: interval precision is required"
        )
    start = _timestamp(
        row.get("interval_start") or row.get("event_time_start"),
        field="interval_start",
        row_id=row_id,
    )
    end = _timestamp(
        row.get("interval_end") or row.get("event_time_end"),
        field="interval_end",
        row_id=row_id,
    )
    if end <= start:
        raise IntervalNegativeSamplingError(
            f"{label} {row_id}: interval_end must be after interval_start"
        )
    lat = _coordinate(row.get("lat"), field="lat", row_id=row_id, lower=-90.0, upper=90.0)
    lng = _coordinate(row.get("lng"), field="lng", row_id=row_id, lower=-180.0, upper=180.0)
    region_key = str(row.get("region_key") or "").strip()
    if not region_key:
        raise IntervalNegativeSamplingError(f"{label} {row_id}: region_key is required")
    return start, end, lat, lng, region_key


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _row_id(row: Mapping[str, Any], *, index: int, label: str) -> str:
    value = str(
        row.get("source_event_id")
        or row.get("event_id")
        or row.get("candidate_id")
        or row.get("row_id")
        or ""
    ).strip()
    return value or f"{label}:{index}"


def filter_interval_negative_candidates(
    candidates: Iterable[Mapping[str, Any]],
    positive_intervals: Iterable[Mapping[str, Any]],
    *,
    policy: IntervalNegativeSamplingPolicy | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return candidates not protected by a nearby positive interval.

    Time comparisons use half-open intervals. A candidate beginning exactly at
    the end of the buffered positive interval is therefore eligible. The
    function is deterministic and preserves candidate order.
    """

    selected_policy = policy or IntervalNegativeSamplingPolicy()
    positives: list[tuple[datetime, datetime, float, float, str, str]] = []
    for index, row in enumerate(positive_intervals):
        row_id = _row_id(row, index=index, label="positive")
        if row.get("label") not in (1, True):
            raise IntervalNegativeSamplingError(f"positive {row_id}: label must be one")
        start, end, lat, lng, region_key = _interval(row, row_id=row_id, label="positive")
        positives.append((start, end, lat, lng, region_key, row_id))

    accepted: list[dict[str, Any]] = []
    excluded_reason_counts: dict[str, int] = {}
    for index, candidate in enumerate(candidates):
        row_id = _row_id(candidate, index=index, label="candidate")
        if candidate.get("label") not in (0, False, None):
            raise IntervalNegativeSamplingError(f"candidate {row_id}: label must be zero")
        start, end, lat, lng, region_key = _interval(candidate, row_id=row_id, label="candidate")
        excluded_reason = None
        for positive_start, positive_end, positive_lat, positive_lng, positive_region, _ in positives:
            if region_key != positive_region:
                continue
            if _haversine_m(lat, lng, positive_lat, positive_lng) > selected_policy.spatial_exclusion_m:
                continue
            protected_start = positive_start - timedelta(
                hours=selected_policy.temporal_buffer_before_hours
            )
            protected_end = positive_end + timedelta(
                hours=selected_policy.temporal_buffer_after_hours
            )
            if start < protected_end and end > protected_start:
                excluded_reason = "near_positive_interval"
                break
        if excluded_reason is not None:
            excluded_reason_counts[excluded_reason] = (
                excluded_reason_counts.get(excluded_reason, 0) + 1
            )
            continue
        accepted.append(dict(candidate))

    candidate_count = len(accepted) + sum(excluded_reason_counts.values())
    return accepted, {
        "version": INTERVAL_NEGATIVE_SAMPLING_VERSION,
        "candidate_count": candidate_count,
        "accepted_count": len(accepted),
        "excluded_count": sum(excluded_reason_counts.values()),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "positive_interval_count": len(positives),
        "point_time_synthesis": False,
        "policy": {
            "spatial_exclusion_m": selected_policy.spatial_exclusion_m,
            "temporal_buffer_before_hours": selected_policy.temporal_buffer_before_hours,
            "temporal_buffer_after_hours": selected_policy.temporal_buffer_after_hours,
            "half_open_intervals": True,
        },
    }
