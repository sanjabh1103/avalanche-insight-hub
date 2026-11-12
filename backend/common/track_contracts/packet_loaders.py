"""Executable Partner packet loaders with strict validation.

These loaders replace the prose templates in Partner_PLUGIN_PACKET_TEMPLATES.md.
Each packet binds approval ID, scope, signer/authority, signature, UTC time,
source hash, rights, reference unit, and permitted track/use.

The loaders reuse existing SourceSnapshot, PartnerSnowpackRecord, LabelContract,
StationContract, SnowpackContract, and PartnerCellInputContract where applicable.
They do NOT create a second competing provenance model.

All packets fail closed on:
- Incomplete fields
- Unsigned authority
- Stale or wrong-track data
- Wrong rights
- Malformed geometry
- Wrong time
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PacketValidationError(ValueError):
    """Raised when a Partner packet fails validation."""


_HEX_RE = re.compile(r'^[0-9a-f]{64}$')
_ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')


def _validate_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise PacketValidationError(f"{field_name} must be timezone-aware UTC")


def _validate_hex_hash(value: str, field_name: str) -> None:
    if not _HEX_RE.fullmatch(value.lower()):
        raise PacketValidationError(
            f"{field_name} must be a valid 64-char hexadecimal SHA-256"
        )


def _reject_unknown_fields(data: dict[str, Any], known_fields: set[str], schema_name: str) -> None:
    """Reject unknown fields in a dict being loaded into a packet.

    Per Codex audit P3: unknown keys must not pass silently.
    """
    unknown = set(data.keys()) - known_fields
    if unknown:
        raise PacketValidationError(
            f"{schema_name}: unknown fields rejected: {sorted(unknown)}"
        )


def _require_json_object(data: Any, schema_name: str) -> None:
    """Normalize non-object input into the stable packet blocker type."""
    if not isinstance(data, dict):
        raise PacketValidationError(
            f'E030_malformed_packet:{schema_name}: payload must be a JSON object'
        )


def _load_json_object(path: Path, schema_name: str) -> dict[str, Any]:
    """Load a packet file with one deterministic malformed-input boundary."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PacketValidationError(
            f'E030_malformed_packet:{schema_name}: cannot load JSON: {exc}'
        ) from exc
    _require_json_object(data, schema_name)
    return data


@dataclass(frozen=True)
class ApprovalPacketV1:
    """Signed M0/M1 authorization from Partner.

    This is the top-level approval that activates gates. Without a valid
    approval packet, no training or evaluation can proceed.
    """

    approval_id: str
    scope: str  # "m0_charter_lock", "m1_source_qualification", or "m0_m1_combined"
    signer: str  # Partner scientist name
    signer_role: str  # e.g., "Lead Scientist", "Director"
    signature_hash: str  # hash of the signed payload
    approved_at: datetime  # UTC
    approved_tracks: tuple[str, ...]  # ("track1", "t2a")
    notes: str = ""
    authority_id: str = ""  # stable registry identifier, required at runtime

    def validate(self) -> None:
        if not self.approval_id.strip():
            raise PacketValidationError("approval_id is required")
        if self.scope not in ("m0_charter_lock", "m1_source_qualification", "m0_m1_combined"):
            raise PacketValidationError(
                f"scope must be m0_charter_lock/m1_source_qualification/m0_m1_combined; "
                f"got {self.scope}"
            )
        if not self.signer.strip():
            raise PacketValidationError("signer is required (no unsigned approvals)")
        if not self.signer_role.strip():
            raise PacketValidationError("signer_role is required")
        _validate_hex_hash(self.signature_hash, "signature_hash")
        _validate_utc(self.approved_at, "approved_at")
        if not self.approved_tracks:
            raise PacketValidationError("at least one approved track is required")
        for track in self.approved_tracks:
            if track not in ("track1", "t2a", "t2b"):
                raise PacketValidationError(
                    f"approved track must be track1/t2a/t2b; got {track}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "approval_packet_v1",
            "approval_id": self.approval_id,
            "scope": self.scope,
            "signer": self.signer,
            "signer_role": self.signer_role,
            "signature_hash": self.signature_hash,
            "approved_at": self.approved_at.isoformat(),
            "approved_tracks": list(self.approved_tracks),
            "notes": self.notes,
            "authority_id": self.authority_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalPacketV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'ApprovalPacketV1')
        if data.get('schema') != 'approval_packet_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'approval_packet_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'approval_id', 'scope', 'signer', 'signer_role',
            'signature_hash', 'approved_at', 'approved_tracks', 'notes', 'authority_id'
        }, 'ApprovalPacketV1')
        required = ['approval_id', 'scope', 'signer', 'signer_role',
                    'signature_hash', 'approved_at', 'approved_tracks']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        packet = cls(
            approval_id=data['approval_id'],
            scope=data['scope'],
            signer=data['signer'],
            signer_role=data['signer_role'],
            signature_hash=data['signature_hash'],
            approved_at=datetime.fromisoformat(data['approved_at']),
            approved_tracks=tuple(data['approved_tracks']),
            notes=data.get('notes', ''),
            authority_id=data.get('authority_id', ''),
        )
        packet.validate()
        return packet


@dataclass(frozen=True)
class ReferenceUnitV1:
    """Reference unit geometry and identity.

    Binds the geographic unit to which labels and predictions are assigned.
    """

    reference_unit_name: str
    latitude: float
    longitude: float
    elevation_m: float
    elevation_band: str  # e.g., "3000-4000m"
    aspect_applicability: str  # e.g., "all", "north", "ne"
    geometry_hash: str  # hash of the GeoJSON geometry
    coordinate_system: str  # e.g., "EPSG:4326"
    approved_by: str
    approved_at: datetime

    def validate(self) -> None:
        if not self.reference_unit_name.strip():
            raise PacketValidationError("reference_unit_name is required")
        if not (-90.0 <= self.latitude <= 90.0):
            raise PacketValidationError(f"latitude out of range: {self.latitude}")
        if not (-180.0 <= self.longitude <= 180.0):
            raise PacketValidationError(f"longitude out of range: {self.longitude}")
        if self.elevation_m <= 0:
            raise PacketValidationError(f"elevation_m must be positive: {self.elevation_m}")
        if not self.elevation_band.strip():
            raise PacketValidationError("elevation_band is required")
        if not self.aspect_applicability.strip():
            raise PacketValidationError("aspect_applicability is required")
        _validate_hex_hash(self.geometry_hash, "geometry_hash")
        if not self.coordinate_system.strip():
            raise PacketValidationError("coordinate_system is required")
        if not self.approved_by.strip():
            raise PacketValidationError("approved_by is required")
        _validate_utc(self.approved_at, "approved_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "reference_unit_v1",
            "reference_unit_name": self.reference_unit_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_m": self.elevation_m,
            "elevation_band": self.elevation_band,
            "aspect_applicability": self.aspect_applicability,
            "geometry_hash": self.geometry_hash,
            "coordinate_system": self.coordinate_system,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReferenceUnitV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'ReferenceUnitV1')
        if data.get('schema') != 'reference_unit_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'reference_unit_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'reference_unit_name', 'latitude', 'longitude', 'elevation_m',
            'elevation_band', 'aspect_applicability', 'geometry_hash',
            'coordinate_system', 'approved_by', 'approved_at'
        }, 'ReferenceUnitV1')
        required = ['reference_unit_name', 'latitude', 'longitude', 'elevation_m',
                    'elevation_band', 'aspect_applicability', 'geometry_hash',
                    'coordinate_system', 'approved_by', 'approved_at']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        packet = cls(
            reference_unit_name=data['reference_unit_name'],
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            elevation_m=float(data['elevation_m']),
            elevation_band=data['elevation_band'],
            aspect_applicability=data['aspect_applicability'],
            geometry_hash=data['geometry_hash'],
            coordinate_system=data['coordinate_system'],
            approved_by=data['approved_by'],
            approved_at=datetime.fromisoformat(data['approved_at']),
        )
        packet.validate()
        return packet


@dataclass(frozen=True)
class IssueValidityRuleV1:
    """Issue and validity time rules for labels and predictions."""

    issue_cadence_hours: int  # e.g., 6
    issue_slots_utc: tuple[int, ...]  # e.g., (0, 6, 12, 18)
    validity_window_hours: int  # e.g., 24
    timezone: str  # must be "UTC"
    horizon_hours: int  # e.g., 72
    approved_by: str
    approved_at: datetime

    def validate(self) -> None:
        if self.issue_cadence_hours <= 0 or 24 % self.issue_cadence_hours != 0:
            raise PacketValidationError(
                f"issue_cadence_hours must divide 24 evenly; got {self.issue_cadence_hours}"
            )
        if not self.issue_slots_utc:
            raise PacketValidationError("issue_slots_utc is required")
        for slot in self.issue_slots_utc:
            if not 0 <= slot <= 23:
                raise PacketValidationError(f"issue slot out of range: {slot}")
        if self.validity_window_hours <= 0:
            raise PacketValidationError(
                f"validity_window_hours must be positive; got {self.validity_window_hours}"
            )
        if self.timezone != "UTC":
            raise PacketValidationError(f"timezone must be UTC; got {self.timezone}")
        if self.horizon_hours <= 0:
            raise PacketValidationError(
                f"horizon_hours must be positive; got {self.horizon_hours}"
            )
        if not self.approved_by.strip():
            raise PacketValidationError("approved_by is required")
        _validate_utc(self.approved_at, "approved_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "issue_validity_rule_v1",
            "issue_cadence_hours": self.issue_cadence_hours,
            "issue_slots_utc": list(self.issue_slots_utc),
            "validity_window_hours": self.validity_window_hours,
            "timezone": self.timezone,
            "horizon_hours": self.horizon_hours,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IssueValidityRuleV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'IssueValidityRuleV1')
        if data.get('schema') != 'issue_validity_rule_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'issue_validity_rule_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'issue_cadence_hours', 'issue_slots_utc',
            'validity_window_hours', 'timezone', 'horizon_hours',
            'approved_by', 'approved_at'
        }, 'IssueValidityRuleV1')
        required = ['issue_cadence_hours', 'issue_slots_utc', 'validity_window_hours',
                    'timezone', 'horizon_hours', 'approved_by', 'approved_at']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        packet = cls(
            issue_cadence_hours=int(data['issue_cadence_hours']),
            issue_slots_utc=tuple(data['issue_slots_utc']),
            validity_window_hours=int(data['validity_window_hours']),
            timezone=data['timezone'],
            horizon_hours=int(data['horizon_hours']),
            approved_by=data['approved_by'],
            approved_at=datetime.fromisoformat(data['approved_at']),
        )
        packet.validate()
        return packet


@dataclass(frozen=True)
class RightsManifestV1:
    """Rights and permitted-use declaration for a data source."""

    data_source: str  # e.g., "Partner bulletin archive"
    rights_holder: str
    permitted_uses: tuple[str, ...]  # ("ml_training_track1", "ml_training_t2a", ...)
    prohibited_uses: tuple[str, ...]
    license_review_id: str
    license_review_status: str  # "approved", "pending", "rejected"
    approved_by: str
    approved_at: datetime

    def validate(self) -> None:
        if not self.data_source.strip():
            raise PacketValidationError("data_source is required")
        if not self.rights_holder.strip():
            raise PacketValidationError("rights_holder is required")
        if not self.permitted_uses:
            raise PacketValidationError("at least one permitted_use is required")
        valid_uses = {
            "ml_training_track1", "ml_training_t2a", "ml_training_t2b",
            "ml_promotion_track1", "ml_promotion_t2a", "ml_promotion_t2b",
            "ml_serving_track1", "ml_serving_t2a", "ml_serving_t2b",
            "scientific_publication", "internal_review_only", "public_disclosure",
        }
        for use in self.permitted_uses:
            if use not in valid_uses:
                raise PacketValidationError(
                    f"permitted_use '{use}' not in valid set: {sorted(valid_uses)}"
                )
        if self.license_review_status not in ("approved", "pending", "rejected"):
            raise PacketValidationError(
                f"license_review_status must be approved/pending/rejected; "
                f"got {self.license_review_status}"
            )
        if self.license_review_status != "approved":
            raise PacketValidationError(
                f"license_review_status must be 'approved' for training; "
                f"got {self.license_review_status}"
            )
        if not self.license_review_id.strip():
            raise PacketValidationError("license_review_id is required")
        if not self.approved_by.strip():
            raise PacketValidationError("approved_by is required")
        _validate_utc(self.approved_at, "approved_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rights_manifest_v1",
            "data_source": self.data_source,
            "rights_holder": self.rights_holder,
            "permitted_uses": list(self.permitted_uses),
            "prohibited_uses": list(self.prohibited_uses),
            "license_review_id": self.license_review_id,
            "license_review_status": self.license_review_status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RightsManifestV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'RightsManifestV1')
        if data.get('schema') != 'rights_manifest_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'rights_manifest_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'data_source', 'rights_holder', 'permitted_uses',
            'prohibited_uses', 'license_review_id', 'license_review_status',
            'approved_by', 'approved_at'
        }, 'RightsManifestV1')
        required = ['data_source', 'rights_holder', 'permitted_uses',
                    'license_review_id', 'license_review_status', 'approved_by', 'approved_at']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        packet = cls(
            data_source=data['data_source'],
            rights_holder=data['rights_holder'],
            permitted_uses=tuple(data['permitted_uses']),
            prohibited_uses=tuple(data.get('prohibited_uses', [])),
            license_review_id=data['license_review_id'],
            license_review_status=data['license_review_status'],
            approved_by=data['approved_by'],
            approved_at=datetime.fromisoformat(data['approved_at']),
        )
        packet.validate()
        return packet


@dataclass(frozen=True)
class ForcingSourceManifestV1:
    """T2A forcing source qualification manifest."""

    provider: str  # e.g., "Open-Meteo"
    model_id: str  # e.g., "gfs_seamless"
    run_id_format: str  # e.g., "YYYY-MM-DDTHH:MM UTC"
    native_resolution_m: float
    assimilation_disclosure: str
    source_hash: str  # SHA-256 of the source snapshot
    license_review_id: str
    license_review_status: str
    permitted_track: str  # "t2a" or "track1"
    approved_by: str
    approved_at: datetime

    def validate(self) -> None:
        if not self.provider.strip():
            raise PacketValidationError("provider is required")
        if not self.model_id.strip():
            raise PacketValidationError("model_id is required")
        if not self.run_id_format.strip():
            raise PacketValidationError("run_id_format is required")
        if self.native_resolution_m <= 0:
            raise PacketValidationError(
                f"native_resolution_m must be positive; got {self.native_resolution_m}"
            )
        if not self.assimilation_disclosure.strip():
            raise PacketValidationError("assimilation_disclosure is required")
        _validate_hex_hash(self.source_hash, "source_hash")
        if self.license_review_status not in ("approved", "pending", "rejected"):
            raise PacketValidationError(
                f"license_review_status must be approved/pending/rejected; "
                f"got {self.license_review_status}"
            )
        if self.license_review_status != "approved":
            raise PacketValidationError(
                f"license_review_status must be 'approved'; got {self.license_review_status}"
            )
        if self.permitted_track not in ("t2a", "track1", "t2b"):
            raise PacketValidationError(
                f"permitted_track must be t2a/track1/t2b; got {self.permitted_track}"
            )
        if not self.approved_by.strip():
            raise PacketValidationError("approved_by is required")
        _validate_utc(self.approved_at, "approved_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "forcing_source_manifest_v1",
            "provider": self.provider,
            "model_id": self.model_id,
            "run_id_format": self.run_id_format,
            "native_resolution_m": self.native_resolution_m,
            "assimilation_disclosure": self.assimilation_disclosure,
            "source_hash": self.source_hash,
            "license_review_id": self.license_review_id,
            "license_review_status": self.license_review_status,
            "permitted_track": self.permitted_track,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ForcingSourceManifestV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'ForcingSourceManifestV1')
        if data.get('schema') != 'forcing_source_manifest_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'forcing_source_manifest_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'provider', 'model_id', 'run_id_format', 'native_resolution_m',
            'assimilation_disclosure', 'source_hash', 'license_review_id',
            'license_review_status', 'permitted_track', 'approved_by', 'approved_at'
        }, 'ForcingSourceManifestV1')
        required = ['provider', 'model_id', 'run_id_format', 'native_resolution_m',
                    'assimilation_disclosure', 'source_hash', 'license_review_id',
                    'license_review_status', 'permitted_track', 'approved_by', 'approved_at']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        packet = cls(
            provider=data['provider'],
            model_id=data['model_id'],
            run_id_format=data['run_id_format'],
            native_resolution_m=float(data['native_resolution_m']),
            assimilation_disclosure=data['assimilation_disclosure'],
            source_hash=data['source_hash'],
            license_review_id=data['license_review_id'],
            license_review_status=data['license_review_status'],
            permitted_track=data['permitted_track'],
            approved_by=data['approved_by'],
            approved_at=datetime.fromisoformat(data['approved_at']),
        )
        packet.validate()
        return packet


@dataclass(frozen=True)
class StationAnchorManifestV1:
    """Track 1 station/anchor source designation."""

    station_id: str
    latitude: float
    longitude: float
    elevation_m: float
    station_type: str  # "aws", "edrmg", "aavds", "manual"
    source_hash: str
    license_review_status: str
    permitted_track: str  # must be "track1"
    approved_by: str
    approved_at: datetime

    def validate(self) -> None:
        if not self.station_id.strip():
            raise PacketValidationError("station_id is required")
        if not (-90.0 <= self.latitude <= 90.0):
            raise PacketValidationError(f"latitude out of range: {self.latitude}")
        if not (-180.0 <= self.longitude <= 180.0):
            raise PacketValidationError(f"longitude out of range: {self.longitude}")
        if self.elevation_m <= 0:
            raise PacketValidationError(f"elevation_m must be positive: {self.elevation_m}")
        if self.station_type not in ("aws", "edrmg", "aavds", "manual"):
            raise PacketValidationError(
                f"station_type must be aws/edrmg/aavds/manual; got {self.station_type}"
            )
        _validate_hex_hash(self.source_hash, "source_hash")
        if self.license_review_status != "approved":
            raise PacketValidationError(
                f"license_review_status must be 'approved'; got {self.license_review_status}"
            )
        if self.permitted_track != "track1":
            raise PacketValidationError(
                f"station/anchor sources are only for track1; got {self.permitted_track}"
            )
        if not self.approved_by.strip():
            raise PacketValidationError("approved_by is required")
        _validate_utc(self.approved_at, "approved_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "station_anchor_manifest_v1",
            "station_id": self.station_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_m": self.elevation_m,
            "station_type": self.station_type,
            "source_hash": self.source_hash,
            "license_review_status": self.license_review_status,
            "permitted_track": self.permitted_track,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StationAnchorManifestV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'StationAnchorManifestV1')
        if data.get('schema') != 'station_anchor_manifest_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'station_anchor_manifest_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'station_id', 'latitude', 'longitude', 'elevation_m',
            'station_type', 'source_hash', 'license_review_status',
            'permitted_track', 'approved_by', 'approved_at'
        }, 'StationAnchorManifestV1')
        required = ['station_id', 'latitude', 'longitude', 'elevation_m',
                    'station_type', 'source_hash', 'license_review_status',
                    'permitted_track', 'approved_by', 'approved_at']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        packet = cls(
            station_id=data['station_id'],
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            elevation_m=float(data['elevation_m']),
            station_type=data['station_type'],
            source_hash=data['source_hash'],
            license_review_status=data['license_review_status'],
            permitted_track=data['permitted_track'],
            approved_by=data['approved_by'],
            approved_at=datetime.fromisoformat(data['approved_at']),
        )
        packet.validate()
        return packet


@dataclass(frozen=True)
class TrackPreflightContextV1:
    """Shared preflight context binding all packets to a track experiment.

    This is the top-level packet that wires together approval, reference unit,
    issue/validity rules, rights, forcing/station sources, label inventory,
    and split manifest. It is the gate that must pass before training.
    """

    track: str  # "track1" or "t2a"
    approval: ApprovalPacketV1
    reference_unit: ReferenceUnitV1
    issue_validity_rule: IssueValidityRuleV1
    rights: RightsManifestV1
    label_inventory_hash: str  # SHA-256 of the label inventory
    split_manifest_hash: str  # SHA-256 of the frozen split manifest
    forcing_source: ForcingSourceManifestV1 | None = None  # required for t2a
    station_source: StationAnchorManifestV1 | None = None  # required for track1
    label_inventory: Any = None  # Optional PartnerLabelInventoryV1 for content binding
    # Relative paths under the ContentResolver root. The keys are deliberately
    # fixed so a packet cannot smuggle an arbitrary file into verification.
    content_paths: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if self.track not in ("track1", "t2a"):
            raise PacketValidationError(
                f"track must be track1/t2a; got {self.track}"
            )
        # Validate all sub-packets
        self.approval.validate()
        self.reference_unit.validate()
        self.issue_validity_rule.validate()
        self.rights.validate()
        _validate_hex_hash(self.label_inventory_hash, "label_inventory_hash")
        _validate_hex_hash(self.split_manifest_hash, "split_manifest_hash")
        # If label_inventory is provided, validate it
        if self.label_inventory is not None:
            from .label_record import PartnerLabelInventoryV1
            if not isinstance(self.label_inventory, PartnerLabelInventoryV1):
                raise PacketValidationError(
                    "label_inventory must be a PartnerLabelInventoryV1 instance"
                )
            self.label_inventory.validate()
            # Verify reference unit matches
            if self.label_inventory.reference_unit != self.reference_unit.reference_unit_name:
                raise PacketValidationError(
                    f"label_inventory reference_unit "
                    f"'{self.label_inventory.reference_unit}' != "
                    f"context reference_unit "
                    f"'{self.reference_unit.reference_unit_name}'"
                )
        allowed_content_keys = {
            "label_inventory", "split_manifest", "reference_geometry",
            "forcing_source", "station_source",
        }
        unknown_content_keys = set(self.content_paths) - allowed_content_keys
        if unknown_content_keys:
            raise PacketValidationError(
                f"content_paths contains unsupported keys: {sorted(unknown_content_keys)}"
            )
        for key, path in self.content_paths.items():
            if not isinstance(path, str) or not path.strip():
                raise PacketValidationError(f"content_paths['{key}'] must be a non-empty path")
        # Track-specific requirements
        if self.track == "t2a":
            if self.forcing_source is None:
                raise PacketValidationError(
                    "t2a requires forcing_source manifest"
                )
            self.forcing_source.validate()
            if self.forcing_source.permitted_track != "t2a":
                raise PacketValidationError(
                    f"t2a forcing source has wrong permitted_track: "
                    f"{self.forcing_source.permitted_track}"
                )
            # T2A must NOT have station sources (station-free by definition)
            if self.station_source is not None:
                raise PacketValidationError(
                    "t2a is station-free; station_source must be None"
                )
        if self.track == "track1":
            if self.station_source is None:
                raise PacketValidationError(
                    "track1 requires station_source manifest"
                )
            self.station_source.validate()
            if self.station_source.permitted_track != "track1":
                raise PacketValidationError(
                    f"track1 station source has wrong permitted_track: "
                    f"{self.station_source.permitted_track}"
                )
        # Approval must cover this track
        if self.track not in self.approval.approved_tracks:
            raise PacketValidationError(
                f"approval does not cover track '{self.track}'; "
                f"approved: {self.approval.approved_tracks}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "track_preflight_context_v1",
            "track": self.track,
            "approval": self.approval.to_dict(),
            "reference_unit": self.reference_unit.to_dict(),
            "issue_validity_rule": self.issue_validity_rule.to_dict(),
            "rights": self.rights.to_dict(),
            "label_inventory_hash": self.label_inventory_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "forcing_source": self.forcing_source.to_dict() if self.forcing_source else None,
            "station_source": self.station_source.to_dict() if self.station_source else None,
            "label_inventory": self.label_inventory.to_dict() if self.label_inventory else None,
            "content_paths": dict(self.content_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackPreflightContextV1":
        """Create from dict with strict schema validation."""
        _require_json_object(data, 'TrackPreflightContextV1')
        if data.get('schema') != 'track_preflight_context_v1':
            raise PacketValidationError(
                f"wrong schema: expected 'track_preflight_context_v1', got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'track', 'approval', 'reference_unit', 'issue_validity_rule',
            'rights', 'label_inventory_hash', 'split_manifest_hash',
            'forcing_source', 'station_source', 'label_inventory', 'content_paths'
        }, 'TrackPreflightContextV1')
        required = ['track', 'approval', 'reference_unit', 'issue_validity_rule',
                    'rights', 'label_inventory_hash', 'split_manifest_hash']
        for field_name in required:
            if field_name not in data:
                raise PacketValidationError(f"missing required field: {field_name}")
        forcing_source = None
        if data.get('forcing_source') is not None:
            forcing_source = ForcingSourceManifestV1.from_dict(data['forcing_source'])
        station_source = None
        if data.get('station_source') is not None:
            station_source = StationAnchorManifestV1.from_dict(data['station_source'])
        label_inventory = None
        if data.get('label_inventory') is not None:
            from .label_record import PartnerLabelInventoryV1
            label_inventory = PartnerLabelInventoryV1.from_dict(data['label_inventory'])
        ctx = cls(
            track=data['track'],
            approval=ApprovalPacketV1.from_dict(data['approval']),
            reference_unit=ReferenceUnitV1.from_dict(data['reference_unit']),
            issue_validity_rule=IssueValidityRuleV1.from_dict(data['issue_validity_rule']),
            rights=RightsManifestV1.from_dict(data['rights']),
            label_inventory_hash=data['label_inventory_hash'],
            split_manifest_hash=data['split_manifest_hash'],
            forcing_source=forcing_source,
            station_source=station_source,
            label_inventory=label_inventory,
            content_paths=dict(data.get('content_paths', {})),
        )
        ctx.validate()
        return ctx


def load_approval_packet_from_json(path: Path) -> ApprovalPacketV1:
    """Load and validate an approval packet from a JSON file."""
    return ApprovalPacketV1.from_dict(_load_json_object(path, 'ApprovalPacketV1'))


def load_reference_unit_from_json(path: Path) -> ReferenceUnitV1:
    """Load and validate a reference unit packet from a JSON file."""
    return ReferenceUnitV1.from_dict(_load_json_object(path, 'ReferenceUnitV1'))


def load_issue_validity_rule_from_json(path: Path) -> IssueValidityRuleV1:
    """Load and validate an issue/validity rule from a JSON file."""
    return IssueValidityRuleV1.from_dict(_load_json_object(path, 'IssueValidityRuleV1'))


def load_rights_manifest_from_json(path: Path) -> RightsManifestV1:
    """Load and validate a rights manifest from a JSON file."""
    return RightsManifestV1.from_dict(_load_json_object(path, 'RightsManifestV1'))


def load_forcing_source_from_json(path: Path) -> ForcingSourceManifestV1:
    """Load and validate a forcing source manifest from a JSON file."""
    return ForcingSourceManifestV1.from_dict(_load_json_object(path, 'ForcingSourceManifestV1'))


def load_station_anchor_from_json(path: Path) -> StationAnchorManifestV1:
    """Load and validate a station/anchor manifest from a JSON file."""
    return StationAnchorManifestV1.from_dict(_load_json_object(path, 'StationAnchorManifestV1'))


def load_track_preflight_context_from_json(path: Path) -> TrackPreflightContextV1:
    """Load and validate a track preflight context from a JSON file."""
    return TrackPreflightContextV1.from_dict(_load_json_object(path, 'TrackPreflightContextV1'))
