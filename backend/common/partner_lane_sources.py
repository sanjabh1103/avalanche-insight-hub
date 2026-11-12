"""Fail-closed source contracts for the Partner preparation lanes.

These contracts deliberately do not fetch ERA5, DEM, IMD, or Partner station
data. They define the minimum evidence an adapter must provide before feature
generation can be enabled. Public availability is not treated as a rights,
schema, byte-integrity, or lane-authorization proof.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

SOURCE_CONTRACT_STATUS_UNRESOLVED = 'unresolved'
SOURCE_CONTRACT_STATUS_CONTENT_VERIFIED = 'content_verified'
SOURCE_CONTRACT_STATUS_BLOCKED = 'blocked'

_SOURCE_KINDS = {'forcing', 'terrain', 'station_anchor'}
_VALID_TRACKS = {'t2a', 'track1'}


def _is_sha256(value: str | None) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class PartnerLaneSourceContractV1:
    """One source contract used by a lane adapter."""

    source_id: str
    track: str
    source_kind: str
    provider: str
    source_url: str | None = None
    source_hash: str | None = None
    schema_hash: str | None = None
    rights_status: str = 'pending'
    permitted_track: str | None = None
    temporal_coverage: str | None = None
    spatial_coverage: str | None = None
    status: str = SOURCE_CONTRACT_STATUS_UNRESOLVED
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.provider.strip():
            raise ValueError('source_id and provider must be non-empty')
        if self.track not in _VALID_TRACKS:
            raise ValueError(f'unsupported lane track: {self.track!r}')
        if self.source_kind not in _SOURCE_KINDS:
            raise ValueError(f'unsupported source_kind: {self.source_kind!r}')
        if self.status not in {
            SOURCE_CONTRACT_STATUS_UNRESOLVED,
            SOURCE_CONTRACT_STATUS_CONTENT_VERIFIED,
            SOURCE_CONTRACT_STATUS_BLOCKED,
        }:
            raise ValueError(f'unsupported source contract status: {self.status!r}')
        if self.source_hash is not None and not _is_sha256(self.source_hash):
            raise ValueError('source_hash must be a 64-character hexadecimal SHA-256')
        if self.schema_hash is not None and not _is_sha256(self.schema_hash):
            raise ValueError('schema_hash must be a 64-character hexadecimal SHA-256')
        if self.permitted_track is not None and self.permitted_track != self.track:
            raise ValueError('source rights cannot authorize a different track')
        if self.track == 't2a' and self.source_kind == 'station_anchor':
            raise ValueError('T2A is station-free and cannot carry station_anchor input')

    @property
    def feature_generation_ready(self) -> bool:
        return (
            self.status == SOURCE_CONTRACT_STATUS_CONTENT_VERIFIED
            and self.rights_status == 'approved'
            and self.permitted_track == self.track
            and _is_sha256(self.source_hash)
            and _is_sha256(self.schema_hash)
            and bool(self.temporal_coverage and self.spatial_coverage)
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LaneSourceGateResult:
    track: str
    allowed: bool
    blocker_codes: tuple[str, ...] = ()
    blocker_messages: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_lane_source_contracts(track: str) -> list[PartnerLaneSourceContractV1]:
    """Return the bounded source plan for a lane; no source is pre-authorized."""
    if track == 't2a':
        return [
            PartnerLaneSourceContractV1(
                source_id='t2a_era5_forcing', track='t2a', source_kind='forcing',
                provider='ECMWF/Copernicus ERA5',
                notes='Requires source access, schema, temporal/spatial coverage, and rights review.',
            ),
            PartnerLaneSourceContractV1(
                source_id='t2a_himalayan_dem', track='t2a', source_kind='terrain',
                provider='NASA/USGS SRTM or ASTER',
                notes='Candidate terrain source; exact product and license remain to be bound.',
            ),
        ]
    if track == 'track1':
        return [
            PartnerLaneSourceContractV1(
                source_id='track1_Partner_station_anchor', track='track1', source_kind='station_anchor',
                provider='Partner',
                notes='Mandatory Partner-approved station/anchor source; no public substitute is implied.',
            ),
            PartnerLaneSourceContractV1(
                source_id='track1_forcing', track='track1', source_kind='forcing',
                provider='ECMWF/Copernicus ERA5',
                notes='Forcing source must be bound to the approved Track 1 reference lane.',
            ),
        ]
    raise ValueError(f'unsupported lane track: {track!r}')


def validate_lane_source_contracts(
    track: str,
    contracts: list[PartnerLaneSourceContractV1],
) -> LaneSourceGateResult:
    """Validate source isolation and readiness without fetching external data."""
    blockers: list[str] = []
    expected_kinds = {'forcing', 'terrain'} if track == 't2a' else {'forcing', 'station_anchor'}
    if track not in _VALID_TRACKS:
        return LaneSourceGateResult(track, False, ('E031_unknown_source_track',), ('unknown source track',))
    if not contracts:
        return LaneSourceGateResult(track, False, ('E032_missing_source_contracts',), ('no source contracts supplied',))
    seen_kinds: set[str] = set()
    for contract in contracts:
        if contract.track != track:
            blockers.append(f'{contract.source_id}: cross-lane source contract')
        if track == 't2a' and contract.source_kind == 'station_anchor':
            blockers.append(f'{contract.source_id}: station input is forbidden for T2A')
        seen_kinds.add(contract.source_kind)
        if not contract.feature_generation_ready:
            blockers.append(f'{contract.source_id}: content, schema, rights, or coverage evidence is incomplete')
    missing_kinds = sorted(expected_kinds - seen_kinds)
    if missing_kinds:
        blockers.append(f'missing required source kinds: {missing_kinds}')
    return LaneSourceGateResult(
        track=track,
        allowed=not blockers,
        blocker_codes=tuple('E033_source_contract_blocked' for _ in blockers),
        blocker_messages=tuple(blockers),
        source_ids=tuple(contract.source_id for contract in contracts),
    )


def content_schema_hash(schema: dict[str, Any]) -> str:
    """Compute a stable schema hash for an adapter's declared columns."""
    import json
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
