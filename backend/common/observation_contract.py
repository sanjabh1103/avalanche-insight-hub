"""Append-only observation contract for the verification spine.

The contract deliberately separates an observation from a derived baseline.
Every persisted observation carries enough provenance to be replayed, filtered,
or excluded from public-warning paths without reconstructing the original run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


QUALITY_UNVERIFIED = 'unverified'
QUALITY_PROVISIONAL = 'provisional'
QUALITY_VERIFIED = 'verified'
QUALITY_REJECTED = 'rejected'
QUALITY_MISSING = 'missing'

VALID_QUALITY_STATES = frozenset({
    QUALITY_UNVERIFIED,
    QUALITY_PROVISIONAL,
    QUALITY_VERIFIED,
    QUALITY_REJECTED,
    QUALITY_MISSING,
})


def _normalise_acquisition_time(value: datetime | str) -> str:
    """Return an ISO-8601 UTC timestamp, rejecting ambiguous input."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('acquisition_time must be ISO-8601') from exc
    else:
        raise ValueError('acquisition_time is required')

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class ObservationContract:
    """One immutable, append-only sensor observation.

    ``value`` may be null when a source explicitly reports missing data, but
    the record still retains its unit, acquisition time, quality, and lineage.
    Unknown freshness is represented as null and must fail closed at publish
    gates rather than being silently treated as fresh.
    """

    region_key: str
    cell_id: str
    sensor: str
    variable: str
    value: float | None
    unit: str
    uncertainty: float | None
    acquisition_time: datetime | str
    freshness_hours: float | None
    quality_state: str = QUALITY_UNVERIFIED
    lineage: dict[str, Any] = field(default_factory=dict)
    synthetic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ('region_key', 'cell_id', 'sensor', 'variable', 'unit'):
            if not str(getattr(self, name) or '').strip():
                raise ValueError(f'{name} is required')

        if self.value is not None and not math.isfinite(float(self.value)):
            raise ValueError('value must be finite when present')
        if self.uncertainty is not None:
            uncertainty = float(self.uncertainty)
            if not math.isfinite(uncertainty) or uncertainty < 0:
                raise ValueError('uncertainty must be finite and non-negative')
        if self.freshness_hours is not None:
            freshness = float(self.freshness_hours)
            if not math.isfinite(freshness) or freshness < 0:
                raise ValueError('freshness_hours must be finite and non-negative')
        if self.quality_state not in VALID_QUALITY_STATES:
            raise ValueError(f'Invalid quality_state: {self.quality_state}')
        if not isinstance(self.lineage, dict):
            raise ValueError('lineage must be a mapping')
        _normalise_acquisition_time(self.acquisition_time)

    @property
    def lineage_verified(self) -> bool:
        """Whether the source lineage explicitly passed verification."""
        return bool(self.lineage.get('verified', False))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the Supabase row shape without derived fields."""
        return {
            'region_key': self.region_key,
            'cell_id': self.cell_id,
            'sensor': self.sensor,
            'variable': self.variable,
            'value': float(self.value) if self.value is not None else None,
            'unit': self.unit,
            'uncertainty': float(self.uncertainty) if self.uncertainty is not None else None,
            'acquisition_time': _normalise_acquisition_time(self.acquisition_time),
            'freshness_hours': float(self.freshness_hours) if self.freshness_hours is not None else None,
            'quality_state': self.quality_state,
            'lineage': self.lineage,
            'synthetic': bool(self.synthetic),
            'metadata': self.metadata,
        }
