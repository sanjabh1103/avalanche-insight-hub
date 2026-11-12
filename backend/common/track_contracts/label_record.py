"""Partner five-level label record contract.

Every historical danger label used for Track 1 or T2A training must satisfy
this contract. It rejects:

- Binary or two-level targets (Partner requires levels 1-5).
- Missing level-5 support (the approval request prohibits silent merging).
- Unsigned placeholders (no training without Partner-approved labels).
- Missing reference unit, issue/validity times, or provenance.

This contract is data-only; it does not fetch, store, or publish anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 5)
MIN_LEVEL = 1
MAX_LEVEL = 5


class LabelValidationError(ValueError):
    """Raised when a Partner label record fails contract validation."""


@dataclass(frozen=True)
class PartnerLabelRecordV1:
    """A single historical Partner danger-level label bound to a reference unit.

    Fields mirror the 'Historical danger labels' row in Section 7 of the
    Partner approval request (page 8).
    """

    level: int  # 1-5
    reference_unit: str  # named Pir Panjal sector or warning unit
    issue_time: datetime  # when the label was issued (UTC)
    valid_time_start: datetime  # validity window start (UTC)
    valid_time_end: datetime  # validity window end (UTC)
    geography: str  # region/sector identifier
    elevation_band: str  # e.g., "3000-4000m"
    aspect_applicability: str  # e.g., "all", "north", "ne"
    issuer: str  # who issued the label
    revision: int  # revision number (0 = original)
    provenance: str  # source document/hash
    rights_status: str  # "approved", "pending", "rejected"
    quality_status: str  # "reviewed", "unreviewed", "auto"
    approved_by: str  # Partner scientist who approved
    approved_at: datetime  # approval timestamp (UTC)
    notes: str = ""
    season: str = ""  # Partner-defined season identifier, when supplied

    def validate(self) -> None:
        """Fail-closed validation of all fields."""
        if not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise LabelValidationError(
                f"level must be {MIN_LEVEL}-{MAX_LEVEL}, got {self.level}"
            )
        if not self.reference_unit.strip():
            raise LabelValidationError("reference_unit is required")
        self._validate_utc(self.issue_time, "issue_time")
        self._validate_utc(self.valid_time_start, "valid_time_start")
        self._validate_utc(self.valid_time_end, "valid_time_end")
        # Enforce issue_time <= valid_time_start < valid_time_end (P4)
        if self.valid_time_start < self.issue_time:
            raise LabelValidationError(
                "valid_time_start must be >= issue_time (label cannot be valid before issued)"
            )
        if self.valid_time_end <= self.valid_time_start:
            raise LabelValidationError("valid_time_end must be after valid_time_start")
        if not self.geography.strip():
            raise LabelValidationError("geography is required")
        if not self.elevation_band.strip():
            raise LabelValidationError("elevation_band is required")
        # Controlled aspect applicability (P4)
        valid_aspects = {"all", "north", "south", "east", "west",
                         "ne", "nw", "se", "sw", "n", "s", "e", "w"}
        if self.aspect_applicability.lower().strip() not in valid_aspects:
            raise LabelValidationError(
                f"aspect_applicability must be one of {sorted(valid_aspects)}, "
                f"got '{self.aspect_applicability}'"
            )
        if not self.issuer.strip():
            raise LabelValidationError("issuer is required")
        if self.revision < 0:
            raise LabelValidationError("revision must be >= 0")
        if not self.provenance.strip():
            raise LabelValidationError("provenance is required")
        if self.rights_status not in ("approved", "pending", "rejected"):
            raise LabelValidationError(
                f"rights_status must be approved/pending/rejected, got {self.rights_status}"
            )
        if self.rights_status != "approved":
            raise LabelValidationError(
                f"rights_status must be 'approved' for training; got {self.rights_status}"
            )
        if self.quality_status not in ("reviewed", "unreviewed", "auto"):
            raise LabelValidationError(
                f"quality_status must be reviewed/unreviewed/auto, got {self.quality_status}"
            )
        # Require reviewed quality status for training (P4)
        if self.quality_status != "reviewed":
            raise LabelValidationError(
                f"quality_status must be 'reviewed' for training; got {self.quality_status}"
            )
        if not self.approved_by.strip():
            raise LabelValidationError("approved_by is required (no unsigned labels)")
        self._validate_utc(self.approved_at, "approved_at")

    @staticmethod
    def _validate_utc(value: datetime, field_name: str) -> None:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise LabelValidationError(f"{field_name} must be timezone-aware UTC")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "Partner_label_record_v1",
            "level": self.level,
            "reference_unit": self.reference_unit,
            "issue_time": self.issue_time.isoformat(),
            "valid_time_start": self.valid_time_start.isoformat(),
            "valid_time_end": self.valid_time_end.isoformat(),
            "geography": self.geography,
            "elevation_band": self.elevation_band,
            "aspect_applicability": self.aspect_applicability,
            "issuer": self.issuer,
            "revision": self.revision,
            "provenance": self.provenance,
            "rights_status": self.rights_status,
            "quality_status": self.quality_status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "notes": self.notes,
            "season": self.season,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PartnerLabelRecordV1":
        """Load a label record without silently dropping fields."""
        if not isinstance(data, dict):
            raise LabelValidationError("label record must be a JSON object")
        known = {
            "schema", "level", "reference_unit", "issue_time", "valid_time_start",
            "valid_time_end", "geography", "elevation_band", "aspect_applicability",
            "issuer", "revision", "provenance", "rights_status", "quality_status",
            "approved_by", "approved_at", "notes", "season",
        }
        unknown = set(data) - known
        if unknown:
            raise LabelValidationError(
                f"PartnerLabelRecordV1: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "Partner_label_record_v1":
            raise LabelValidationError(
                "wrong schema: expected 'Partner_label_record_v1'"
            )
        required = (
            "level", "reference_unit", "issue_time", "valid_time_start",
            "valid_time_end", "geography", "elevation_band", "aspect_applicability",
            "issuer", "revision", "provenance", "rights_status", "quality_status",
            "approved_by", "approved_at",
        )
        missing = [name for name in required if name not in data]
        if missing:
            raise LabelValidationError(f"missing required fields: {missing}")
        try:
            record = cls(
                level=int(data["level"]),
                reference_unit=str(data["reference_unit"]),
                issue_time=datetime.fromisoformat(str(data["issue_time"])),
                valid_time_start=datetime.fromisoformat(str(data["valid_time_start"])),
                valid_time_end=datetime.fromisoformat(str(data["valid_time_end"])),
                geography=str(data["geography"]),
                elevation_band=str(data["elevation_band"]),
                aspect_applicability=str(data["aspect_applicability"]),
                issuer=str(data["issuer"]),
                revision=int(data["revision"]),
                provenance=str(data["provenance"]),
                rights_status=str(data["rights_status"]),
                quality_status=str(data["quality_status"]),
                approved_by=str(data["approved_by"]),
                approved_at=datetime.fromisoformat(str(data["approved_at"])),
                notes=str(data.get("notes", "")),
                season=str(data.get("season", "")),
            )
        except (TypeError, ValueError) as exc:
            raise LabelValidationError(f"invalid label record field: {exc}") from exc
        record.validate()
        return record


@dataclass
class PartnerLabelInventoryV1:
    """Inventory of all historical labels for a reference unit.

    The approval request (Section 7, page 8) requires an inventory by
    season, region, issuer, completeness, and class count. This dataclass
    enforces that the inventory covers all five levels.
    """

    records: list[PartnerLabelRecordV1] = field(default_factory=list)
    reference_unit: str = ""
    seasons_covered: list[str] = field(default_factory=list)
    record_counts_by_level: dict[int, int] = field(default_factory=dict)
    missing_periods: list[str] = field(default_factory=list)
    policy_changes: list[str] = field(default_factory=list)
    level_5_support: bool = False
    support_policy_id: str = ""
    support_policy_hash: str = ""
    support_policy_signed_by: str = ""
    minimum_seasons: int = 3
    minimum_support_by_level: dict[int, int] = field(default_factory=dict)
    source_hash: str = ""

    def validate(self) -> None:
        if not self.reference_unit.strip():
            raise LabelValidationError("reference_unit is required for inventory")
        # Reject empty inventories
        if not self.records:
            raise LabelValidationError(
                "inventory has no records; cannot validate an empty inventory"
            )
        # Validate each record
        for record in self.records:
            record.validate()
        # Check all records share the inventory's reference_unit
        for record in self.records:
            if record.reference_unit != self.reference_unit:
                raise LabelValidationError(
                    f"record reference_unit '{record.reference_unit}' != "
                    f"inventory reference_unit '{self.reference_unit}'"
                )
        # Check for duplicate revisions (same level+issue_time+reference_unit+revision)
        seen_keys: set[tuple[int, datetime, str, int]] = set()
        for record in self.records:
            key = (record.level, record.issue_time, record.reference_unit, record.revision)
            if key in seen_keys:
                raise LabelValidationError(
                    f"duplicate record: level={record.level}, "
                    f"issue_time={record.issue_time}, revision={record.revision}"
                )
            seen_keys.add(key)
        # Recompute counts from actual records (do not trust caller-supplied counts)
        actual_counts: dict[int, int] = {}
        for record in self.records:
            actual_counts[record.level] = actual_counts.get(record.level, 0) + 1
        # Verify caller-supplied counts match actual
        if self.record_counts_by_level != actual_counts:
            raise LabelValidationError(
                f"record_counts_by_level does not match actual record counts: "
                f"claimed={self.record_counts_by_level}, actual={actual_counts}"
            )
        # Check all five levels are represented
        present_levels = set(actual_counts.keys())
        missing = set(REQUIRED_LEVELS) - present_levels
        if missing:
            raise LabelValidationError(
                f"inventory missing levels: {sorted(missing)}; all five required"
            )
        # Level 5 support must be backed by actual Level 5 records
        if self.level_5_support and actual_counts.get(5, 0) == 0:
            raise LabelValidationError(
                "level_5_support=True but no Level 5 records exist; "
                "cannot claim support without evidence"
            )
        if not self.level_5_support:
            raise LabelValidationError(
                "level_5_support must be True; cannot merge Level 4/5 silently"
            )
        # Check minimum support per level
        for level in REQUIRED_LEVELS:
            count = actual_counts.get(level, 0)
            if count <= 0:
                raise LabelValidationError(
                    f"level {level} has {count} records; minimum 1 required"
                )

        if self.seasons_covered:
            declared_seasons = {str(season).strip() for season in self.seasons_covered}
            if "" in declared_seasons:
                raise LabelValidationError("seasons_covered cannot contain empty values")
            if len(declared_seasons) != len(self.seasons_covered):
                raise LabelValidationError("seasons_covered cannot contain duplicates")
            record_seasons = {record.season for record in self.records if record.season}
            if record_seasons and not record_seasons.issubset(declared_seasons):
                raise LabelValidationError(
                    "record season is not present in seasons_covered"
                )

        if self.minimum_seasons <= 0:
            raise LabelValidationError("minimum_seasons must be positive")
        for level, minimum in self.minimum_support_by_level.items():
            if level not in REQUIRED_LEVELS or not isinstance(minimum, int) or minimum <= 0:
                raise LabelValidationError(
                    "minimum_support_by_level must contain positive integer values "
                    "for levels 1-5"
                )
            if actual_counts.get(level, 0) < minimum:
                raise LabelValidationError(
                    f"level {level} has {actual_counts.get(level, 0)} records; "
                    f"minimum policy support is {minimum}"
                )

        if self.support_policy_hash:
            self._validate_hex_hash(self.support_policy_hash, "support_policy_hash")
        if self.source_hash:
            self._validate_hex_hash(self.source_hash, "source_hash")
        if self.support_policy_id and not self.support_policy_signed_by.strip():
            raise LabelValidationError(
                "support_policy_signed_by is required when support_policy_id is supplied"
            )

    @staticmethod
    def _validate_hex_hash(value: str, field_name: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise LabelValidationError(f"{field_name} must be a 64-character hexadecimal hash")

    def training_eligibility_blockers(self) -> list[str]:
        """Return the additional Partner evidence required before training.

        ``validate`` proves structural integrity. This method proves that the
        inventory carries a Partner-supplied support policy and enough seasonal,
        reviewer-bound evidence to authorize training.
        """
        blockers: list[str] = []
        try:
            self.validate()
        except LabelValidationError as exc:
            return [str(exc)]

        if len(self.seasons_covered) < self.minimum_seasons:
            blockers.append(
                f"inventory covers {len(self.seasons_covered)} seasons; "
                f"minimum is {self.minimum_seasons}"
            )
        if any(not record.season for record in self.records):
            blockers.append("every label record must carry an exact Partner season identifier")
        else:
            record_seasons = {record.season for record in self.records}
            declared_seasons = {str(season).strip() for season in self.seasons_covered}
            if record_seasons != declared_seasons:
                blockers.append(
                    "seasons_covered must exactly match the seasons carried by label records"
                )
        if not self.support_policy_id.strip():
            blockers.append("support_policy_id is required for training eligibility")
        if not self.support_policy_hash:
            blockers.append("support_policy_hash is required for training eligibility")
        else:
            try:
                self._validate_hex_hash(self.support_policy_hash, "support_policy_hash")
            except LabelValidationError as exc:
                blockers.append(str(exc))
        if not self.support_policy_signed_by.strip():
            blockers.append("support_policy_signed_by is required for training eligibility")
        if not self.source_hash:
            blockers.append("source_hash is required to bind labels to their source")
        else:
            try:
                self._validate_hex_hash(self.source_hash, "source_hash")
            except LabelValidationError as exc:
                blockers.append(str(exc))
        missing_policy_levels = set(REQUIRED_LEVELS) - set(self.minimum_support_by_level)
        if missing_policy_levels:
            blockers.append(
                "minimum_support_by_level must define Partner support thresholds for "
                f"levels {sorted(missing_policy_levels)}"
            )
        return blockers

    @property
    def training_eligible(self) -> bool:
        return not self.training_eligibility_blockers()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "Partner_label_inventory_v1",
            "records": [record.to_dict() for record in self.records],
            "reference_unit": self.reference_unit,
            "seasons_covered": self.seasons_covered,
            "record_counts_by_level": {
                str(level): count for level, count in self.record_counts_by_level.items()
            },
            "missing_periods": self.missing_periods,
            "policy_changes": self.policy_changes,
            "level_5_support": self.level_5_support,
            "support_policy_id": self.support_policy_id,
            "support_policy_hash": self.support_policy_hash,
            "support_policy_signed_by": self.support_policy_signed_by,
            "minimum_seasons": self.minimum_seasons,
            "minimum_support_by_level": {
                str(level): count for level, count in self.minimum_support_by_level.items()
            },
            "source_hash": self.source_hash,
            "record_count": len(self.records),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PartnerLabelInventoryV1":
        """Load the complete inventory, including every label record."""
        if not isinstance(data, dict):
            raise LabelValidationError("label inventory must be a JSON object")
        known = {
            "schema", "records", "reference_unit", "seasons_covered",
            "record_counts_by_level", "missing_periods", "policy_changes",
            "level_5_support", "support_policy_id", "support_policy_hash",
            "support_policy_signed_by", "minimum_seasons", "minimum_support_by_level",
            "source_hash", "record_count",
        }
        unknown = set(data) - known
        if unknown:
            raise LabelValidationError(
                f"PartnerLabelInventoryV1: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "Partner_label_inventory_v1":
            raise LabelValidationError(
                "wrong schema: expected 'Partner_label_inventory_v1'"
            )
        required = (
            "records", "reference_unit", "seasons_covered", "record_counts_by_level",
            "missing_periods", "policy_changes", "level_5_support",
        )
        missing = [name for name in required if name not in data]
        if missing:
            raise LabelValidationError(f"missing required fields: {missing}")
        records = [PartnerLabelRecordV1.from_dict(item) for item in data["records"]]
        counts = {int(level): int(count) for level, count in data["record_counts_by_level"].items()}
        minimum_support = {
            int(level): int(count)
            for level, count in data.get("minimum_support_by_level", {}).items()
        }
        inventory = cls(
            records=records,
            reference_unit=str(data["reference_unit"]),
            seasons_covered=[str(value) for value in data["seasons_covered"]],
            record_counts_by_level=counts,
            missing_periods=[str(value) for value in data["missing_periods"]],
            policy_changes=[str(value) for value in data["policy_changes"]],
            level_5_support=bool(data["level_5_support"]),
            support_policy_id=str(data.get("support_policy_id", "")),
            support_policy_hash=str(data.get("support_policy_hash", "")),
            support_policy_signed_by=str(data.get("support_policy_signed_by", "")),
            minimum_seasons=int(data.get("minimum_seasons", 3)),
            minimum_support_by_level=minimum_support,
            source_hash=str(data.get("source_hash", "")),
        )
        if "record_count" in data and int(data["record_count"]) != len(records):
            raise LabelValidationError("record_count does not match records")
        inventory.validate()
        return inventory


def load_label_inventory_from_json(path: Path) -> PartnerLabelInventoryV1:
    """Load a complete Partner inventory from a JSON file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelValidationError(f"cannot load label inventory {path}: {exc}") from exc
    return PartnerLabelInventoryV1.from_dict(data)
