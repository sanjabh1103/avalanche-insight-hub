"""RAvaFcast cadence contract — six-hour issue slot semantics.

This module defines the cadence contract for six-hourly forecast issue slots.
It is a pure module with no side effects, no DB calls, and no network access.

The cadence is a *proposed technical-reference cadence*, NOT an official
Partner bulletin cadence. Partner bulletins are valid 17:00 IST to 17:00 IST
next day. Six-hourly output is a technical-reference candidate for
comparison only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date


@dataclass(frozen=True)
class CadenceContract:
    """Contract for forecast issue cadence and slot semantics."""
    cadence_hours: int = 6
    issue_slots: tuple[str, ...] = ("00", "06", "12", "18")
    timezone: str = "UTC"
    horizon_hours: int = 72

    def validate(self) -> None:
        """Validate the cadence contract. Raises ValueError on invalid config."""
        if self.cadence_hours <= 0:
            raise ValueError(f"cadence_hours must be > 0, got {self.cadence_hours}")
        if not self.issue_slots:
            raise ValueError("issue_slots must not be empty")
        if 24 % self.cadence_hours != 0:
            raise ValueError(
                f"cadence_hours ({self.cadence_hours}) must evenly divide 24"
            )
        expected_count = 24 // self.cadence_hours
        if len(self.issue_slots) != expected_count:
            raise ValueError(
                f"issue_slots count ({len(self.issue_slots)}) must equal "
                f"24 / cadence_hours ({expected_count})"
            )
        for slot in self.issue_slots:
            try:
                hour = int(slot)
            except (ValueError, TypeError):
                raise ValueError(f"issue_slot '{slot}' is not a valid integer")
            if not (0 <= hour <= 23):
                raise ValueError(f"issue_slot hour {hour} out of range [0, 23]")
        if self.horizon_hours <= 0:
            raise ValueError(f"horizon_hours must be > 0, got {self.horizon_hours}")
        if self.timezone != "UTC":
            raise ValueError(
                f"Only UTC timezone is supported, got '{self.timezone}'"
            )


# The utility default remains the six-hour technical-reference cadence for
# backward-compatible slot helpers. Runtime publication defaults are explicit
# and daily via DEFAULT_RUNTIME_CADENCE below.
DEFAULT_CADENCE = CadenceContract()
DEFAULT_RUNTIME_CADENCE = CadenceContract(
    cadence_hours=24,
    issue_slots=("06",),
)


def compute_issue_slot(
    issue_time: datetime,
    cadence: CadenceContract = DEFAULT_CADENCE,
) -> str:
    """Compute the issue slot (HH string) for a given issue time.

    Args:
        issue_time: The datetime when the forecast is issued.
        cadence: The cadence contract defining slots.

    Returns:
        Two-digit hour string, e.g. "00", "06", "12", "18".
    """
    cadence.validate()
    if issue_time.tzinfo is None:
        raise ValueError(
            "issue_time must be timezone-aware (use UTC)"
        )
    issue_time = issue_time.astimezone(timezone.utc)
    hour = issue_time.hour
    slot_index = hour // cadence.cadence_hours
    slot_index = min(slot_index, len(cadence.issue_slots) - 1)
    return cadence.issue_slots[slot_index]


def compute_valid_window(
    issue_slot: str,
    cadence: CadenceContract = DEFAULT_CADENCE,
    base_date: date | None = None,
) -> tuple[datetime, datetime]:
    """Compute the (valid_from, valid_to) window for a given issue slot.

    Args:
        issue_slot: Two-digit hour string, e.g. "06".
        cadence: The cadence contract.
        base_date: The forecast date. Defaults to today (UTC).

    Returns:
        Tuple of (valid_from, valid_to) as timezone-aware UTC datetimes.
    """
    cadence.validate()
    if issue_slot not in cadence.issue_slots:
        raise ValueError(
            f"issue_slot '{issue_slot}' is not in cadence slots {cadence.issue_slots}"
        )
    slot_hour = int(issue_slot)
    if base_date is None:
        base_date = datetime.now(timezone.utc).date()
    valid_from = datetime(
        base_date.year, base_date.month, base_date.day,
        slot_hour, 0, 0, tzinfo=timezone.utc,
    )
    valid_to = valid_from + timedelta(hours=cadence.horizon_hours)
    if valid_to <= valid_from:
        raise ValueError(
            f"valid_to ({valid_to}) must be > valid_from ({valid_from})"
        )
    return valid_from, valid_to


def compute_forecast_date(issue_time: datetime) -> date:
    """Compute the forecast date from issue time.

    The forecast date is the calendar date of the issue time in UTC.
    For issue times at or after midnight UTC, the forecast date is
    the same day. For issue times before midnight (which shouldn't
    happen in normal operation), it's still the same UTC date.

    Args:
        issue_time: The datetime when the forecast is issued.

    Returns:
        The UTC calendar date of the issue time.
    """
    if issue_time.tzinfo is None:
        raise ValueError("issue_time must be timezone-aware (use UTC)")
    return issue_time.astimezone(timezone.utc).date()


@dataclass(frozen=True)
class ForecastCadenceContext:
    """Typed cadence context threaded through the publication pipeline.

    Replaces implicit _current_* locals from main() to avoid NameError
    in module-level functions like upsert_forecast_grid().
    """
    issue_time: datetime
    forecast_date: date
    issue_slot: str
    cadence_hours: int
    valid_from: datetime
    valid_to: datetime
    source_as_of: datetime
    source_as_of_inferred: bool = False

    def validate(self) -> None:
        timestamps = {
            'issue_time': self.issue_time,
            'valid_from': self.valid_from,
            'valid_to': self.valid_to,
            'source_as_of': self.source_as_of,
        }
        for name, value in timestamps.items():
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be timezone-aware UTC")
        if not self.issue_slot:
            raise ValueError("issue_slot must not be empty")
        if self.cadence_hours not in (6, 24):
            raise ValueError(f"cadence_hours must be 6 or 24, got {self.cadence_hours}")
        horizon_hours = int((self.valid_to - self.valid_from).total_seconds() / 3600)
        cadence = (
            CadenceContract(
                cadence_hours=6,
                issue_slots=("00", "06", "12", "18"),
                horizon_hours=horizon_hours,
            )
            if self.cadence_hours == 6
            else CadenceContract(
                cadence_hours=24,
                issue_slots=("06",),
                horizon_hours=horizon_hours,
            )
        )
        expected_slots = ("00", "06", "12", "18") if self.cadence_hours == 6 else ("06",)
        if self.issue_slot not in expected_slots:
            raise ValueError(f"issue_slot {self.issue_slot!r} is invalid for cadence {self.cadence_hours}")
        if compute_issue_slot(self.issue_time, cadence) != self.issue_slot:
            raise ValueError("issue_slot does not match issue_time and cadence")
        if self.forecast_date != self.issue_time.astimezone(timezone.utc).date():
            raise ValueError("forecast_date must match issue_time UTC date")
        if self.valid_from.astimezone(timezone.utc).date() != self.forecast_date:
            raise ValueError("valid_from date must match forecast_date")
        if self.valid_from.astimezone(timezone.utc).hour != int(self.issue_slot):
            raise ValueError("valid_from hour must match issue_slot")
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be > valid_from")
        if self.source_as_of > self.issue_time:
            raise ValueError("source_as_of cannot be later than issue_time")


def build_cadence_context(
    issue_time: datetime | None = None,
    cadence_hours: int | None = None,
    source_as_of: datetime | None = None,
) -> ForecastCadenceContext:
    """Build a ForecastCadenceContext from env vars or explicit args.

    Reads RAVAFCAST_CADENCE_HOURS env var (default 24).
    Only 6 and 24 are valid values; others raise ValueError.

    Args:
        issue_time: Override issue time (defaults to now UTC).
        cadence_hours: Override cadence hours (defaults to env var).

    Returns:
        ForecastCadenceContext with computed slot, window, and date.
    """
    import os

    if cadence_hours is None:
        cadence_hours = int(os.getenv('RAVAFCAST_CADENCE_HOURS', '24'))
    if cadence_hours not in (6, 24):
        raise ValueError(
            f"RAVAFCAST_CADENCE_HOURS must be 6 or 24, got {cadence_hours}"
        )

    if cadence_hours == 6:
        cadence = CadenceContract(
            cadence_hours=6,
            issue_slots=("00", "06", "12", "18"),
            horizon_hours=int(os.getenv('FORECAST_HORIZON_HOURS', '72')),
        )
    else:
            cadence = CadenceContract(
                cadence_hours=24,
                issue_slots=("06",),
                horizon_hours=int(os.getenv('FORECAST_HORIZON_HOURS', '72')),
        )

    if issue_time is None:
        issue_time = datetime.now(timezone.utc)
    if issue_time.tzinfo is None:
        raise ValueError(
            "issue_time must be timezone-aware (use UTC)"
        )
    issue_time = issue_time.astimezone(timezone.utc)

    slot = compute_issue_slot(issue_time, cadence)
    fdate = compute_forecast_date(issue_time)
    vf, vt = compute_valid_window(slot, cadence, base_date=fdate)

    inferred_source_as_of = source_as_of is None
    if source_as_of is None:
        raw_source_as_of = os.getenv('RAVAFCAST_SOURCE_AS_OF', '').strip()
        if raw_source_as_of:
            try:
                source_as_of = datetime.fromisoformat(raw_source_as_of.replace('Z', '+00:00'))
            except ValueError as exc:
                raise ValueError('RAVAFCAST_SOURCE_AS_OF must be ISO 8601') from exc
            inferred_source_as_of = False
        else:
            source_as_of = issue_time
    if source_as_of.tzinfo is None:
        raise ValueError('source_as_of must be timezone-aware')
    source_as_of = source_as_of.astimezone(timezone.utc)

    context = ForecastCadenceContext(
        issue_time=issue_time,
        forecast_date=fdate,
        issue_slot=slot,
        cadence_hours=cadence_hours,
        valid_from=vf,
        valid_to=vt,
        source_as_of=source_as_of,
        source_as_of_inferred=inferred_source_as_of,
    )
    context.validate()
    return context
