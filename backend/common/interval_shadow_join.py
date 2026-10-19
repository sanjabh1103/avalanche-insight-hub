"""Deterministic, shadow-only joins for bounded avalanche-label intervals.

This module deliberately does not turn an occurrence interval into a point
timestamp.  It joins a bounded label interval to a feature row only when the
feature validity window fully contains the label interval and the feature was
available no later than the interval start.  The result is an evidence/shadow
record; it is never a core-training or production-scoring row.

The module has no network, database, model, or training-path side effects.  It
is intentionally not wired into ``training_reproducibility.py`` yet because
that path remains timestamp-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Iterable, Mapping


INTERVAL_SHADOW_JOIN_VERSION = "interval_shadow_join_v1"
INTERVAL_LABEL_PRECISIONS = frozenset({"day", "interval", "bounded_12_day_detection_interval"})
REVIEWED_OVERLAP_STATUSES = frozenset({"reviewed", "not_required"})


class IntervalShadowJoinError(ValueError):
    """Raised when a label or feature violates the explicit join contract."""


@dataclass(frozen=True)
class IntervalShadowJoinPolicy:
    """Explicit policies for a bounded, non-promoting shadow join."""

    require_overlap_review: bool = True
    require_distinct_source_families: bool = True
    reject_ambiguous_matches: bool = True


def _text(value: Any, *, field: str, row_id: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IntervalShadowJoinError(f"{row_id}: missing {field}")
    return text


def _row_id(row: Mapping[str, Any], *, position: int) -> str:
    for field in ("source_event_id", "event_id", "external_id", "feature_id", "row_id", "sample_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return f"row:{position}"


def _timestamp(value: Any, *, field: str, row_id: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise IntervalShadowJoinError(f"{row_id}: missing {field}")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise IntervalShadowJoinError(f"{row_id}: invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntervalShadowJoinError(f"{row_id}: {field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _flag(value: Any, *, field: str, row_id: str) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise IntervalShadowJoinError(f"{row_id}: {field} must be boolean")


def _join_key(row: Mapping[str, Any], *, row_id: str) -> str:
    for field in ("feature_join_key", "spatial_group_id", "join_key"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    raise IntervalShadowJoinError(
        f"{row_id}: missing explicit feature_join_key/spatial_group_id/join_key",
    )


def _overlap_status(row: Mapping[str, Any], *, row_id: str, policy: IntervalShadowJoinPolicy) -> str:
    value = str(row.get("source_overlap_review_status") or "").strip().lower()
    if policy.require_overlap_review and value not in REVIEWED_OVERLAP_STATUSES:
        raise IntervalShadowJoinError(
            f"{row_id}: source_overlap_review_status must be reviewed or not_required",
        )
    return value or "not_required"


def _normalise_label(
    row: Mapping[str, Any],
    *,
    position: int,
    policy: IntervalShadowJoinPolicy,
) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise IntervalShadowJoinError(f"label:{position}: row must be an object")
    row_id = _row_id(row, position=position)
    start = _timestamp(
        row.get("interval_start", row.get("event_time_start")),
        field="interval_start",
        row_id=row_id,
    )
    end = _timestamp(
        row.get("interval_end", row.get("event_time_end")),
        field="interval_end",
        row_id=row_id,
    )
    if end <= start:
        raise IntervalShadowJoinError(f"{row_id}: interval_end must be after interval_start")
    for point_field in ("event_time", "timestamp"):
        if row.get(point_field) not in (None, ""):
            raise IntervalShadowJoinError(
                f"{row_id}: point-time field {point_field} is forbidden for interval labels",
            )
    precision = str(row.get("precision") or row.get("timestamp_precision") or "interval").strip().lower()
    if precision not in INTERVAL_LABEL_PRECISIONS:
        raise IntervalShadowJoinError(
            f"{row_id}: unsupported interval precision {precision!r}",
        )
    for field in (
        "training_eligible",
        "core_training_eligible",
        "production_eligible",
        "production_scoring_eligible",
    ):
        if _flag(row.get(field), field=field, row_id=row_id):
            raise IntervalShadowJoinError(f"{row_id}: {field} must remain false")
    return {
        "label_id": row_id,
        "label_source_key": _text(row.get("source_key"), field="source_key", row_id=row_id),
        "label_source_family": _text(
            row.get("source_family") or row.get("origin_source_family"),
            field="source_family",
            row_id=row_id,
        ),
        "region_key": _text(row.get("region_key"), field="region_key", row_id=row_id),
        "join_key": _join_key(row, row_id=row_id),
        "interval_start": start,
        "interval_end": end,
        "label_precision": "day" if precision == "day" else "interval",
        "source_overlap_review_status": _overlap_status(row, row_id=row_id, policy=policy),
    }


def _normalise_feature(row: Mapping[str, Any], *, position: int) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise IntervalShadowJoinError(f"feature:{position}: row must be an object")
    row_id = _row_id(row, position=position)
    valid_from = _timestamp(row.get("feature_valid_from"), field="feature_valid_from", row_id=row_id)
    valid_until = _timestamp(row.get("feature_valid_until"), field="feature_valid_until", row_id=row_id)
    if valid_until <= valid_from:
        raise IntervalShadowJoinError(f"{row_id}: feature_valid_until must be after feature_valid_from")
    cutoff = _timestamp(row.get("feature_cutoff_at"), field="feature_cutoff_at", row_id=row_id)
    for field in (
        "training_eligible",
        "core_training_eligible",
        "production_eligible",
        "production_scoring_eligible",
    ):
        if _flag(row.get(field), field=field, row_id=row_id):
            raise IntervalShadowJoinError(f"{row_id}: {field} must remain false")
    reserved = {
        "feature_id",
        "row_id",
        "sample_id",
        "region_key",
        "feature_join_key",
        "spatial_group_id",
        "join_key",
        "feature_valid_from",
        "feature_valid_until",
        "feature_cutoff_at",
        "source_key",
        "source_family",
        "feature_source_family",
        "production_eligible",
        "training_eligible",
        "core_training_eligible",
        "production_scoring_eligible",
    }
    payload = row.get("features")
    if not isinstance(payload, Mapping):
        payload = {str(key): value for key, value in row.items() if key not in reserved}
    return {
        "feature_id": row_id,
        "feature_source_key": _text(row.get("source_key"), field="source_key", row_id=row_id),
        "feature_source_family": _text(
            row.get("feature_source_family") or row.get("source_family"),
            field="source_family",
            row_id=row_id,
        ),
        "region_key": _text(row.get("region_key"), field="region_key", row_id=row_id),
        "join_key": _join_key(row, row_id=row_id),
        "feature_valid_from": valid_from,
        "feature_valid_until": valid_until,
        "feature_cutoff_at": cutoff,
        "features": dict(payload),
    }


def _sort_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    values = (
        row.get("region_key"),
        row.get("join_key"),
        row.get("label_id") or row.get("feature_id"),
        row.get("interval_start") or row.get("feature_valid_from"),
        row.get("interval_end") or row.get("feature_valid_until"),
    )
    return tuple(_iso(value) if isinstance(value, datetime) else str(value or "") for value in values)


def _intervals_overlap(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    """Return overlap under end-exclusive interval semantics."""
    return left_start < right_end and right_start < left_end


def build_interval_shadow_join(
    labels: Iterable[Mapping[str, Any]],
    features: Iterable[Mapping[str, Any]],
    *,
    policy: IntervalShadowJoinPolicy | None = None,
) -> dict[str, Any]:
    """Build a deterministic, non-promoting interval-to-feature shadow result.

    A feature is eligible only when its validity window fully contains the
    label interval, its cutoff is no later than the interval start, its source
    family is distinct from the label family, and the label has an approved
    overlap-review status.  Ambiguous matches are rejected rather than
    resolved by an arbitrary ranking.
    """
    join_policy = policy or IntervalShadowJoinPolicy()
    normalised_labels = sorted(
        (
            _normalise_label(row, position=position, policy=join_policy)
            for position, row in enumerate(labels)
        ),
        key=_sort_key,
    )
    normalised_features = sorted(
        (_normalise_feature(row, position=position) for position, row in enumerate(features)),
        key=_sort_key,
    )
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for feature in normalised_features:
        by_key.setdefault((feature["region_key"], feature["join_key"]), []).append(feature)

    output_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for label in normalised_labels:
        key = (label["region_key"], label["join_key"])
        candidates: list[dict[str, Any]] = []
        for feature in by_key.get(key, []):
            if not _intervals_overlap(
                label["interval_start"],
                label["interval_end"],
                feature["feature_valid_from"],
                feature["feature_valid_until"],
            ):
                continue
            if not (
                feature["feature_valid_from"] <= label["interval_start"]
                and feature["feature_valid_until"] >= label["interval_end"]
            ):
                issues.append({"label_id": label["label_id"], "feature_id": feature["feature_id"], "reason": "partial_feature_validity"})
                continue
            if feature["feature_cutoff_at"] > label["interval_start"]:
                issues.append({"label_id": label["label_id"], "feature_id": feature["feature_id"], "reason": "feature_cutoff_violation"})
                continue
            if join_policy.require_distinct_source_families and (
                feature["feature_source_family"] == label["label_source_family"]
            ):
                issues.append({"label_id": label["label_id"], "feature_id": feature["feature_id"], "reason": "source_family_not_distinct"})
                continue
            candidates.append(feature)

        if not candidates:
            issues.append({"label_id": label["label_id"], "reason": "no_eligible_feature"})
            continue
        if len(candidates) > 1:
            issue = {
                "label_id": label["label_id"],
                "feature_ids": [candidate["feature_id"] for candidate in candidates],
                "reason": "ambiguous_feature_match",
            }
            issues.append(issue)
            if join_policy.reject_ambiguous_matches:
                continue
        for feature in candidates if not join_policy.reject_ambiguous_matches else candidates[:1]:
            output_rows.append({
                "join_version": INTERVAL_SHADOW_JOIN_VERSION,
                "label_id": label["label_id"],
                "label_source_key": label["label_source_key"],
                "label_source_family": label["label_source_family"],
                "region_key": label["region_key"],
                "join_key": label["join_key"],
                "interval_start": _iso(label["interval_start"]),
                "interval_end": _iso(label["interval_end"]),
                "label_precision": label["label_precision"],
                "source_overlap_review_status": label["source_overlap_review_status"],
                "feature_id": feature["feature_id"],
                "feature_source_key": feature["feature_source_key"],
                "feature_source_family": feature["feature_source_family"],
                "feature_valid_from": _iso(feature["feature_valid_from"]),
                "feature_valid_until": _iso(feature["feature_valid_until"]),
                "feature_cutoff_at": _iso(feature["feature_cutoff_at"]),
                "features": feature["features"],
                "shadow_only": True,
                "core_training_eligible": False,
                "production_scoring_eligible": False,
            })

    output_rows.sort(key=_sort_key)
    issues.sort(key=lambda issue: json.dumps(issue, sort_keys=True, separators=(",", ":")))
    return {
        "version": INTERVAL_SHADOW_JOIN_VERSION,
        "policy": {
            "require_overlap_review": join_policy.require_overlap_review,
            "require_distinct_source_families": join_policy.require_distinct_source_families,
            "reject_ambiguous_matches": join_policy.reject_ambiguous_matches,
            "interval_semantics": "[start,end), feature validity must contain full label interval",
            "cutoff_rule": "feature_cutoff_at<=interval_start",
            "point_time_synthesis": False,
        },
        "rows": output_rows,
        "issues": issues,
        "summary": {
            "label_count": len(normalised_labels),
            "feature_count": len(normalised_features),
            "joined_count": len(output_rows),
            "issue_count": len(issues),
            "core_training_eligible": False,
            "production_scoring_eligible": False,
        },
    }
