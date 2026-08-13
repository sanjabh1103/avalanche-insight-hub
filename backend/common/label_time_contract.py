"""Fail-closed time-precision contracts for open-source label rows.

The core model may eventually use labels whose occurrence time is known only
to a day or to a bounded interval.  This module validates that distinction
without inventing a timestamp.  It deliberately does not approve a source,
decide whether a row is scientifically independent, or alter the training
frame; those decisions remain in the reviewed-snapshot and model gates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


LABEL_TIME_CONTRACT_EXACT_V1 = "exact_time_core_v1"
LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1 = "interval_censored_core_v1"
SUPPORTED_LABEL_TIME_CONTRACTS = frozenset(
    {
        LABEL_TIME_CONTRACT_EXACT_V1,
        LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
    }
)
CANONICAL_PRECISIONS = frozenset({"day", "interval", "exact"})
EXACT_OCCURRENCE_TIME_SEMANTICS = frozenset({
    "independent_observed_occurrence_time",
    "source_reported_occurrence_time",
})
EXACT_OCCURRENCE_TIME_REVIEW_STATUS = "approved_occurrence_time"

_PRECISION_ALIASES = {
    "day": "day",
    "interval": "interval",
    "range": "interval",
    "bounded_12_day_detection_interval": "interval",
    "exact": "exact",
    "timestamp": "exact",
    "instant": "exact",
    "exact_timestamp": "exact",
}
_INTERVAL_START_FIELDS = ("interval_start", "event_time_start", "timestamp_start")
_INTERVAL_END_FIELDS = ("interval_end", "event_time_end", "timestamp_end")
_EXACT_FIELDS = ("event_time", "timestamp")


def _first_present(row: Mapping[str, Any], fields: Iterable[str]) -> tuple[str | None, Any]:
    for field in fields:
        if field in row and row[field] not in (None, ""):
            return field, row[field]
    return None, None


def normalise_precision(value: Any) -> str | None:
    """Map supported legacy field values to the canonical precision names."""
    text = str(value or "").strip().lower()
    return _PRECISION_ALIASES.get(text)


def normalise_contract(value: Any) -> str | None:
    """Return a contract version from either a string or a versioned object."""
    if isinstance(value, Mapping):
        value = value.get("version") or value.get("name")
    text = str(value or "").strip()
    return text if text in SUPPORTED_LABEL_TIME_CONTRACTS else None


def _provenance_value(
    row: Mapping[str, Any],
    field: str,
    *,
    source_manifest: Mapping[str, Any] | None = None,
) -> Any:
    """Read a source-time review field from a row or its source manifest."""
    containers: list[Mapping[str, Any]] = [row]
    for container_key in ("metadata", "features"):
        container = row.get(container_key)
        if isinstance(container, Mapping):
            containers.append(container)
    if isinstance(source_manifest, Mapping):
        containers.append(source_manifest)
    for container in containers:
        value = container.get(field)
        if value is not None and str(value).strip():
            return value
    return None


def has_approved_occurrence_time_review(
    row: Mapping[str, Any],
    *,
    source_manifest: Mapping[str, Any] | None = None,
) -> bool:
    """Require explicit semantics, approval, and a review ID for exact time."""
    semantics = str(
        _provenance_value(row, "event_time_semantics", source_manifest=source_manifest) or ""
    ).strip().lower()
    review_status = str(
        _provenance_value(row, "source_time_review_status", source_manifest=source_manifest) or ""
    ).strip().lower()
    review_id = str(
        _provenance_value(row, "source_time_review_id", source_manifest=source_manifest) or ""
    ).strip()
    return (
        semantics in EXACT_OCCURRENCE_TIME_SEMANTICS
        and review_status == EXACT_OCCURRENCE_TIME_REVIEW_STATUS
        and bool(review_id)
    )


def parse_utc_timestamp(value: Any) -> datetime | None:
    """Parse only timezone-aware timestamps; never localise a naive value."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def inspect_label_time_row(
    row: Mapping[str, Any],
    *,
    row_index: int = 0,
    require_feature_cutoff: bool = True,
) -> dict[str, Any]:
    """Inspect one row and return deterministic errors plus its time window.

    ``day`` and ``interval`` rows must not contain ``event_time``/``timestamp``:
    an exact-looking value on a censored row is treated as an unsafe fabricated
    timestamp.  For a day row the interval is exactly 24 hours and end is
    exclusive; interval rows may have any positive duration.
    """
    errors: list[dict[str, Any]] = []

    def add(code: str, message: str, field: str | None = None) -> None:
        issue: dict[str, Any] = {
            "row_index": row_index,
            "code": code,
            "message": message,
        }
        if field is not None:
            issue["field"] = field
        errors.append(issue)

    precision_field, precision_value = _first_present(row, ("precision", "timestamp_precision"))
    precision = normalise_precision(precision_value)
    if precision is None:
        add(
            "missing_or_unsupported_precision",
            "precision must be one of day, interval, or exact",
            precision_field or "precision",
        )

    start_field, start_value = _first_present(row, _INTERVAL_START_FIELDS)
    end_field, end_value = _first_present(row, _INTERVAL_END_FIELDS)
    exact_field, exact_value = _first_present(row, _EXACT_FIELDS)
    start = parse_utc_timestamp(start_value)
    end = parse_utc_timestamp(end_value)
    exact = parse_utc_timestamp(exact_value)

    if start_value is not None and start is None:
        add("invalid_or_naive_interval_start", "interval start must be a valid timezone-aware timestamp", start_field)
    if end_value is not None and end is None:
        add("invalid_or_naive_interval_end", "interval end must be a valid timezone-aware timestamp", end_field)
    if exact_value is not None and exact is None:
        add("invalid_or_naive_exact_time", "exact event time must be a valid timezone-aware timestamp", exact_field)

    window_start: datetime | None = None
    window_end: datetime | None = None
    if precision in {"day", "interval"}:
        if start_value is None or end_value is None:
            add(
                "missing_interval_bounds",
                f"{precision} precision requires explicit interval_start and interval_end",
                "interval_start/interval_end",
            )
        if exact_value is not None:
            add(
                "censored_row_contains_exact_time",
                "day/interval rows must not contain event_time or timestamp",
                exact_field,
            )
        window_start, window_end = start, end
        if start is not None and end is not None:
            duration = end - start
            if duration <= timedelta(0):
                add("non_positive_interval", "interval_end must be after interval_start", end_field)
            elif precision == "day" and duration != timedelta(days=1):
                add("day_interval_not_24_hours", "day precision requires a 24-hour, end-exclusive interval", end_field)
    elif precision == "exact":
        if exact_value is None:
            add("missing_exact_time", "exact precision requires event_time or timestamp", "event_time")
        window_start = exact
        if start_value is not None or end_value is not None:
            if start_value is None or end_value is None:
                add("partial_interval_bounds", "interval_start and interval_end must be supplied together")
            elif start is not None and end is not None:
                if end <= start:
                    add("non_positive_interval", "interval_end must be after interval_start", end_field)
                if exact is not None and not start <= exact < end:
                    add("exact_time_outside_interval", "exact event time must fall inside its explicit interval")
                window_start, window_end = start, end
        if window_end is None and exact is not None:
            window_end = exact

    cutoff_field, cutoff_value = _first_present(row, ("feature_cutoff_at",))
    cutoff = parse_utc_timestamp(cutoff_value)
    if require_feature_cutoff and cutoff_value is None:
        add("missing_feature_cutoff", "feature_cutoff_at is required for leakage-safe labels", "feature_cutoff_at")
    elif cutoff_value is not None and cutoff is None:
        add("invalid_or_naive_feature_cutoff", "feature_cutoff_at must be a valid timezone-aware timestamp", cutoff_field)
    if cutoff is not None and window_start is not None and cutoff > window_start:
        add(
            "feature_cutoff_after_occurrence_start",
            "feature_cutoff_at must be at or before the occurrence interval start",
            cutoff_field,
        )

    return {
        "row_index": row_index,
        "valid": not errors,
        "precision": precision,
        "interval_start": _iso(window_start),
        "interval_end": _iso(window_end),
        "feature_cutoff_at": _iso(cutoff),
        "errors": errors,
    }


def validate_label_time_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    contract: str,
    require_feature_cutoff: bool = True,
    include_row_inspections: bool = False,
) -> dict[str, Any]:
    """Validate a snapshot's row time contract without changing any rows."""
    normalised_contract = normalise_contract(contract)
    records = list(rows)
    if normalised_contract is None:
        return {
            "contract": contract,
            "passed": False,
            "row_count": len(records),
            "valid_row_count": 0,
            "invalid_row_count": len(records),
            "precision_counts": {},
            "error_counts": {"unsupported_label_time_contract": len(records) or 1},
            "errors": [{"code": "unsupported_label_time_contract", "message": "unsupported label time contract"}],
        }

    inspections = [
        inspect_label_time_row(row, row_index=index, require_feature_cutoff=require_feature_cutoff)
        for index, row in enumerate(records)
    ]
    precision_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    for inspection in inspections:
        precision = inspection.get("precision")
        if precision is not None:
            precision_counts[precision] = precision_counts.get(precision, 0) + 1
        for issue in inspection["errors"]:
            code = str(issue["code"])
            error_counts[code] = error_counts.get(code, 0) + 1
            if len(errors) < 20:
                errors.append(issue)

    if normalised_contract == LABEL_TIME_CONTRACT_EXACT_V1:
        interval_rows = sum(1 for inspection in inspections if inspection.get("precision") in {"day", "interval"})
        if interval_rows:
            error_counts["interval_precision_not_allowed_by_exact_contract"] = interval_rows
            errors.append({
                "code": "interval_precision_not_allowed_by_exact_contract",
                "message": "day/interval rows require interval_censored_core_v1",
            })
    report = {
        "contract": normalised_contract,
        "passed": not error_counts,
        "row_count": len(records),
        "valid_row_count": sum(1 for inspection in inspections if inspection["valid"]),
        "invalid_row_count": sum(1 for inspection in inspections if not inspection["valid"]),
        "precision_counts": dict(sorted(precision_counts.items())),
        "error_counts": dict(sorted(error_counts.items())),
        "errors": errors,
    }
    if include_row_inspections:
        report["row_inspections"] = inspections
    return report
