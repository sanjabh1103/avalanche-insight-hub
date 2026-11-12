#!/usr/bin/env python3
"""Validate a customer-approved, non-promoting MVP4 shadow-scope decision.

This is intentionally separate from ``verify_mvp4_pre_remote_gate.py``.  An
approved shadow scope can authorize only bounded evidence work; it can never
clear the exact-time core gate or authorize model fitting, production scoring,
remote pilots, or timestamp synthesis.

Exit codes:
  0  an attributable APPROVED_SHADOW_ONLY decision is valid
  2  pending, malformed, promoted, or externally-bound evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "mvp4_shadow_scope_approval_v1"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
SCIENTIST_ROLES = {"scientist", "data_owner"}
CUSTOMER_ROLES = {"customer", "product_owner"}
REQUIRED_DECISIONS = {
    "station_free_interpretation",
    "historical_feature_cutoff",
    "interval_label_semantics",
    "negative_sampling",
    "customer_claims",
    "source_rights_and_api_scope",
}


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(value: Any, label: str, errors: list[str]) -> Path:
    if isinstance(value, Path):
        candidate = value.expanduser()
    elif isinstance(value, str) and value.strip():
        candidate = Path(value).expanduser()
    else:
        errors.append(f"{label} must be a non-empty repository-relative path")
        return ROOT / "__invalid_shadow_scope_input__"
    try:
        resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        errors.append(f"{label} must resolve under the repository root")
        return ROOT / "__invalid_shadow_scope_input__"
    return resolved


def _load_manifest(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"shadow-scope approval manifest does not resolve to a file: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"shadow-scope approval manifest is not valid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append("shadow-scope approval manifest must be a JSON object")
        return None
    return value


def _has_identity(item: Any) -> bool:
    return isinstance(item, dict) and bool(
        str(item.get("name") or item.get("approval_ref") or "").strip()
    )


def _check_approval_time(value: Any, errors: list[str]) -> None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone missing")
    except ValueError:
        errors.append("approved_at must be timezone-aware ISO-8601")


def validate_shadow_scope_approval(manifest_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    resolved_manifest = _repo_path(manifest_path, "approval manifest", errors)
    manifest = _load_manifest(resolved_manifest, errors)
    decision = manifest.get("decision") if manifest else None
    approved = decision == "APPROVED_SHADOW_ONLY"

    if manifest is not None:
        if manifest.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"schema_version must be {SCHEMA_VERSION}")
        if decision not in {"PENDING", "APPROVED_SHADOW_ONLY"}:
            errors.append("decision must be PENDING or APPROVED_SHADOW_ONLY")

        regions = manifest.get("selected_region_keys")
        if not isinstance(regions, list) or not regions or any(
            not isinstance(item, str) or not item.strip() for item in regions
        ):
            errors.append("selected_region_keys must be a non-empty list of names")
        elif len({item.strip() for item in regions}) != len(regions):
            errors.append("selected_region_keys must not contain duplicates")

        policy = manifest.get("policy")
        if not isinstance(policy, dict):
            errors.append("policy must be an object")
        else:
            required_false = (
                "model_fit_allowed",
                "training_eligible",
                "production_scoring_eligible",
                "remote_pilot_allowed",
            )
            for field in required_false:
                if policy.get(field) is not False:
                    errors.append(f"policy.{field} must remain false")
            if policy.get("shadow_only") is not True:
                errors.append("policy.shadow_only must be true")
            if policy.get("point_time_synthesis_forbidden") is not True:
                errors.append("policy.point_time_synthesis_forbidden must be true")
            if policy.get("core_exact_time_gate_unchanged") is not True:
                errors.append("policy.core_exact_time_gate_unchanged must be true")
            if policy.get("feature_cutoff_rule") != "feature_cutoff_at<=interval_start":
                errors.append("policy.feature_cutoff_rule must be feature_cutoff_at<=interval_start")
            if policy.get("interval_semantics") != "[start,end)":
                errors.append("policy.interval_semantics must be [start,end)")

        label_sources = manifest.get("label_sources")
        if not isinstance(label_sources, list) or not label_sources:
            errors.append("label_sources must be a non-empty list")
        else:
            for index, source in enumerate(label_sources):
                prefix = f"label_sources[{index}]"
                if not isinstance(source, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                if not str(source.get("source_key") or "").strip():
                    errors.append(f"{prefix}.source_key is required")
                if source.get("role") != "shadow":
                    errors.append(f"{prefix}.role must be shadow")
                if source.get("precision") not in {"day", "interval"}:
                    errors.append(f"{prefix}.precision must be day or interval")
                for field in ("training_eligible", "production_scoring_eligible"):
                    if source.get(field) is not False:
                        errors.append(f"{prefix}.{field} must remain false")

        feature_sources = manifest.get("feature_sources")
        if not isinstance(feature_sources, list) or not feature_sources:
            errors.append("feature_sources must be a non-empty list")
        else:
            for index, source in enumerate(feature_sources):
                if not isinstance(source, dict):
                    errors.append(f"feature_sources[{index}] must be an object")
                elif source.get("station_file_required") is not False:
                    errors.append(f"feature_sources[{index}].station_file_required must be false")

        approval_decisions = manifest.get("approval_decisions")
        if not isinstance(approval_decisions, dict) or set(approval_decisions) != REQUIRED_DECISIONS:
            errors.append("approval_decisions must contain exactly the six required decision fields")
        else:
            for field, value in approval_decisions.items():
                if value not in {"PENDING", "APPROVED", "REJECTED"}:
                    errors.append(f"approval_decisions.{field} must be PENDING, APPROVED, or REJECTED")
                if approved and value != "APPROVED":
                    errors.append(f"approval_decisions.{field} must be APPROVED for an approved shadow scope")

        bindings = manifest.get("snapshot_bindings")
        if not isinstance(bindings, list) or not bindings:
            errors.append("snapshot_bindings must be a non-empty list")
        else:
            for index, binding in enumerate(bindings):
                prefix = f"snapshot_bindings[{index}]"
                if not isinstance(binding, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                path = _repo_path(binding.get("path"), f"{prefix}.path", errors)
                declared = binding.get("sha256")
                if approved:
                    actual = _sha256(path)
                    if actual is None:
                        errors.append(f"{prefix}.path does not resolve to a file")
                    if not isinstance(declared, str) or not SHA256_PATTERN.fullmatch(declared):
                        errors.append(f"{prefix}.sha256 must be a 64-character SHA-256 digest")
                    elif actual is not None and actual.lower() != declared.lower():
                        errors.append(f"{prefix}.sha256 does not match the bound file")
                elif declared not in (None, ""):
                    actual = _sha256(path)
                    if actual is None or not isinstance(declared, str) or actual.lower() != declared.lower():
                        errors.append(f"{prefix}.sha256 does not match the bound file")

        approvers = manifest.get("approved_by")
        approver_records = [item for item in approvers if isinstance(item, dict)] if isinstance(approvers, list) else []
        roles = {str(item.get("role") or "").strip() for item in approver_records}
        if not roles & SCIENTIST_ROLES:
            errors.append("approved_by requires a scientist or data_owner role")
        if not roles & CUSTOMER_ROLES:
            errors.append("approved_by requires a customer or product_owner role")
        if approved:
            if not any(str(item.get("role") or "").strip() in SCIENTIST_ROLES and _has_identity(item) for item in approver_records):
                errors.append("approved_by requires an attributable scientist or data_owner")
            if not any(str(item.get("role") or "").strip() in CUSTOMER_ROLES and _has_identity(item) for item in approver_records):
                errors.append("approved_by requires an attributable customer or product_owner")
            _check_approval_time(manifest.get("approved_at"), errors)
            if not str(manifest.get("scope_change_reference") or "").strip():
                errors.append("scope_change_reference is required for an approved shadow scope")
        elif manifest.get("approved_at") not in (None, ""):
            errors.append("approved_at must remain null while the decision is PENDING")

    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_path": str(resolved_manifest),
        "decision": decision,
        "passed": approved and not errors,
        "structurally_valid": manifest is not None and not errors,
        "approval_required": decision == "PENDING",
        "shadow_only": True,
        "core_exact_time_gate_unchanged": True,
        "errors": sorted(set(errors)),
        "proof_boundary": "Local contract validation only; this does not authorize exact-time core training, production scoring, remote pilots, or customer claims.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    report = validate_shadow_scope_approval(args.manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
