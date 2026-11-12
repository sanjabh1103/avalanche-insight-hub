#!/usr/bin/env python3
"""Generate ITU evidence package from a local native SNOWPACK v16 run.

Fail-closed: rejects missing files, stale toolchain paths, unparsed logs.

Two-lane evidence model:
  Lane 1 (hosted-v2): customer-facing, NOT in this package.
  Lane 2 (local-v16): ITU supplementary evidence, local Docker, local-unapproved.

Outputs to artifacts/itu_deadline_proof/:
  - proof-summary.json, artifact-inventory.json, runtime.txt
  - repeatability-report.json, ITU_EVIDENCE_CARD.md
  - proof-card.md, proof-card.csv, provenance-manifest.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DECISION_RECORD = ROOT / "docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json"
OUT_DIR = ROOT / "artifacts/itu_deadline_proof"

NON_CLAIMS = [
    "no_official_warning", "no_validated_pir_panjal_accuracy",
    "no_scientific_validation", "no_Partner_approval",
    "no_operational_readiness", "no_production_ml_promotion",
]

CLAIM_BOUNDARY = (
    "Retrospective candidate pipeline demonstration on Open-Meteo historical "
    "replay data. Local Docker native SNOWPACK 3.7.0 + MeteoIO 2.11.0 run "
    "with attested toolchain binding. Repeatability verified with exact "
    "SHA-256 matches on 3 of 4 science artifacts; .pro differs only in "
    "timestamp header. This is a pipeline integrity proof, not scientific "
    "validation."
)

EVIDENCE_LANE = "local_v16_docker_native"
EVIDENCE_LANE_DESCRIPTION = (
    "Local Docker native SNOWPACK run; local-unapproved candidate; "
    "not a hosted or cloud run"
)

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
LOG_LEVEL_RE = re.compile(r"\[(?P<level>[EW])\]")
PRO_TIMESTAMP_RE = re.compile(
    rb"^#(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    rb"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?),\s*Snowpack\b.*(?:\r?\n|$)",
    re.MULTILINE,
)
SCIENCE_ARTIFACTS = (
    ("pir-panjal-middle-candidate-34021875-74347536_candidate.smet", "forcing/output SMET"),
    ("pir-panjal-middle-candidate-34021875-74347536_candidate.sno", "snow profile state"),
    ("pir-panjal-middle-candidate-34021875-74347536_candidate.haz", "hazard output"),
    ("pir-panjal-middle-candidate-34021875-74347536_candidate.pro", "profile output"),
)
PACKAGE_FILES = (
    "proof-summary.json",
    "artifact-inventory.json",
    "runtime.txt",
    "repeatability-report.json",
    "ITU_EVIDENCE_CARD.md",
    "proof-card.md",
    "proof-card.csv",
    "provenance-manifest.json",
)


class EvidencePackageError(ValueError):
    """Raised when the evidence contract cannot be proven."""


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head(cwd: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        text=True,
        cwd=cwd,
    ).strip()


def git_worktree_dirty(cwd: Path) -> bool:
    r = subprocess.run(["git", "status", "--short"], text=True, cwd=cwd, capture_output=True)
    return len(r.stdout.strip()) > 0


def validate_commit_sha(value: str, label: str, cwd: Path = ROOT) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise EvidencePackageError(f"{label} must be a full Git commit SHA")
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{value}^{{commit}}"],
        text=True,
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise EvidencePackageError(f"{label} is not present as a commit: {value}")
    return value.lower()


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidencePackageError(f"invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise EvidencePackageError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_source_attestation(path: Path, expected_sha: str | None = None) -> dict[str, Any]:
    attestation = read_json_object(path)
    if attestation.get("schema_version") != "itu_run_source_attestation_v1":
        raise EvidencePackageError(f"unsupported source attestation schema: {path}")
    if attestation.get("captured_before_native_execution") is not True:
        raise EvidencePackageError(f"source attestation was not captured before execution: {path}")
    if attestation.get("capture_method") != "runner_preflight_git_identity":
        raise EvidencePackageError(f"untrusted source attestation method: {path}")
    source_sha = validate_commit_sha(
        str(attestation.get("run_source_sha") or ""),
        "run_source_sha",
    )
    if expected_sha and source_sha != expected_sha.lower():
        raise EvidencePackageError(
            f"run source SHA mismatch: attestation={source_sha}, declared={expected_sha}"
        )
    if attestation.get("worktree_dirty_at_capture") is not False:
        raise EvidencePackageError("native run source worktree was dirty at capture")
    return attestation


def parse_runtime_log(log_path: Path) -> dict[str, Any]:
    if not log_path or not log_path.exists():
        return {"errors": [], "warnings": [], "error_count": 0, "warning_count": 0, "log_exists": False}
    text = log_path.read_text(errors="replace")
    errors = [l for l in text.splitlines() if any(m.group("level") == "E" for m in LOG_LEVEL_RE.finditer(l))]
    warnings = [l for l in text.splitlines() if any(m.group("level") == "W" for m in LOG_LEVEL_RE.finditer(l))]
    return {"errors": errors, "warnings": warnings, "error_count": len(errors),
            "warning_count": len(warnings), "log_exists": True}


def recursive_inventory(directory: Path, base: Path) -> list[dict[str, Any]]:
    artifacts = []
    if not directory.exists():
        return artifacts
    for p in sorted(directory.rglob("*")):
        if p.is_symlink():
            raise EvidencePackageError(f"symlinked run artifact is not allowed: {p}")
        if p.is_file():
            artifacts.append({"relative_path": str(p.relative_to(base)),
                              "sha256": sha256_file(p), "size_bytes": p.stat().st_size})
    return artifacts


def find_log_file(run_dir: Path) -> Path | None:
    logs = sorted(run_dir.glob("*.log"))
    if len(logs) > 1:
        raise EvidencePackageError(f"multiple runtime logs found in {run_dir}")
    return logs[0] if logs else None


def _normalized_version(value: Any) -> str:
    return " ".join(str(value or "").split())


def validate_toolchain_manifest(
    path: Path,
    native_execution: dict[str, Any],
) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Toolchain manifest not found: {path}")
    manifest = read_json_object(path)
    path_str = str(path)
    if "v15" in path_str and "v16" not in path_str:
        raise ValueError(f"Stale v15 toolchain manifest path rejected: {path}")
    runtime_path = str(native_execution.get("toolchain_manifest_path") or "")
    if "v15" in runtime_path and "v16" not in runtime_path:
        raise ValueError(f"Native execution references stale v15 toolchain path: {runtime_path}")
    if runtime_path and Path(runtime_path).name != path.name:
        raise ValueError(
            "Native execution toolchain manifest basename does not match the supplied manifest"
        )
    required = ["binary_sha256", "binary_version", "image_id", "image_archive_sha256"]
    missing = [f for f in required if f not in manifest]
    if missing:
        raise ValueError(f"Toolchain manifest missing fields: {missing}")
    comparisons = {
        "binary_sha256": (manifest.get("binary_sha256"), native_execution.get("binary_sha256")),
        "binary_version": (
            _normalized_version(manifest.get("binary_version")),
            _normalized_version(native_execution.get("binary_version")),
        ),
        "image_id": (manifest.get("image_id"), native_execution.get("image_id")),
        "image_archive_sha256": (
            manifest.get("image_archive_sha256"),
            native_execution.get("image_archive_sha256"),
        ),
    }
    mismatches = {
        field: {"manifest": expected, "native_execution": observed}
        for field, (expected, observed) in comparisons.items()
        if expected != observed
    }
    if mismatches:
        raise ValueError(f"Toolchain/native execution mismatch: {mismatches}")
    manifest_hash = sha256_file(path)
    declared_manifest_hash = native_execution.get("toolchain_manifest_sha256")
    if declared_manifest_hash and declared_manifest_hash != manifest_hash:
        raise ValueError(
            "Native execution toolchain manifest SHA does not match the supplied manifest"
        )
    embedded = native_execution.get("toolchain_manifest")
    if isinstance(embedded, dict):
        embedded_mismatches = {
            field: {"file": manifest.get(field), "embedded": embedded.get(field)}
            for field in required
            if manifest.get(field) != embedded.get(field)
        }
        if embedded_mismatches:
            raise ValueError(f"Embedded toolchain manifest mismatch: {embedded_mismatches}")
    return manifest


def normalize_pro_bytes(data: bytes) -> tuple[bytes, str]:
    matches = list(PRO_TIMESTAMP_RE.finditer(data))
    if len(matches) != 1:
        raise EvidencePackageError(
            f"expected exactly one SNOWPACK timestamp header, found {len(matches)}"
        )
    match = matches[0]
    normalized = data[:match.start()] + data[match.end():]
    return normalized, match.group("timestamp").decode("ascii")


def compare_pro_files(first: Path, second: Path) -> dict[str, Any]:
    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    first_hash = hashlib.sha256(first_bytes).hexdigest()
    second_hash = hashlib.sha256(second_bytes).hexdigest()
    if first_bytes == second_bytes:
        return {
            "exact_match": True,
            "physics_content_identical": True,
            "normalized_match": True,
            "normalization": "none; byte-identical",
            "normalized_sha256": hashlib.sha256(first_bytes).hexdigest(),
            "first_timestamp": None,
            "second_timestamp": None,
            "note": "byte-identical",
            "v16_sha256": first_hash,
            "repeat_sha256": second_hash,
        }
    try:
        first_normalized, first_timestamp = normalize_pro_bytes(first_bytes)
        second_normalized, second_timestamp = normalize_pro_bytes(second_bytes)
    except EvidencePackageError as exc:
        return {
            "exact_match": False,
            "physics_content_identical": False,
            "normalized_match": False,
            "normalization": "failed",
            "normalized_sha256": None,
            "first_timestamp": None,
            "second_timestamp": None,
            "note": str(exc),
            "v16_sha256": first_hash,
            "repeat_sha256": second_hash,
        }
    normalized_match = first_normalized == second_normalized
    return {
        "exact_match": False,
        "physics_content_identical": normalized_match,
        "normalized_match": normalized_match,
        "normalization": "removed exactly one SNOWPACK timestamp header line",
        "normalized_sha256": hashlib.sha256(first_normalized).hexdigest()
        if normalized_match
        else None,
        "first_timestamp": first_timestamp,
        "second_timestamp": second_timestamp,
        "note": (
            "differs only in one timestamp header line; normalized profile content identical"
            if normalized_match
            else "normalized profile content differs"
        ),
        "v16_sha256": first_hash,
        "repeat_sha256": second_hash,
    }


def recompute_repeatability(run_dir: Path, repeat_dir: Path) -> dict[str, Any]:
    comparisons = []
    exact = 0
    missing_artifacts: list[str] = []
    pro_comparison: dict[str, Any] | None = None
    for fname, desc in SCIENCE_ARTIFACTS:
        f1, f2 = run_dir / fname, repeat_dir / fname
        if not f1.exists() or not f2.exists():
            missing_artifacts.append(fname)
            comparisons.append({"artifact": fname, "description": desc,
                "v16_sha256": sha256_file(f1) if f1.exists() else "MISSING",
                "repeat_sha256": sha256_file(f2) if f2.exists() else "MISSING",
                "exact_match": False, "note": "file missing"})
            continue
        if fname.endswith(".pro"):
            pro_comparison = compare_pro_files(f1, f2)
            comparison = {
                "artifact": fname,
                "description": desc,
                **pro_comparison,
            }
            match = bool(pro_comparison["exact_match"])
        else:
            h1, h2 = sha256_file(f1), sha256_file(f2)
            match = h1 == h2
            comparison = {"artifact": fname, "description": desc,
                          "v16_sha256": h1, "repeat_sha256": h2,
                          "exact_match": match, "note": "byte-identical" if match else "byte content differs",
                          "physics_content_identical": match}
        if match:
            exact += 1
        comparisons.append(comparison)
    total = len(comparisons)
    if missing_artifacts:
        result = "FAIL_MISSING_ARTIFACTS"
    elif pro_comparison is None:
        result = "FAIL_PRO_COMPARISON_UNPROVEN"
    elif pro_comparison["physics_content_identical"]:
        result = f"EXACT_MATCH_{exact}_OF_{total}_ARTIFACTS_PLUS_PRO_PHYSICS_CONTENT_IDENTICAL"
    else:
        result = f"EXACT_MATCH_{exact}_OF_{total}_ARTIFACTS_PLUS_PRO_PHYSICS_CONTENT_DIFFERENT"
    return {
        "comparisons": comparisons,
        "exact_hash_matches": exact,
        "total_artifacts_compared": total,
        "missing_artifacts": missing_artifacts,
        "pro_physics_content_identical": bool(
            pro_comparison and pro_comparison["physics_content_identical"]
        ),
        "repeatability_result": result,
    }


def relative_repo_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise EvidencePackageError(f"path is outside repository root: {path}") from exc


def package_content_sha256(out_dir: Path) -> str:
    """Hash generated package content without self-referential provenance."""
    digest = hashlib.sha256()
    for name in PACKAGE_FILES:
        if name == "provenance-manifest.json":
            continue
        path = out_dir / name
        if not path.is_file():
            raise EvidencePackageError(f"expected package file is missing: {path}")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_proof_card_csv(path: Path, rows: list[tuple[str, Any]]) -> None:
    """Write the machine-readable proof card with repository-friendly line endings."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["field", "value"])
        writer.writerows(rows)


def proof_card_rows(summary: dict[str, Any]) -> list[tuple[str, Any]]:
    native = summary["native_execution"]
    profile = summary["profile_summary"]
    repeatability = summary["repeatability"]
    source = summary["source"]
    return [
        ("evidence_lane", summary["evidence_lane"]),
        ("run_source_sha", summary["run_source_sha"]),
        ("package_generation_sha", summary["package_generation_sha"]),
        ("run_source_attestation_status", summary["provenance_status"]["run_source_sha"]),
        ("decision_record_sha256", summary["decision_record_sha256"]),
        ("run_id", summary["run_id"]),
        ("status", summary["status"]),
        ("evidence_class", summary["evidence_class"]),
        ("native_execution_end_date", native["end_date"]),
        ("runtime_error_count", native["runtime_error_count"]),
        ("runtime_warning_count", native["runtime_warning_count"]),
        ("exit_code", native["exit_code"]),
        ("binary_sha256", native["binary_sha256"]),
        ("image_id", native["image_id"]),
        ("image_archive_sha256", native["image_archive_sha256"]),
        ("forcing_manifest_sha256", summary["forcing_manifest_sha256"]),
        ("case_manifest_sha256", summary["case_manifest_sha256"]),
        ("toolchain_manifest_sha256", summary["toolchain_manifest_sha256"]),
        ("source_id", source["source_id"]),
        ("model_id", source["model_id"]),
        ("sample_count", source["sample_count"]),
        ("source_sample_count", source["source_sample_count"]),
        ("warmup_hours", source["warmup_hours"]),
        ("core_null_count", source["core_null_count"]),
        ("snow_height_m", profile["snow_height_m"]),
        ("layer_count", profile["layer_count"]),
        ("weak_layer_depth_m", profile["weak_layer_depth_m"]),
        ("bulk_density_kgm3", profile["bulk_density_kgm3"]),
        ("snowpack_stability_index", profile["snowpack_stability_index"]),
        ("weak_layer_grain_type", profile["weak_layer_grain_type"]),
        ("weak_layer_shear_strength_kpa", profile["weak_layer_shear_strength_kpa"]),
        ("repeatability_exact_matches", repeatability["exact_hash_matches"]),
        ("repeatability_total_compared", repeatability["total_artifacts_compared"]),
        ("repeatability_result", repeatability["result"]),
        ("pro_physics_content_identical", repeatability["pro_physics_content_identical"]),
        ("license_review_status", summary["license_review_status"]),
        ("scope", summary["scope"]),
    ] + [(f"non_claim_{i}", claim) for i, claim in enumerate(summary["non_claims"], 1)]


def render_proof_card_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Proof Card — Pir Panjal Snowpack POC",
        "",
        f"Generated (UTC): {summary['generated_at']}",
        "",
        "| Field | Value |",
        "|-------|-------|",
    ]
    for field, value in proof_card_rows(summary):
        rendered = str(value).replace("|", "\\|")
        lines.append(f"| {field} | {rendered} |")
    return "\n".join(lines) + "\n"


def repeatability_claim_boundary(repeatability: dict[str, Any]) -> str:
    if repeatability["pro_physics_content_identical"]:
        return (
            f"{repeatability['exact_hash_matches']} of "
            f"{repeatability['total_artifacts_compared']} science artifacts are byte-identical; "
            ".pro differs only after removal of exactly one SNOWPACK timestamp header line."
        )
    return (
        f"{repeatability['exact_hash_matches']} of "
        f"{repeatability['total_artifacts_compared']} science artifacts are byte-identical; "
        ".pro normalized profile content is not identical."
    )


def generate_package(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    repeat_dir = args.repeat_dir.resolve()
    toolchain_path = args.toolchain_manifest.resolve()
    out_dir = args.output_dir.resolve()
    if not run_dir.is_dir():
        raise EvidencePackageError(f"run-dir does not exist: {run_dir}")
    if not repeat_dir.is_dir():
        raise EvidencePackageError(f"repeat-dir does not exist: {repeat_dir}")
    cr_path = run_dir / "candidate-result.json"
    rr_path = repeat_dir / "candidate-result.json"
    if not cr_path.is_file() or not rr_path.is_file():
        raise EvidencePackageError("both run and repeat candidate-result.json files are required")
    cr = read_json_object(cr_path)
    rr = read_json_object(rr_path)
    declared_source_sha = validate_commit_sha(args.run_source_sha, "run_source_sha")
    pkg_gen_sha = validate_commit_sha(git_head(ROOT), "package_generation_sha")
    if git_worktree_dirty(ROOT):
        raise EvidencePackageError(
            "package generation requires a clean source worktree; commit scoped changes first"
        )
    if not DECISION_RECORD.is_file():
        raise EvidencePackageError(f"decision record not found: {DECISION_RECORD}")

    run_attestation_path = run_dir / "input-manifests" / "run-source-attestation.json"
    repeat_attestation_path = repeat_dir / "input-manifests" / "run-source-attestation.json"
    run_attestation = load_source_attestation(run_attestation_path, declared_source_sha)
    repeat_attestation = load_source_attestation(repeat_attestation_path, declared_source_sha)
    if run_attestation["run_source_sha"] != repeat_attestation["run_source_sha"]:
        raise EvidencePackageError("run and repeat source attestations bind different commits")
    for label, result in (("run", cr), ("repeat", rr)):
        if result.get("run_source_sha", "").lower() != declared_source_sha:
            raise EvidencePackageError(f"{label} candidate result does not bind run_source_sha")
    if cr.get("run_id") == rr.get("run_id"):
        raise EvidencePackageError("run and repeat must have distinct run IDs")

    ne = cr.get("native_execution")
    if not isinstance(ne, dict):
        raise EvidencePackageError("candidate result native_execution is missing")
    toolchain_manifest = validate_toolchain_manifest(toolchain_path, ne)
    forcing_sha = str(cr.get("forcing_manifest_sha256") or "")
    case_sha = str(cr.get("case_manifest_sha256") or "")
    if not SHA256_RE.fullmatch(forcing_sha) or not SHA256_RE.fullmatch(case_sha):
        raise EvidencePackageError("candidate result input manifest hashes are invalid")
    forcing_path = run_dir / "input-manifests" / "forcing-manifest.json"
    if not forcing_path.is_file() or sha256_file(forcing_path) != forcing_sha:
        raise EvidencePackageError("copied forcing manifest does not match candidate result hash")
    forcing_manifest = read_json_object(forcing_path)
    log_path = find_log_file(run_dir)
    repeat_log_path = find_log_file(repeat_dir)
    log_analysis = parse_runtime_log(log_path)
    repeat_log_analysis = parse_runtime_log(repeat_log_path)
    if not log_analysis["log_exists"] or not repeat_log_analysis["log_exists"]:
        raise EvidencePackageError("both native runtime logs are required")
    if log_analysis["error_count"] or repeat_log_analysis["error_count"]:
        raise EvidencePackageError(
            f"runtime logs contain errors: run={log_analysis['error_count']}, "
            f"repeat={repeat_log_analysis['error_count']}"
        )

    repeatability = recompute_repeatability(run_dir, repeat_dir)
    if repeatability["missing_artifacts"]:
        raise EvidencePackageError(
            f"repeatability artifacts missing: {repeatability['missing_artifacts']}"
        )
    if not repeatability["pro_physics_content_identical"]:
        raise EvidencePackageError(
            "profile repeatability failed: normalized .pro content differs or timestamp header is unproven"
        )
    repeatability["run_1"] = {
        "run_id": cr.get("run_id"),
        "output_dir": relative_repo_path(run_dir),
        "source_attestation": run_attestation,
    }
    repeatability["run_2"] = {
        "run_id": rr.get("run_id"),
        "output_dir": relative_repo_path(repeat_dir),
        "source_attestation": repeat_attestation,
    }

    run_inv = recursive_inventory(run_dir, ROOT)
    rep_inv = recursive_inventory(repeat_dir, ROOT)
    generated_at = utc_now_iso()
    decision_hash = sha256_file(DECISION_RECORD)
    ps = cr.get("profile_summary", {})
    input_quality = forcing_manifest.get("input_quality", {})
    null_counts = input_quality.get("null_counts", {})
    core_variables = input_quality.get("core_variables", [])
    optional_variables = input_quality.get("optional_variables", [])
    source = {
        "source_id": forcing_manifest.get("source_id"),
        "model_id": forcing_manifest.get("model_id"),
        "forecast_role": forcing_manifest.get("forecast_role"),
        "sample_count": forcing_manifest.get("sample_count"),
        "source_sample_count": forcing_manifest.get("source_sample_count"),
        "warmup_hours": forcing_manifest.get("warmup_hours"),
        "core_null_count": sum(int(null_counts.get(name, 0) or 0) for name in core_variables),
        "optional_null_counts": {
            name: int(null_counts.get(name, 0) or 0) for name in optional_variables
        },
        "resolution": forcing_manifest.get("resolution"),
        "longwave_mapping_status": forcing_manifest.get("longwave_mapping_status", "unavailable"),
        "terrestrial_radiation_treatment": forcing_manifest.get("unit_transforms", {}).get(
            "terrestrial_radiation", "unavailable"
        ),
    }
    claim_boundary = repeatability_claim_boundary(repeatability)
    provenance_status = {
        "run_source_sha": "verified_pre_execution_attestation_on_clean_worktree",
        "package_generation_sha": "verified_committed_head_on_clean_worktree",
    }
    governance = {
        "official_warning_eligible": cr.get("official_warning_eligible"),
        "scientific_validation_eligible": cr.get("scientific_validation_eligible"),
        "publish_eligible": cr.get("publish_eligible"),
        "no_fallback": cr.get("no_fallback", "unavailable"),
        "rf_comparison": cr.get("rf_comparison", {}),
    }
    native = {
        "success": ne.get("success"),
        "exit_code": ne.get("exit_code"),
        "binary_sha256": ne.get("binary_sha256"),
        "binary_version": _normalized_version(ne.get("binary_version")),
        "image_id": ne.get("image_id"),
        "image_archive_sha256": ne.get("image_archive_sha256"),
        "toolchain_manifest_verified": ne.get("toolchain_manifest_verified"),
        "no_fallback": cr.get("no_fallback", "unavailable"),
        "end_date": cr.get("native_execution_end_date"),
        "runtime_error_count": log_analysis["error_count"],
        "runtime_warning_count": log_analysis["warning_count"],
    }
    profile = {
        "snow_height_m": ps.get("snow_height_m"),
        "layer_count": ps.get("layer_count"),
        "weak_layer_depth_m": ps.get("weak_layer_depth_m"),
        "bulk_density_kgm3": ps.get("bulk_density_kgm3"),
        "snowpack_stability_index": ps.get("snowpack_stability_index"),
        "weak_layer_grain_type": ps.get("weak_layer_grain_type"),
        "weak_layer_shear_strength_kpa": ps.get("weak_layer_shear_strength_kpa"),
    }
    proof_summary = {
        "schema_version": "itu_proof_summary_v3",
        "generated_at": generated_at,
        "evidence_lane": EVIDENCE_LANE,
        "evidence_lane_description": EVIDENCE_LANE_DESCRIPTION,
        "run_source_sha": declared_source_sha,
        "package_generation_sha": pkg_gen_sha,
        "provenance_status": provenance_status,
        "decision_record_sha256": decision_hash,
        "run_id": cr.get("run_id"),
        "evidence_class": cr.get("evidence_class"),
        "status": cr.get("status"),
        "scope": "pipeline_integrity_proof_only_not_scientific_validation",
        "native_execution": native,
        "source": source,
        "initial_state": cr.get("initial_state", {}),
        "governance": governance,
        "forcing_manifest_sha256": forcing_sha,
        "case_manifest_sha256": case_sha,
        "toolchain_manifest_sha256": sha256_file(toolchain_path),
        "profile_summary": profile,
        "repeatability": {
            "exact_hash_matches": repeatability["exact_hash_matches"],
            "total_artifacts_compared": repeatability["total_artifacts_compared"],
            "result": repeatability["repeatability_result"],
            "pro_physics_content_identical": repeatability["pro_physics_content_identical"],
            "comparisons": repeatability["comparisons"],
        },
        "non_claims": NON_CLAIMS,
        "claim_boundary": claim_boundary,
        "license_review_status": "pending",
    }
    inventory = {
        "schema_version": "itu_artifact_inventory_v3",
        "generated_at": generated_at,
        "evidence_lane": EVIDENCE_LANE,
        "run_source_sha": declared_source_sha,
        "package_generation_sha": pkg_gen_sha,
        "run_id": cr.get("run_id"),
        "run_dir": relative_repo_path(run_dir),
        "repeat_dir": relative_repo_path(repeat_dir),
        "inventory_scope": "recursive_metadata_and_sha256_only; raw_run_files_remain_internal",
        "run_artifacts": run_inv,
        "repeat_artifacts": rep_inv,
        "total_run_files": len(run_inv),
        "total_repeat_files": len(rep_inv),
    }
    rep_report = {
        "schema_version": "itu_repeatability_report_v3",
        "generated_at": generated_at,
        "run_source_sha": declared_source_sha,
        "package_generation_sha": pkg_gen_sha,
        **repeatability,
        "claim_boundary": claim_boundary,
        "non_claims": NON_CLAIMS,
    }
    provenance = {
        "schema_version": "itu_provenance_manifest_v2",
        "generated_at": generated_at,
        "evidence_lane": EVIDENCE_LANE,
        "evidence_lane_description": EVIDENCE_LANE_DESCRIPTION,
        "run_source_sha": declared_source_sha,
        "package_generation_sha": pkg_gen_sha,
        "sha_mismatch": declared_source_sha != pkg_gen_sha,
        "worktree_dirty_at_generation": False,
        "provenance_status": provenance_status,
        "run_source_attestation": run_attestation,
        "repeat_source_attestation": repeat_attestation,
        "decision_record_sha256": decision_hash,
        "decision_record_path": relative_repo_path(DECISION_RECORD),
        "run_dir": relative_repo_path(run_dir),
        "repeat_dir": relative_repo_path(repeat_dir),
        "toolchain_manifest_path": relative_repo_path(toolchain_path),
        "toolchain_manifest_sha256": sha256_file(toolchain_path),
        "toolchain_binary_sha256": toolchain_manifest.get("binary_sha256"),
        "toolchain_binary_version": _normalized_version(toolchain_manifest.get("binary_version")),
        "runtime_log": {
            "path": relative_repo_path(log_path),
            "error_count": log_analysis["error_count"],
            "warning_count": log_analysis["warning_count"],
            "errors": log_analysis["errors"],
            "warnings": log_analysis["warnings"],
        },
        "repeat_runtime_log": {
            "path": relative_repo_path(repeat_log_path),
            "error_count": repeat_log_analysis["error_count"],
            "warning_count": repeat_log_analysis["warning_count"],
        },
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "os": platform.system(),
            "arch": platform.machine(),
        },
        "candidate_result_sha256": sha256_file(cr_path),
        "repeat_candidate_result_sha256": sha256_file(rr_path),
        "forcing_manifest_sha256": forcing_sha,
        "case_manifest_sha256": case_sha,
        "native_execution": native,
        "native_execution_end_date": cr.get("native_execution_end_date"),
        "source": source,
        "governance": governance,
        "license_review_status": "pending",
        "rights_note": "Open-Meteo raw data and derived artifacts remain internal until owner records rights decision.",
        "non_claims": NON_CLAIMS,
        "claim_boundary": claim_boundary,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    unexpected = sorted({item.name for item in out_dir.iterdir()} - set(PACKAGE_FILES))
    if unexpected:
        raise EvidencePackageError(f"unexpected files in output directory: {unexpected}")
    write_json(out_dir / "proof-summary.json", proof_summary)
    write_json(out_dir / "artifact-inventory.json", inventory)
    write_json(out_dir / "repeatability-report.json", rep_report)
    runtime_lines = [
        "ITU Evidence Package - Runtime Record",
        f"Generated (UTC): {generated_at}",
        f"Evidence lane: {EVIDENCE_LANE}",
        f"Evidence lane description: {EVIDENCE_LANE_DESCRIPTION}",
        f"Run source SHA: {declared_source_sha}",
        f"Package generation SHA: {pkg_gen_sha}",
        "Run source attestation: verified before native execution on clean worktree",
        f"Decision record SHA-256: {decision_hash}",
        "Worktree dirty at generation: False",
        "",
        f"Run ID: {cr.get('run_id')}",
        f"Repeat run ID: {rr.get('run_id')}",
        f"Status: {cr.get('status')}",
        f"Evidence class: {cr.get('evidence_class')}",
        "",
        "Native execution:",
        f"  Binary: {ne.get('binary_path')}",
        f"  Binary SHA-256: {ne.get('binary_sha256')}",
        f"  Binary version: {_normalized_version(ne.get('binary_version'))}",
        f"  Exit code: {ne.get('exit_code')}",
        f"  Image ID: {ne.get('image_id')}",
        f"  Image archive SHA-256: {ne.get('image_archive_sha256')}",
        f"  End date: {cr.get('native_execution_end_date')}",
        f"  Runtime errors [E]: {log_analysis['error_count']}",
        f"  Runtime warnings [W]: {log_analysis['warning_count']}",
        "",
        f"Toolchain manifest SHA-256: {sha256_file(toolchain_path)}",
        f"Forcing manifest SHA-256: {forcing_sha}",
        f"Case manifest SHA-256: {case_sha}",
        "",
        "Source:",
        f"  Source ID: {source['source_id']}",
        f"  Model ID: {source['model_id']}",
        f"  Sample count: {source['sample_count']}",
        f"  Source sample count: {source['source_sample_count']}",
        f"  Warmup hours: {source['warmup_hours']}",
        f"  Core null count: {source['core_null_count']}",
        "",
        "Profile summary:",
        *(f"  {field}: {value}" for field, value in profile.items()),
        "",
        "Repeatability:",
        f"  Exact hash matches: {repeatability['exact_hash_matches']}/{repeatability['total_artifacts_compared']}",
        f"  .pro physics content identical after timestamp normalization: {repeatability['pro_physics_content_identical']}",
        f"  Result: {repeatability['repeatability_result']}",
        "",
        f"Environment Python: {platform.python_version()}",
        f"Environment platform: {platform.platform()}",
        "",
        "Non-claims:",
        *(f"  - {claim}" for claim in NON_CLAIMS),
        "",
        "Scope: pipeline_integrity_proof_only_not_scientific_validation",
        "License review status: pending",
        "Raw run artifacts are not included; artifact-inventory.json is a recursive hash inventory.",
    ]
    (out_dir / "runtime.txt").write_text("\n".join(runtime_lines) + "\n", encoding="utf-8")
    pro_note = repeatability["comparisons"][3]["note"]
    card = f"""# ITU AI for Climate Innovation Factory - Evidence Card

## Pir Panjal Snowpack POC - Local Docker Native SNOWPACK Pipeline Integrity Proof

**Generated (UTC):** {generated_at}

**Evidence lane:** {EVIDENCE_LANE} — {EVIDENCE_LANE_DESCRIPTION}

## Claim boundary

This package proves only a corrected local Docker native SNOWPACK pipeline run and its repeatability checks. It is not scientific validation, an operational warning, a Partner approval, an accuracy claim, or production ML promotion. It is a local Docker run, not a hosted or cloud run.

## Provenance

| Field | Value |
|-------|-------|
| Run source SHA | `{declared_source_sha}` |
| Package generation SHA | `{pkg_gen_sha}` |
| Source attestation | verified before native execution on clean worktree |
| Decision record SHA-256 | `{decision_hash}` |
| Run ID | `{cr.get('run_id')}` |
| Repeat run ID | `{rr.get('run_id')}` |
| Runtime errors / warnings | {log_analysis['error_count']} / {log_analysis['warning_count']} |
| Exit code | {ne.get('exit_code')} |

## Toolchain

| Field | Value |
|-------|-------|
| Binary | SNOWPACK 3.7.0 + MeteoIO 2.11.0 |
| Binary SHA-256 | `{ne.get('binary_sha256')}` |
| Toolchain manifest SHA-256 | `{sha256_file(toolchain_path)}` |
| Docker image ID | `{ne.get('image_id')}` |
| Docker image archive SHA-256 | `{ne.get('image_archive_sha256')}` |

## Forcing and repeatability

The v16 forcing package retains `terrestrial_radiation` as provenance-only and does not map it to SNOWPACK ILWR. The source, sample counts, warmup, null counts, and treatment fields are copied from the forcing manifest.

| Artifact | Result |
|----------|--------|
| `.smet` | {"MATCH" if repeatability['comparisons'][0]['exact_match'] else "MISMATCH"} |
| `.sno` | {"MATCH" if repeatability['comparisons'][1]['exact_match'] else "MISMATCH"} |
| `.haz` | {"MATCH" if repeatability['comparisons'][2]['exact_match'] else "MISMATCH"} |
| `.pro` | {pro_note} |

**Result:** {repeatability['repeatability_result']}

## Profile summary

| Field | Value |
|-------|-------|
{''.join(f"| {field} | {value} |\n" for field, value in profile.items())}

## Rights and package scope

Open-Meteo raw data and derived artifacts remain internal until the owner records a rights decision. The eight package files contain evidence summaries and recursive hashes; raw run files remain internal.

## Non-claims

{''.join(f"- {claim}\n" for claim in NON_CLAIMS)}
"""
    (out_dir / "ITU_EVIDENCE_CARD.md").write_text(card.rstrip() + "\n", encoding="utf-8")
    (out_dir / "proof-card.md").write_text(
        render_proof_card_markdown(proof_summary),
        encoding="utf-8",
    )
    write_proof_card_csv(out_dir / "proof-card.csv", proof_card_rows(proof_summary))

    package_hash = package_content_sha256(out_dir)
    provenance["package_content_sha256"] = package_hash
    provenance["package_content_hash_scope"] = [name for name in PACKAGE_FILES if name != "provenance-manifest.json"]
    write_json(out_dir / "provenance-manifest.json", provenance)
    actual_names = sorted(item.name for item in out_dir.iterdir())
    if actual_names != sorted(PACKAGE_FILES):
        raise EvidencePackageError(
            f"package file set mismatch: expected={sorted(PACKAGE_FILES)}, actual={actual_names}"
        )
    print("=== ITU Evidence Package Generated (v3, fail-closed) ===")
    for p in sorted(out_dir.iterdir()):
        print(f"  {p.name}: {p.stat().st_size} bytes")
    print(f"\nRun source SHA: {declared_source_sha}")
    print(f"Package generation SHA: {pkg_gen_sha}")
    print(f"SHA mismatch: {declared_source_sha != pkg_gen_sha}")
    print("Worktree dirty at generation: False")
    print(f"Package content SHA-256: {package_hash}")
    print(f"Runtime errors: {log_analysis['error_count']}")
    print(f"Runtime warnings: {log_analysis['warning_count']}")
    print(f"Repeatability: {repeatability['repeatability_result']}")
    print(f"Run inventory: {len(run_inv)} files")
    print(f"Repeat inventory: {len(rep_inv)} files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ITU evidence package (fail-closed)")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--repeat-dir", required=True, type=Path)
    parser.add_argument("--run-source-sha", required=True)
    parser.add_argument("--toolchain-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    try:
        return generate_package(args)
    except (EvidencePackageError, FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: ITU evidence package generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
