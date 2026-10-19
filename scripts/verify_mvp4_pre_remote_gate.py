#!/usr/bin/env python3
"""Fail-closed local gate before an MVP4 Nepal remote pilot.

This gate composes the already-authoritative scope, source-owner intake, and
metadata-only preflight checks.  It is read-only: it never trains, uploads,
pushes, changes a repository variable, or mutates a remote service.

Exit codes:
  0  every pre-remote condition passed
  2  expected fail-closed block or invalid evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATE_VERSION = "mvp4_pre_remote_gate_v1"
APPROVAL_SCHEMA_VERSION = "mvp4_pre_remote_approval_v1"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
SCIENTIST_ROLES = {"scientist", "data_owner"}
CUSTOMER_ROLES = {"customer", "product_owner"}


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str, blockers: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        blockers.append(f"{label} does not resolve to a file: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        blockers.append(f"{label} is not valid JSON: {path} ({exc})")
        return None
    if not isinstance(value, dict):
        blockers.append(f"{label} must be a JSON object: {path}")
        return None
    return value


def _path_matches(declared: Any, actual: Path) -> bool:
    if not isinstance(declared, str) or not declared.strip():
        return False
    try:
        declared_path = Path(declared).expanduser()
        if not declared_path.is_absolute():
            declared_path = ROOT / declared_path
        return declared_path.resolve() == actual.expanduser().resolve()
    except OSError:
        return False


def _repo_input_path(value: Path, label: str, blockers: list[str]) -> Path:
    """Resolve an evidence input relative to the checkout and reject escape."""

    candidate = value.expanduser()
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        blockers.append(f"{label} must resolve under the repository root")
        # Keep the rest of the report deterministic without reading the
        # caller-supplied path after it has failed the containment check.
        return ROOT / "__mvp4_invalid_input__"
    return resolved


def _check_hash(
    path: Path,
    declared: Any,
    label: str,
    blockers: list[str],
) -> str | None:
    actual = _sha256(path)
    if actual is None:
        blockers.append(f"{label} cannot be hashed because the file is missing: {path}")
        return None
    if not isinstance(declared, str) or not SHA256_PATTERN.fullmatch(declared):
        blockers.append(f"{label} must declare a 64-character SHA-256 digest")
    elif actual.lower() != declared.lower():
        blockers.append(f"{label} hash does not match the supplied file: {path}")
    return actual


def _validate_approval(
    *,
    scope_path: Path,
    scope: dict[str, Any] | None,
    approval_path: Path,
    snapshot_path: Path,
    snapshot: dict[str, Any] | None,
    selected_region_keys: list[str],
    blockers: list[str],
) -> dict[str, Any]:
    approval = _load_json(approval_path, "approval manifest", blockers)
    report: dict[str, Any] = {
        "path": str(approval_path),
        "passed": False,
        "scope_manifest_sha256": _sha256(scope_path),
        "snapshot_manifest_sha256": _sha256(snapshot_path),
    }
    if scope is None or snapshot is None or approval is None:
        return report

    if approval.get("schema_version") != APPROVAL_SCHEMA_VERSION:
        blockers.append(f"approval manifest schema_version must be {APPROVAL_SCHEMA_VERSION}")
    if approval.get("decision") != "GO":
        blockers.append("approval manifest decision must be GO")
    if not _path_matches(approval.get("scope_manifest_path"), scope_path):
        blockers.append("approval manifest scope path does not match the selected scope manifest")
    if not _path_matches(approval.get("snapshot_manifest_path"), snapshot_path):
        blockers.append("approval manifest snapshot path does not match the selected snapshot manifest")
    _check_hash(scope_path, approval.get("scope_manifest_sha256"), "scope manifest hash", blockers)
    _check_hash(snapshot_path, approval.get("snapshot_manifest_sha256"), "snapshot manifest hash", blockers)
    if approval.get("approved_candidate_selection_hash") != scope.get("selection_hash"):
        blockers.append("approval manifest selection hash does not match the scope manifest")

    approved_regions = approval.get("selected_region_keys")
    if not isinstance(approved_regions, list) or sorted(str(v) for v in approved_regions) != sorted(selected_region_keys):
        blockers.append("approval manifest selected_region_keys do not match the requested pilot regions")

    approvers = approval.get("approved_by")
    approver_records = [item for item in approvers if isinstance(item, dict)] if isinstance(approvers, list) else []
    roles = {
        str(item.get("role")).strip()
        for item in approver_records
        if isinstance(item.get("role"), str)
    }
    if not roles & SCIENTIST_ROLES:
        blockers.append("approval manifest requires a scientist or data_owner approver")
    elif not any(
        str(item.get("name") or item.get("approval_ref") or "").strip()
        and str(item.get("role") or "").strip() in SCIENTIST_ROLES
        for item in approver_records
    ):
        blockers.append(
            "approval manifest requires a scientist or data_owner with a non-empty name or approval_ref"
        )
    if not roles & CUSTOMER_ROLES:
        blockers.append("approval manifest requires a customer or product_owner approver")
    elif not any(
        str(item.get("name") or item.get("approval_ref") or "").strip()
        and str(item.get("role") or "").strip() in CUSTOMER_ROLES
        for item in approver_records
    ):
        blockers.append(
            "approval manifest requires a customer or product_owner with a non-empty name or approval_ref"
        )

    approved_at = approval.get("approved_at")
    try:
        parsed = datetime.fromisoformat(str(approved_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError:
        blockers.append("approval manifest approved_at must be timezone-aware ISO-8601")

    if scope.get("release_candidate_ready") is not True:
        blockers.append("scope manifest release_candidate_ready is not true")
    if scope.get("decision") != "GO":
        blockers.append("scope manifest decision is not GO")
    selected_paths = scope.get("selected_paths")
    if not isinstance(selected_paths, list) or not selected_paths:
        blockers.append("scope manifest has no approved selected_paths")

    if snapshot.get("training_eligible") is not True:
        blockers.append("snapshot manifest training_eligible is not true")
    if snapshot.get("production_scoring_eligible") is not False:
        blockers.append("snapshot manifest production_scoring_eligible must remain false")
    if snapshot.get("label_time_contract") != "exact_time_core_v1":
        blockers.append("snapshot manifest does not declare exact_time_core_v1")

    report["passed"] = not blockers
    report["roles"] = sorted(roles)
    return report


def _run_json_gate(command: list[str], label: str, blockers: list[str]) -> dict[str, Any] | None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        blockers.append(
            f"{label} did not produce a JSON report (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout[-400:].strip()}"
        )
        return None
    if result.returncode != 0 or report.get("passed") is not True:
        blockers.append(f"{label} did not pass (exit {result.returncode})")
    return report


def _validate_attestation(
    attestation: dict[str, Any],
    shadow_bundle_report: dict[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    """Validate a release attestation against live verifier output.

    Checks:
    - attestation_schema_version is the expected version
    - status is shadow_only
    - training_eligible is False
    - production_eligible is False
    - bundle_sha256 matches the verifier report's bundle_sha256
    - preflight_report_sha256 is present (not None)
    - dependency_lock_sha256 is present (not None)
    - source_commit is present and not "unknown"
    - attestation_sha256 is present and matches recomputed hash
    """
    import hashlib as _hashlib

    expected_schema = "mvp4_shadow_release_attestation_v1"
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            blockers.append(f"attestation check failed: {name} — {detail}")

    # Schema version
    check(
        "attestation_schema_version",
        attestation.get("attestation_schema_version") == expected_schema,
        f"expected={expected_schema}, got={attestation.get('attestation_schema_version')}",
    )

    # Status
    check(
        "status_is_shadow_only",
        attestation.get("status") == "shadow_only",
        f"got={attestation.get('status')}",
    )

    # Training eligibility
    check(
        "training_eligible_false",
        attestation.get("training_eligible") is False,
        f"got={attestation.get('training_eligible')}",
    )

    # Production eligibility
    check(
        "production_eligible_false",
        attestation.get("production_eligible") is False,
        f"got={attestation.get('production_eligible')}",
    )

    # Bundle hash matches verifier report
    att_bundle_hash = attestation.get("bundle_sha256")
    if shadow_bundle_report is not None:
        verifier_bundle_hash = shadow_bundle_report.get("bundle_sha256")
        check(
            "bundle_sha256_matches_verifier",
            att_bundle_hash == verifier_bundle_hash,
            f"attestation={str(att_bundle_hash)[:16]}, verifier={str(verifier_bundle_hash)[:16]}",
        )
    else:
        check(
            "bundle_sha256_matches_verifier",
            False,
            "shadow bundle verifier report is None; cannot compare",
        )

    # Preflight report hash is present
    check(
        "preflight_report_sha256_present",
        attestation.get("preflight_report_sha256") is not None,
        f"got={attestation.get('preflight_report_sha256')}",
    )

    # Dependency lock hash is present
    check(
        "dependency_lock_sha256_present",
        attestation.get("dependency_lock_sha256") is not None,
        f"got={attestation.get('dependency_lock_sha256')}",
    )

    # Source commit is present and not "unknown"
    source_commit = attestation.get("source_commit")
    check(
        "source_commit_valid",
        source_commit is not None and source_commit != "unknown",
        f"got={source_commit}",
    )

    # Attestation hash matches recomputed hash
    stored_hash = attestation.get("attestation_sha256")
    recomputed_bytes = json.dumps(
        {k: v for k, v in attestation.items() if k != "attestation_sha256"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    recomputed_hash = _hashlib.sha256(recomputed_bytes).hexdigest()
    check(
        "attestation_sha256_matches_recomputed",
        stored_hash == recomputed_hash,
        f"stored={str(stored_hash)[:16]}, recomputed={recomputed_hash[:16]}",
    )

    return {
        "checks": checks,
        "all_passed": all(c["passed"] for c in checks),
        "attestation_sha256": stored_hash,
    }


def evaluate_pre_remote_gate(
    *,
    scope_manifest: Path,
    approval_manifest: Path,
    snapshot_manifest: Path,
    artifact_root: Path,
    source_request_manifest: Path,
    source_request_payload: Path,
    source_request_events: Path,
    selected_region_keys: list[str],
    shadow_bundle_dir: Path | None = None,
    attestation_path: Path | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    scope_manifest = _repo_input_path(scope_manifest, "scope manifest", blockers)
    approval_manifest = _repo_input_path(approval_manifest, "approval manifest", blockers)
    snapshot_manifest = _repo_input_path(snapshot_manifest, "snapshot manifest", blockers)
    artifact_root = _repo_input_path(artifact_root, "artifact root", blockers)
    source_request_manifest = _repo_input_path(
        source_request_manifest,
        "source-owner manifest",
        blockers,
    )
    source_request_payload = _repo_input_path(
        source_request_payload,
        "source-owner payload",
        blockers,
    )
    source_request_events = _repo_input_path(
        source_request_events,
        "source-owner events JSONL",
        blockers,
    )
    scope = _load_json(scope_manifest, "scope manifest", blockers)
    snapshot = _load_json(snapshot_manifest, "snapshot manifest", blockers)
    approval_report = _validate_approval(
        scope_path=scope_manifest,
        scope=scope,
        approval_path=approval_manifest,
        snapshot_path=snapshot_manifest,
        snapshot=snapshot,
        selected_region_keys=selected_region_keys,
        blockers=blockers,
    )

    source_report: dict[str, Any] | None = None
    if not source_request_manifest.is_file():
        blockers.append(f"source-owner manifest does not resolve to a file: {source_request_manifest}")
    elif not source_request_payload.is_file():
        blockers.append(f"source-owner payload does not resolve to a file: {source_request_payload}")
    elif not source_request_events.is_file():
        blockers.append(f"source-owner events JSONL does not resolve to a file: {source_request_events}")
    else:
        source_report = _run_json_gate(
            [
                sys.executable,
                str(ROOT / "backend/scripts/validate_mvp4_source_manifest.py"),
                "--manifest",
                str(source_request_manifest),
                "--payload",
                str(source_request_payload),
                "--events-jsonl",
                str(source_request_events),
            ],
            "source-owner intake",
            blockers,
        )

    # Shadow-bundle verifier: if a shadow bundle directory is provided,
    # run the real bundle verifier before the metadata-only preflight.
    # This gate fails closed: any non-zero exit blocks the remote pilot.
    # Exit 0 = structural pass + training blocked (expected for shadow)
    # Exit 1 = structural failure (tamper, hash mismatch, coverage gap)
    # Exit 2 = safety violation (training eligibility incorrectly enabled)
    #
    # ADVISOR FIX: The shadow bundle is MANDATORY on the pre-remote path.
    # If shadow_bundle_dir is None or empty, the gate blocks fail-closed.
    # This prevents bypassing the verifier by simply omitting the argument.
    shadow_bundle_report: dict[str, Any] | None = None
    if shadow_bundle_dir is None:
        blockers.append(
            "shadow-bundle directory is required on the pre-remote path; "
            "omit --shadow-bundle-dir only in explicit dev override mode"
        )
    elif str(shadow_bundle_dir).strip() == "" or str(shadow_bundle_dir) == ".":
        blockers.append(
            "shadow-bundle directory path is empty; a valid artifact directory is required"
        )
    else:
        shadow_bundle_dir = _repo_input_path(shadow_bundle_dir, "shadow bundle dir", blockers)
        if shadow_bundle_dir is not None and shadow_bundle_dir.is_dir():
            shadow_command = [
                sys.executable,
                "-m",
                "backend.scripts.preflight_shadow_nepal",
                str(shadow_bundle_dir),
                "--repo-root",
                str(ROOT),
            ]
            result = subprocess.run(
                shadow_command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            try:
                shadow_bundle_report = json.loads(result.stdout)
            except json.JSONDecodeError:
                blockers.append(
                    f"shadow-bundle verifier did not produce JSON (exit {result.returncode}): "
                    f"{result.stderr.strip() or result.stdout[-400:].strip()}"
                )
                shadow_bundle_report = None
            if shadow_bundle_report is not None:
                shadow_bundle_report["exit_code"] = result.returncode
                # Exit 0 = structural pass + training blocked (expected for shadow)
                if result.returncode != 0:
                    blockers.append(
                        f"shadow-bundle verifier failed with exit code {result.returncode}; "
                        f"expected 0 (structural pass, training blocked)"
                    )
                # Explicitly verify training_blocked is true — a shadow pass
                # must never be interpreted as training approval
                if shadow_bundle_report.get("training_blocked") is not True:
                    blockers.append(
                        "shadow-bundle verifier reports training is NOT blocked; "
                        "shadow pass cannot be interpreted as training approval"
                    )
                # Verify structural_pass is true
                if shadow_bundle_report.get("structural_pass") is not True:
                    blockers.append(
                        "shadow-bundle verifier reports structural_pass is not true"
                    )
                # Verify coverage_pass is true (advisor fix: was missing)
                if shadow_bundle_report.get("coverage_pass") is not True:
                    blockers.append(
                        "shadow-bundle verifier reports coverage_pass is not true"
                    )
                # Verify preflight version matches expected (360 fix: version mismatch)
                expected_preflight_version = "mvp4_shadow_preflight_v3"
                actual_preflight_version = shadow_bundle_report.get("preflight_version", "")
                if actual_preflight_version != expected_preflight_version:
                    blockers.append(
                        f"shadow-bundle verifier preflight version mismatch: "
                        f"expected {expected_preflight_version}, got {actual_preflight_version}"
                    )

    preflight_report: dict[str, Any] | None = None
    if not artifact_root.is_dir():
        blockers.append(f"artifact root does not resolve to a directory: {artifact_root}")
    elif snapshot is not None:
        preflight_command = [
            sys.executable,
            "-m",
            "backend.scripts.audit_training_dataset",
            "--artifact-root",
            str(artifact_root),
            "--snapshot-manifest",
            str(snapshot_manifest),
            "--source-request-manifest",
            str(source_request_manifest),
            "--source-request-payload",
            str(source_request_payload),
            "--source-request-events-jsonl",
            str(source_request_events),
            "--region-keys",
            ",".join(selected_region_keys),
            "--strict",
        ]
        preflight_report = _run_json_gate(preflight_command, "strict Nepal preflight", blockers)

    # ---- Attestation validation (G3: enforce attestation binding) ----
    # The attestation is the external trust anchor. If provided, the gate
    # verifies that it matches the live artifacts — a stale or tampered
    # attestation blocks the gate.
    attestation_report: dict[str, Any] | None = None
    if attestation_path is None:
        blockers.append(
            "attestation path is required on the pre-remote path; "
            "the gate cannot verify release provenance without it"
        )
    elif str(attestation_path).strip() == "" or str(attestation_path) == ".":
        blockers.append(
            "attestation path is empty; a valid tracked attestation JSON is required"
        )
    elif not attestation_path.is_file():
        blockers.append(
            f"attestation file does not resolve to a file: {attestation_path}"
        )
    else:
        try:
            attestation_data = json.loads(attestation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            blockers.append(f"attestation file is not valid JSON: {exc}")
            attestation_data = None
        if attestation_data is not None:
            attestation_report = _validate_attestation(
                attestation_data, shadow_bundle_report, blockers
            )

    unique_blockers = sorted(set(blockers))
    return {
        "gate_version": GATE_VERSION,
        "passed": not unique_blockers,
        "decision": "ready_for_remote_pilot" if not unique_blockers else "blocked_pre_remote_gate",
        "selected_region_keys": selected_region_keys,
        "scope_manifest": str(scope_manifest),
        "approval_manifest": approval_report,
        "source_owner_intake": source_report,
        "shadow_bundle_verifier": shadow_bundle_report,
        "strict_preflight": preflight_report,
        "attestation_validation": attestation_report,
        "blockers": unique_blockers,
        "proof_boundary": "Read-only local evidence gate; it never trains, uploads, pushes, or mutates remote/customer state.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-manifest", type=Path, required=True)
    parser.add_argument("--approval-manifest", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-request-manifest", type=Path, required=True)
    parser.add_argument("--source-request-payload", type=Path, required=True)
    parser.add_argument("--source-request-events-jsonl", type=Path, required=True)
    parser.add_argument("--region-keys", required=True)
    parser.add_argument(
        "--shadow-bundle-dir",
        type=Path,
        default=None,
        help="MANDATORY on the pre-remote path: shadow-bundle artifact directory to verify before preflight. "
             "The gate fails closed if this is omitted or empty.",
    )
    parser.add_argument(
        "--attestation",
        type=Path,
        default=None,
        help="MANDATORY on the pre-remote path: path to the release attestation JSON. "
             "The gate verifies the attestation matches live artifacts.",
    )
    args = parser.parse_args(argv)
    regions = [value.strip() for value in args.region_keys.split(",") if value.strip()]
    if not regions:
        print(json.dumps({"gate_version": GATE_VERSION, "passed": False, "decision": "blocked_pre_remote_gate", "blockers": ["at least one region key is required"]}, indent=2, sort_keys=True))
        return 2
    report = evaluate_pre_remote_gate(
        scope_manifest=args.scope_manifest,
        approval_manifest=args.approval_manifest,
        snapshot_manifest=args.snapshot_manifest,
        artifact_root=args.artifact_root,
        source_request_manifest=args.source_request_manifest,
        source_request_payload=args.source_request_payload,
        source_request_events=args.source_request_events_jsonl,
        selected_region_keys=regions,
        shadow_bundle_dir=args.shadow_bundle_dir,
        attestation_path=args.attestation,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
