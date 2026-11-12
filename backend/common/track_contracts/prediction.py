"""Learned five-level danger prediction contract.

This is the ML output contract required by the Partner approval request
(Section 3, page 4). It is SEPARATE from the rule-weighted shadow danger
semantics in ``shadow_danger_semantics.py``.

Key requirements from the approval request:
- The model produces a probability for every approved level from 1 through 5.
- The reported level is selected from those learned class probabilities.
- Fixed risk bands, binary-risk conversion, and the EAWS Matrix are NOT
  substitutes for the learned final output.
- The five-level scale is ordinal; evaluation includes both exact
  classification and the size/direction of level errors.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class PredictionValidationError(ValueError):
    """Raised when a danger prediction fails contract validation."""


REQUIRED_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 5)
NUM_LEVELS = 5


@dataclass(frozen=True)
class DangerPredictionV1:
    """A learned five-level danger prediction with calibrated probabilities.

    This contract rejects:
    - Fewer than 5 class probabilities (binary or merged output).
    - Probabilities that do not sum to ~1.0 (uncalibrated output).
    - Missing reference unit or validity interval.
    - Missing model/snapshot provenance.
    - Predictions from fixed thresholds rather than learned probabilities.
    """

    probabilities: tuple[float, ...]  # exactly 5, ordered 1-5
    predicted_level: int  # 1-5, selected from argmax of probabilities
    reference_unit: str
    valid_time_start: datetime
    valid_time_end: datetime
    model_id: str  # e.g., "t2a_rf_v1" or "track1_rf_v1"
    snapshot_id: str  # content hash of the model artifact
    track: str  # "track1", "t2a", or "t2b"
    issue_time: datetime
    calibration_method: str  # "sigmoid", "isotonic", "none"
    abstention: bool = False  # True if model abstains (insufficient evidence)
    abstention_reason: str = ""
    is_diagnostic_only: bool = False  # True if uncalibrated/research-only output
    manifest_digest: str = ""  # experiment manifest content hash
    feature_hash: str = ""  # feature contract content hash
    source_hash: str = ""  # source/forcing content hash
    context_hash: str = ""  # preflight context content hash
    calibration_hash: str = ""  # calibration artifact/content hash
    approval_id: str = ""  # authority-resolved approval reference

    def validate(self) -> None:
        """Fail-closed validation."""
        if len(self.probabilities) != NUM_LEVELS:
            raise PredictionValidationError(
                f"exactly {NUM_LEVELS} probabilities required (one per level 1-5); "
                f"got {len(self.probabilities)}"
            )
        for i, p in enumerate(self.probabilities):
            if not math.isfinite(p):
                raise PredictionValidationError(
                    f"probability[{i}] is not finite: {p}"
                )
            if not 0.0 <= p <= 1.0:
                raise PredictionValidationError(
                    f"probability[{i}] out of [0,1]: {p}"
                )
        total = sum(self.probabilities)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise PredictionValidationError(
                f"probabilities must sum to 1.0; got {total}"
            )
        if not 1 <= self.predicted_level <= 5:
            raise PredictionValidationError(
                f"predicted_level must be 1-5; got {self.predicted_level}"
            )
        # predicted_level must be argmax of probabilities
        expected_level = 1 + max(range(NUM_LEVELS), key=lambda i: self.probabilities[i])
        if self.predicted_level != expected_level and not self.abstention:
            raise PredictionValidationError(
                f"predicted_level {self.predicted_level} != argmax {expected_level}"
            )
        if not self.reference_unit.strip():
            raise PredictionValidationError("reference_unit is required")
        self._validate_utc(self.valid_time_start, "valid_time_start")
        self._validate_utc(self.valid_time_end, "valid_time_end")
        if self.valid_time_end <= self.valid_time_start:
            raise PredictionValidationError(
                "valid_time_end must be after valid_time_start"
            )
        self._validate_utc(self.issue_time, "issue_time")
        if self.issue_time > self.valid_time_start:
            raise PredictionValidationError(
                "issue_time must be <= valid_time_start"
            )
        if self.track not in ("track1", "t2a", "t2b"):
            raise PredictionValidationError(
                f"track must be track1/t2a/t2b; got {self.track}"
            )
        if not self.model_id.strip():
            raise PredictionValidationError("model_id is required")
        if not self.snapshot_id.strip():
            raise PredictionValidationError("snapshot_id is required")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.snapshot_id):
            raise PredictionValidationError(
                "snapshot_id must be a 64-character hexadecimal content hash"
            )
        if self.calibration_method not in ("sigmoid", "isotonic", "none"):
            raise PredictionValidationError(
                f"calibration_method must be sigmoid/isotonic/none; "
                f"got {self.calibration_method}"
            )
        # Uncalibrated predictions are diagnostic-only, not publishable
        if self.calibration_method == "none" and not self.is_diagnostic_only:
            raise PredictionValidationError(
                "calibration_method='none' is not publishable; "
                "set is_diagnostic_only=True for research-only output"
            )
        if not self.is_diagnostic_only:
            for field_name in (
                "manifest_digest", "feature_hash", "source_hash",
                "context_hash", "calibration_hash",
            ):
                value = getattr(self, field_name)
                if not re.fullmatch(r"[0-9a-fA-F]{64}", value or ""):
                    raise PredictionValidationError(
                        f"{field_name} must be a 64-character hexadecimal content hash "
                        "for publishable output"
                    )
            if not self.approval_id.strip():
                raise PredictionValidationError(
                    "approval_id is required for publishable output"
                )
        if self.abstention and not self.abstention_reason.strip():
            raise PredictionValidationError(
                "abstention_reason required when abstention=True"
            )

    @staticmethod
    def _validate_utc(value: datetime, field_name: str) -> None:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise PredictionValidationError(f"{field_name} must be timezone-aware UTC")

    @property
    def level_probabilities(self) -> dict[int, float]:
        """Map level -> probability."""
        return {level: prob for level, prob in zip(REQUIRED_LEVELS, self.probabilities)}

    def ordinal_error_distance(self, true_level: int) -> int:
        """Absolute distance between predicted and true level (ordinal metric)."""
        if not 1 <= true_level <= 5:
            raise PredictionValidationError(f"true_level must be 1-5; got {true_level}")
        return abs(self.predicted_level - true_level)

    def within_one_level(self, true_level: int) -> bool:
        """True if prediction is within ±1 level of truth."""
        return self.ordinal_error_distance(true_level) <= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "danger_prediction_v1",
            "probabilities": list(self.probabilities),
            "predicted_level": self.predicted_level,
            "reference_unit": self.reference_unit,
            "valid_time_start": self.valid_time_start.isoformat(),
            "valid_time_end": self.valid_time_end.isoformat(),
            "issue_time": self.issue_time.isoformat(),
            "model_id": self.model_id,
            "snapshot_id": self.snapshot_id,
            "track": self.track,
            "calibration_method": self.calibration_method,
            "abstention": self.abstention,
            "abstention_reason": self.abstention_reason,
            "is_diagnostic_only": self.is_diagnostic_only,
            "manifest_digest": self.manifest_digest,
            "feature_hash": self.feature_hash,
            "source_hash": self.source_hash,
            "context_hash": self.context_hash,
            "calibration_hash": self.calibration_hash,
            "approval_id": self.approval_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DangerPredictionV1":
        """Load a prediction with strict schema and provenance preservation."""
        if not isinstance(data, dict):
            raise PredictionValidationError("prediction must be a JSON object")
        known = {
            "schema", "probabilities", "predicted_level", "reference_unit",
            "valid_time_start", "valid_time_end", "issue_time", "model_id",
            "snapshot_id", "track", "calibration_method", "abstention",
            "abstention_reason", "is_diagnostic_only", "manifest_digest",
            "feature_hash", "source_hash", "context_hash", "calibration_hash",
            "approval_id",
        }
        unknown = set(data) - known
        if unknown:
            raise PredictionValidationError(
                f"DangerPredictionV1: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "danger_prediction_v1":
            raise PredictionValidationError("wrong schema: expected 'danger_prediction_v1'")
        required = (
            "probabilities", "predicted_level", "reference_unit", "valid_time_start",
            "valid_time_end", "issue_time", "model_id", "snapshot_id", "track",
            "calibration_method",
        )
        missing = [field_name for field_name in required if field_name not in data]
        if missing:
            raise PredictionValidationError(f"missing required fields: {missing}")
        if not isinstance(data["probabilities"], list):
            raise PredictionValidationError("probabilities must be a list")
        for field_name in ("abstention", "is_diagnostic_only"):
            if field_name in data and not isinstance(data[field_name], bool):
                raise PredictionValidationError(f"{field_name} must be a boolean")
        try:
            prediction = cls(
                probabilities=tuple(float(value) for value in data["probabilities"]),
                predicted_level=int(data["predicted_level"]),
                reference_unit=str(data["reference_unit"]),
                valid_time_start=datetime.fromisoformat(str(data["valid_time_start"])),
                valid_time_end=datetime.fromisoformat(str(data["valid_time_end"])),
                issue_time=datetime.fromisoformat(str(data["issue_time"])),
                model_id=str(data["model_id"]),
                snapshot_id=str(data["snapshot_id"]),
                track=str(data["track"]),
                calibration_method=str(data["calibration_method"]),
                abstention=bool(data.get("abstention", False)),
                abstention_reason=str(data.get("abstention_reason", "")),
                is_diagnostic_only=bool(data.get("is_diagnostic_only", False)),
                manifest_digest=str(data.get("manifest_digest", "")),
                feature_hash=str(data.get("feature_hash", "")),
                source_hash=str(data.get("source_hash", "")),
                context_hash=str(data.get("context_hash", "")),
                calibration_hash=str(data.get("calibration_hash", "")),
                approval_id=str(data.get("approval_id", "")),
            )
        except (TypeError, ValueError) as exc:
            raise PredictionValidationError(f"invalid prediction field: {exc}") from exc
        prediction.validate()
        return prediction
