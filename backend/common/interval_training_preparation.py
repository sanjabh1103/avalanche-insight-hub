"""Content-addressed preparation evidence for interval-censored training.

The existing model path consumes point timestamps.  This module implements the
boundary immediately before model fitting: it verifies the exact interval
frame, source/feature hashes, temporal and spatial groups, and approval
requirements without converting an interval into a fabricated timestamp.

The result is deliberately shadow-only.  It is not a model-training adapter,
does not construct negatives, and cannot mark a row or artifact eligible for
core training or production scoring.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from backend.common.interval_training_contract import (
    INTERVAL_LOSS_IMPLEMENTATION_STATUS,
    INTERVAL_LOSS_SEMANTICS_STATUS,
    INTERVAL_NEGATIVE_SAMPLING_STATUS,
    INTERVAL_TRAINING_CONTRACT_VERSION,
    INTERVAL_TRAINING_PATH_STATUS,
    INTERVAL_TRAINING_PREPARATION_VERSION,
)
from backend.common.interval_training_reproducibility import (
    validate_interval_training_frame,
)
from backend.common.label_time_contract import LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class IntervalTrainingPreparationError(ValueError):
    """Raised when interval preparation evidence is incomplete or unsafe."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_field(value: Any, *, field: str) -> str:
    result = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(result):
        raise IntervalTrainingPreparationError(f"{field} must be a SHA-256 value")
    return result


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _canonical(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _read_frame(frame_path: Path, expected_hash: str) -> tuple[list[dict[str, Any]], str]:
    try:
        payload = frame_path.read_bytes()
    except OSError as exc:
        raise IntervalTrainingPreparationError(
            f"interval frame snapshot cannot be read: {frame_path}"
        ) from exc
    actual_hash = _sha256(payload)
    if actual_hash != expected_hash:
        raise IntervalTrainingPreparationError("interval frame snapshot hash mismatch")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IntervalTrainingPreparationError(
                f"interval frame line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise IntervalTrainingPreparationError(
                f"interval frame line {line_number} must be an object"
            )
        rows.append(value)
    if not rows:
        raise IntervalTrainingPreparationError("interval frame snapshot is empty")
    validation = validate_interval_training_frame(rows)
    if not validation["passed"]:
        raise IntervalTrainingPreparationError(
            f"interval frame validation failed: {validation['error_counts']}"
        )
    return rows, actual_hash


def _require_false(container: Mapping[str, Any], field: str, *, label: str) -> None:
    if container.get(field) is not False:
        raise IntervalTrainingPreparationError(f"{label} {field} must be false")


def _validate_split_boundaries(boundaries: Any) -> dict[str, Any]:
    if not isinstance(boundaries, Mapping):
        raise IntervalTrainingPreparationError("interval split_boundaries are required")
    normalized: dict[str, Any] = {}
    seen: set[str] = set()
    for split_name in ("train", "calibration", "test"):
        split = boundaries.get(split_name)
        if not isinstance(split, Mapping):
            raise IntervalTrainingPreparationError(
                f"interval split boundary is missing: {split_name}"
            )
        group_ids = [
            str(value).strip()
            for value in split.get("event_group_ids", [])
            if str(value).strip()
        ] if isinstance(split.get("event_group_ids"), list) else []
        if not group_ids:
            raise IntervalTrainingPreparationError(
                f"interval split boundary has no event groups: {split_name}"
            )
        if seen.intersection(group_ids):
            raise IntervalTrainingPreparationError(
                "interval event groups overlap across split boundaries"
            )
        seen.update(group_ids)
        normalized[split_name] = {
            key: value
            for key, value in split.items()
            if key != "event_group_ids"
        }
        normalized[split_name]["event_group_ids"] = group_ids
    return normalized


def build_interval_training_preparation_manifest(
    *,
    label_manifest: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    join_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate shadow evidence and return a non-promoting preparation manifest."""

    if not isinstance(label_manifest, Mapping):
        raise IntervalTrainingPreparationError("label_manifest must be an object")
    if not isinstance(feature_manifest, Mapping):
        raise IntervalTrainingPreparationError("feature_manifest must be an object")
    if not isinstance(join_report, Mapping):
        raise IntervalTrainingPreparationError("join_report must be an object")

    if join_report.get("status") != "shadow_frame_written":
        raise IntervalTrainingPreparationError(
            "join_report status must be shadow_frame_written"
        )
    _require_false(join_report, "training_eligible", label="join_report")
    _require_false(join_report, "production_scoring_eligible", label="join_report")
    if join_report.get("shadow_only") is not True:
        raise IntervalTrainingPreparationError("join_report shadow_only must be true")

    label_hash = _sha256_field(
        label_manifest.get("event_rows_sha256"),
        field="label_manifest.event_rows_sha256",
    )
    if str(join_report.get("label_event_rows_sha256") or "").strip().lower() != label_hash:
        raise IntervalTrainingPreparationError(
            "join_report label event hash does not match label manifest"
        )
    feature_hash = _sha256_field(
        feature_manifest.get("manifest_hash"),
        field="feature_manifest.manifest_hash",
    )
    if str(join_report.get("feature_manifest_hash") or "").strip().lower() != feature_hash:
        raise IntervalTrainingPreparationError(
            "join_report feature manifest hash does not match feature manifest"
        )
    _require_false(feature_manifest, "training_eligible", label="feature_manifest")
    _require_false(
        feature_manifest,
        "production_scoring_eligible",
        label="feature_manifest",
    )

    evidence = join_report.get("evidence")
    if not isinstance(evidence, Mapping):
        raise IntervalTrainingPreparationError("join_report evidence is required")
    if evidence.get("validation", {}).get("passed") is not True:
        raise IntervalTrainingPreparationError("interval shadow validation did not pass")
    if evidence.get("shadow_only") is not True:
        raise IntervalTrainingPreparationError("interval evidence shadow_only must be true")
    _require_false(evidence, "core_training_eligible", label="interval evidence")
    _require_false(
        evidence,
        "production_scoring_eligible",
        label="interval evidence",
    )

    frame_path_value = str(evidence.get("snapshot_path") or "").strip()
    if not frame_path_value:
        raise IntervalTrainingPreparationError("interval evidence snapshot_path is required")
    frame_hash = _sha256_field(evidence.get("snapshot_hash"), field="snapshot_hash")
    file_hash = _sha256_field(
        evidence.get("snapshot_file_sha256"),
        field="snapshot_file_sha256",
    )
    if frame_hash != file_hash:
        raise IntervalTrainingPreparationError(
            "interval evidence snapshot hashes do not agree"
        )
    frame_rows, actual_frame_hash = _read_frame(Path(frame_path_value), frame_hash)

    row_count = int(evidence.get("row_count") or 0)
    if row_count != len(frame_rows):
        raise IntervalTrainingPreparationError(
            "interval evidence row_count does not match the frame snapshot"
        )
    event_group_ids = {
        str(row.get("event_group_id") or "").strip()
        for row in frame_rows
        if str(row.get("event_group_id") or "").strip()
    }
    spatial_group_ids = {
        str(row.get("spatial_group_id") or "").strip()
        for row in frame_rows
        if str(row.get("spatial_group_id") or "").strip()
    }
    if int(evidence.get("event_group_count") or 0) != len(event_group_ids):
        raise IntervalTrainingPreparationError(
            "interval evidence event_group_count does not match the frame snapshot"
        )
    if int(evidence.get("spatial_group_count") or 0) != len(spatial_group_ids):
        raise IntervalTrainingPreparationError(
            "interval evidence spatial_group_count does not match the frame snapshot"
        )

    seasons = sorted({
        str(value).strip()
        for value in evidence.get("positive_season_ids", [])
        if str(value).strip()
    }) if isinstance(evidence.get("positive_season_ids"), list) else []
    source_ids = sorted({
        str(value).strip()
        for value in evidence.get("positive_source_ids", [])
        if str(value).strip()
    }) if isinstance(evidence.get("positive_source_ids"), list) else []
    source_families = sorted({
        str(value).strip()
        for value in evidence.get("independent_positive_source_family_ids", [])
        if str(value).strip()
    }) if isinstance(evidence.get("independent_positive_source_family_ids"), list) else []
    if len(seasons) < 3:
        raise IntervalTrainingPreparationError(
            f"interval preparation requires at least three positive seasons; found {len(seasons)}"
        )
    if len(source_families) < 2:
        raise IntervalTrainingPreparationError(
            "interval preparation requires at least two independent source families"
        )
    split_boundaries = _validate_split_boundaries(evidence.get("split_boundaries"))

    source_manifests = feature_manifest.get("source_manifests")
    if not isinstance(source_manifests, Mapping) or not source_manifests:
        raise IntervalTrainingPreparationError(
            "feature_manifest source_manifests are required"
        )
    source_reviews = {}
    for source_key, source_manifest in sorted(source_manifests.items()):
        if not isinstance(source_manifest, Mapping):
            raise IntervalTrainingPreparationError(
                f"feature source manifest is invalid: {source_key}"
            )
        source_reviews[str(source_key)] = {
            "license_status": str(source_manifest.get("license_status") or "pending"),
            "cutoff_policy_review_status": str(
                source_manifest.get("cutoff_policy_review_status")
                or feature_manifest.get("cutoff_policy_review_status")
                or "pending"
            ),
        }

    body: dict[str, Any] = {
        "schema_version": INTERVAL_TRAINING_PREPARATION_VERSION,
        "contract_version": INTERVAL_TRAINING_CONTRACT_VERSION,
        "label_time_contract": LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
        "training_path_status": INTERVAL_TRAINING_PATH_STATUS,
        "shadow_evidence_ready": True,
        "interval_training_ready": False,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
        "inputs": {
            "label_event_rows_sha256": label_hash,
            "feature_manifest_sha256": feature_hash,
            "interval_frame_sha256": actual_frame_hash,
            "feature_rows_sha256": str(
                feature_manifest.get("feature_rows_sha256") or ""
            ).strip() or None,
            "row_count": len(frame_rows),
            "event_group_count": len(event_group_ids),
            "spatial_group_count": len(spatial_group_ids),
            "region_keys": sorted({
                str(row.get("region_key") or "").strip()
                for row in frame_rows
                if str(row.get("region_key") or "").strip()
            }),
        },
        "evidence": {
            "positive_season_ids": seasons,
            "positive_source_ids": source_ids,
            "independent_positive_source_family_ids": source_families,
            "source_family_counts": dict(
                sorted((str(key), int(value)) for key, value in (
                    evidence.get("source_family_counts") or {}
                ).items())
            ) if isinstance(evidence.get("source_family_counts"), Mapping) else {},
            "split_boundaries": split_boundaries,
            "source_reviews": source_reviews,
        },
        "contract": {
            "point_time_synthesis_forbidden": True,
            "feature_cutoff_must_be_at_or_before_interval_start": True,
            "negative_sampling_status": INTERVAL_NEGATIVE_SAMPLING_STATUS,
            "interval_loss_implementation_status": INTERVAL_LOSS_IMPLEMENTATION_STATUS,
            "interval_loss_semantics_status": INTERVAL_LOSS_SEMANTICS_STATUS,
            "model_fit_status": "not_implemented",
            "promotion_status": "forbidden",
        },
        "approval": {
            "source_license_status": "pending_review",
            "cutoff_policy_status": "pending_scientist_approval",
            "required_before_core_training": [
                "permissive_core_reviewed feature source licence",
                "approved retrospective cutoff policy",
                "approved interval loss and negative-sampling semantics",
                "independent model-quality gate",
            ],
        },
    }
    body["manifest_hash"] = _sha256(_canonical_bytes(body))
    return body


def validate_interval_training_preparation_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the preparation manifest without changing its promotion flags."""
    if not isinstance(manifest, Mapping):
        return {"passed": False, "errors": ["manifest must be an object"]}
    errors: list[str] = []
    expected_hash = str(manifest.get("manifest_hash") or "").strip().lower()
    if not _SHA256_RE.fullmatch(expected_hash):
        errors.append("manifest_hash is missing or invalid")
    else:
        body = {str(key): value for key, value in manifest.items() if key != "manifest_hash"}
        if _sha256(_canonical_bytes(body)) != expected_hash:
            errors.append("manifest_hash does not match manifest content")
    if manifest.get("schema_version") != INTERVAL_TRAINING_PREPARATION_VERSION:
        errors.append("unsupported interval preparation schema_version")
    if manifest.get("training_path_status") != INTERVAL_TRAINING_PATH_STATUS:
        errors.append("unexpected interval training path status")
    for field in (
        "shadow_evidence_ready",
        "interval_training_ready",
        "training_eligible",
        "core_training_eligible",
        "production_scoring_eligible",
    ):
        if field in manifest and manifest.get(field) is not (True if field == "shadow_evidence_ready" else False):
            errors.append(f"{field} has an unsafe value")
    contract = manifest.get("contract")
    if not isinstance(contract, Mapping):
        errors.append("contract is missing")
    elif contract.get("point_time_synthesis_forbidden") is not True:
        errors.append("point_time_synthesis_forbidden must be true")
    elif contract.get("interval_loss_implementation_status") != INTERVAL_LOSS_IMPLEMENTATION_STATUS:
        errors.append("interval_loss_implementation_status is not the expected shadow-only value")
    return {"passed": not errors, "errors": errors, "manifest_hash": expected_hash}


def write_interval_training_preparation_manifest(
    path: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Write and revalidate a preparation manifest atomically at the file level."""
    validation = validate_interval_training_preparation_manifest(manifest)
    if not validation["passed"]:
        raise IntervalTrainingPreparationError(
            f"invalid interval preparation manifest: {validation['errors']}"
        )
    payload = json.dumps(
        _canonical(manifest),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    loaded = load_interval_training_preparation_manifest(path)
    return loaded


def load_interval_training_preparation_manifest(path: Path) -> dict[str, Any]:
    """Load and validate one preparation manifest from disk."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntervalTrainingPreparationError(
            f"interval preparation manifest cannot be read: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise IntervalTrainingPreparationError("interval preparation manifest must be an object")
    validation = validate_interval_training_preparation_manifest(value)
    if not validation["passed"]:
        raise IntervalTrainingPreparationError(
            f"invalid interval preparation manifest: {validation['errors']}"
        )
    return value
