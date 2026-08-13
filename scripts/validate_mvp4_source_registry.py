#!/usr/bin/env python3
"""Validate the evidence-only MVP4 source registry.

The registry is a review ledger, not a training authority.  This validator
checks that source roles, review states, licence states, occurrence-time
claims, overlap states, and promotion flags cannot contradict that boundary.
It does not grant rights, prove source independence, or authorize training.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


EXPECTED_SCHEMA_VERSION = "mvp4_source_manifest_registry_v1"
EXPECTED_STATUS = "evidence_only_not_training_authority"
EXPECTED_CORE_CONTRACT = "exact_time_core_v1"
VALID_ROLES = {"requested_core", "core", "shadow", "benchmark", "context"}
VALID_REVIEW_STATES = {
    "requested",
    "pending_review",
    "reviewed",
    "approved",
    "rejected_from_core",
    "access_restricted",
}
VALID_LICENSE_STATES = {
    "permissive_core_reviewed",
    "permissive_shadow_reviewed",
    "pending_review",
    "pending_rights_review",
    "research_only",
    "access_restricted",
    "unknown",
}
VALID_OVERLAP_STATES = {"not_started", "pending", "reviewed", "clean", "overlap_found"}
REVIEWED_LICENSE_STATES = {"permissive_core_reviewed", "permissive_shadow_reviewed", "research_only"}
PENDING_LICENSE_STATES = {"pending_review", "pending_rights_review", "unknown", "access_restricted"}
REQUIRED_NO_GO_TERMS = {
    "two independent approved exact-time positive sources",
    "three positive snow seasons for the selected region",
    "reviewed license and attribution terms",
    "clean source overlap report",
    "exact row snapshot and reproducible split evidence",
}


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _required_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def validate_source_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return a machine-readable validation report for one registry object."""
    errors: list[str] = []
    sources = registry.get("sources") if isinstance(registry, Mapping) else None

    if registry.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append("registry schema_version must be mvp4_source_manifest_registry_v1")
    if registry.get("registry_status") != EXPECTED_STATUS:
        errors.append("registry_status must remain evidence_only_not_training_authority")
    if registry.get("strict_core_contract") != EXPECTED_CORE_CONTRACT:
        errors.append("strict_core_contract must remain exact_time_core_v1")
    no_go_until = registry.get("no_go_until")
    if not isinstance(no_go_until, list) or not all(_is_nonempty_string(item) for item in no_go_until):
        errors.append("no_go_until must be a non-empty list of strings")
        no_go_terms: set[str] = set()
    else:
        no_go_terms = {item.strip() for item in no_go_until}
        for required in sorted(REQUIRED_NO_GO_TERMS - no_go_terms):
            errors.append(f"no_go_until is missing required gate: {required}")

    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
        sources = []

    seen_source_ids: set[str] = set()
    source_reports: list[dict[str, Any]] = []
    for index, source_value in enumerate(sources):
        path = f"sources[{index}]"
        source = _required_object(source_value, path, errors)
        source_id = source.get("source_id")
        if not _is_nonempty_string(source_id):
            errors.append(f"{path}.source_id must be a non-empty string")
            source_id = f"<index:{index}>"
        elif source_id in seen_source_ids:
            errors.append(f"{path}.source_id is duplicated: {source_id}")
        else:
            seen_source_ids.add(source_id)

        role = source.get("source_role")
        if role not in VALID_ROLES:
            errors.append(f"{path}.source_role is invalid: {role!r}")
        review_status = source.get("review_status")
        if review_status not in VALID_REVIEW_STATES:
            errors.append(f"{path}.review_status is invalid: {review_status!r}")

        license_data = _required_object(source.get("license"), f"{path}.license", errors)
        license_status = license_data.get("status")
        if license_status not in VALID_LICENSE_STATES:
            errors.append(f"{path}.license.status is invalid: {license_status!r}")
        if not _is_nonempty_string(license_data.get("reuse_scope")):
            errors.append(f"{path}.license.reuse_scope must be a non-empty string")
        if not isinstance(license_data.get("attribution_required"), bool):
            errors.append(f"{path}.license.attribution_required must be boolean")

        training_eligible = source.get("training_eligible")
        production_eligible = source.get("production_scoring_eligible")
        if training_eligible is not False:
            errors.append(f"{path}.training_eligible must be false in the evidence-only registry")
        if production_eligible is not False:
            errors.append(f"{path}.production_scoring_eligible must be false in the evidence-only registry")

        if review_status == "approved" and license_status in PENDING_LICENSE_STATES:
            errors.append(f"{path} cannot be approved while licence status is {license_status}")
        if role == "core":
            if review_status != "approved":
                errors.append(f"{path} core role requires review_status=approved")
            if license_status != "permissive_core_reviewed":
                errors.append(f"{path} core role requires permissive_core_reviewed licence status")
        if role == "requested_core" and review_status not in {"requested", "pending_review"}:
            errors.append(f"{path} requested_core role requires requested or pending_review status")
        if license_status == "research_only" and role == "core":
            errors.append(f"{path} research_only source cannot have core role")
        if license_status in REVIEWED_LICENSE_STATES and not _is_nonempty_string(source.get("license_review_id")):
            errors.append(f"{path} reviewed licence state requires license_review_id")

        time_semantics = _required_object(source.get("time_semantics"), f"{path}.time_semantics", errors)
        if not _is_nonempty_string(time_semantics.get("event_time_field")):
            errors.append(f"{path}.time_semantics.event_time_field must be a non-empty string")
        for field in ("release_time_proven", "source_time_is_avalanche_occurrence_time"):
            if not isinstance(time_semantics.get(field), bool):
                errors.append(f"{path}.time_semantics.{field} must be boolean")
        if time_semantics.get("source_time_is_avalanche_occurrence_time") is True and role != "core":
            errors.append(f"{path} occurrence-time claim requires an explicit core role review")

        independence = _required_object(source.get("independence"), f"{path}.independence", errors)
        if not _is_nonempty_string(independence.get("origin_source_family")):
            errors.append(f"{path}.independence.origin_source_family must be a non-empty string")
        if not isinstance(independence.get("independent_of_source_ids"), list):
            errors.append(f"{path}.independence.independent_of_source_ids must be a list")
        if independence.get("overlap_review_status") not in VALID_OVERLAP_STATES:
            errors.append(
                f"{path}.independence.overlap_review_status is invalid: "
                f"{independence.get('overlap_review_status')!r}"
            )

        evidence_refs = source.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(
            _is_nonempty_string(item) for item in evidence_refs
        ):
            errors.append(f"{path}.evidence_refs must be a non-empty list of strings")
        if not _is_nonempty_string(source.get("required_next_action")):
            errors.append(f"{path}.required_next_action must be a non-empty string")

        source_reports.append(
            {
                "source_id": source_id,
                "source_role": role,
                "review_status": review_status,
                "license_status": license_status,
                "training_eligible": training_eligible,
                "production_scoring_eligible": production_eligible,
                "overlap_review_status": independence.get("overlap_review_status"),
            }
        )

    return {
        "passed": not errors,
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "registry_status": registry.get("registry_status"),
        "source_count": len(sources),
        "non_promoting_registry": all(
            report["training_eligible"] is False and report["production_scoring_eligible"] is False
            for report in source_reports
        ),
        "sources": source_reports,
        "errors": errors,
    }


def validate_source_registry_file(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path).expanduser()
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "source_count": 0,
            "non_promoting_registry": False,
            "sources": [],
            "errors": [f"could not read source registry: {exc}"],
        }
    if not isinstance(registry, dict):
        return {
            "passed": False,
            "source_count": 0,
            "non_promoting_registry": False,
            "sources": [],
            "errors": ["source registry root must be an object"],
        }
    return validate_source_registry(registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "registry",
        nargs="?",
        type=Path,
        default=Path("docs/MVP4/03_ml_evidence/source_manifest_registry.json"),
    )
    args = parser.parse_args(argv)
    report = validate_source_registry_file(args.registry)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
