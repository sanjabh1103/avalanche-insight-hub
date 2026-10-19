#!/usr/bin/env python3
"""Generate a tracked, reviewable release attestation for a shadow artifact.

The attestation is the single external trust anchor for the artifact.  It
binds the bundle digest, component hashes, source commit, generator commit,
dependency-lock hash, preflight report hash, and licence/attribution
references into one reviewable record.

The attestation is NOT externally trusted until it is preserved in a
reviewed release commit or approved immutable store.  This script
generates the attestation; it does not approve it.

Usage:
  python -m backend.scripts.generate_release_attestation \
    --artifact-dir <path> \
    --output <path> \
    [--repo-root <path>]
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(repo_root: Path) -> str:
    """Get the current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def _git_dirty(repo_root: Path) -> bool:
    """Check if the git working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, OSError):
        return True  # Assume dirty if we can't check


def _python_version() -> str:
    import platform
    return platform.python_version()


def _dependency_lock_hash(repo_root: Path) -> dict[str, str | None]:
    """Hash the dependency lock files used by the workflows.

    The workflows install from backend/locks/core-py312.txt (core) and
    backend/locks/ci-py312.txt (CI).  Both are hashed and returned.
    The primary lock (core-py312.txt) is the one used by the training
    and pilot workflows for --require-hashes installation.
    """
    locks: dict[str, str | None] = {
        "core_lock_sha256": None,
        "ci_lock_sha256": None,
        "snowpack_lock_sha256": None,
    }
    lock_paths = {
        "core_lock_sha256": repo_root / "backend" / "locks" / "core-py312.txt",
        "ci_lock_sha256": repo_root / "backend" / "locks" / "ci-py312.txt",
        "snowpack_lock_sha256": repo_root / "backend" / "locks" / "snowpack-py312.txt",
    }
    for key, path in lock_paths.items():
        if path.is_file():
            locks[key] = _sha256_file(path)
    return locks


def _to_portable_rel(path: Path, repo_root: Path) -> str:
    """Convert an absolute path to a repo-root-relative POSIX string.

    G7: The attestation must be portable across machines.  Absolute paths
    like /Users/sanjayb/... leak the build host and break reproducibility.
    If the path is outside repo_root, fall back to the resolved absolute
    path with a note so the anomaly is visible rather than silently hidden.
    """
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        return rel.as_posix()
    except ValueError:
        return str(path.resolve())


def generate_attestation(
    artifact_dir: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Generate a release attestation for the artifact."""
    if repo_root is None:
        repo_root = Path.cwd()

    # G7: store portable repo-root-relative paths, not absolute machine paths
    artifact_dir_rel = _to_portable_rel(artifact_dir, repo_root)

    # Load bundle manifest
    bundle_path = artifact_dir / "bundle_manifest.json"
    if not bundle_path.is_file():
        raise ValueError(f"bundle_manifest.json not found in {artifact_dir}")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    # Load preflight report if it exists
    preflight_path = artifact_dir / "shadow_preflight_report.json"
    preflight_hash = None
    if preflight_path.is_file():
        preflight_hash = _sha256_file(preflight_path)

    # Load source provenance for licence/attribution
    provenance_path = artifact_dir / "source_provenance.json"
    provenance = {}
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    source_manifest = provenance.get("source_manifest", {})

    # Get git metadata
    source_commit = _git_commit(repo_root)
    is_dirty = _git_dirty(repo_root)
    dep_lock_hashes = _dependency_lock_hash(repo_root)

    # G6: generator_commit is the commit that contains the generator script.
    # If the working tree is dirty (generator script uncommitted), mark it
    # as unavailable so the attestation does not claim a false binding.
    if is_dirty:
        generator_commit = "unavailable_dirty_tree"
        generator_commit_note = (
            "The generator script is uncommitted or the working tree is dirty. "
            "This field will be populated with the actual commit SHA after the "
            "reviewed release commit."
        )
    else:
        generator_commit = source_commit
        generator_commit_note = (
            "The generator script is committed at this SHA. "
            "This field binds the attestation to the exact generator version."
        )

    attestation = {
        "attestation_schema_version": "mvp4_shadow_release_attestation_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_dir": artifact_dir_rel,
        "repo_root": ".",  # G7: portable — repo root is implicit
        # Git metadata
        "source_commit": source_commit,
        "working_tree_dirty": is_dirty,
        "generator_commit": generator_commit,
        "generator_commit_note": generator_commit_note,
        # Bundle binding
        "bundle_sha256": bundle.get("bundle_sha256"),
        "bundle_schema_version": bundle.get("bundle_schema_version"),
        "component_hashes": bundle.get("component_hashes"),
        # Preflight binding
        "preflight_report_sha256": preflight_hash,
        "preflight_version": "mvp4_shadow_preflight_v3",
        # Source provenance binding
        "source_provenance_sha256": _sha256_file(provenance_path) if provenance_path.is_file() else None,
        # Dependency lock binding (G4: hash actual lock files)
        "dependency_lock_sha256": dep_lock_hashes["core_lock_sha256"],
        "ci_lock_sha256": dep_lock_hashes["ci_lock_sha256"],
        "snowpack_lock_sha256": dep_lock_hashes["snowpack_lock_sha256"],
        # Runtime metadata
        "python_version": _python_version(),
        "platform": sys.platform,
        # Licence and attribution references
        "license_status": source_manifest.get("license_status", "unknown"),
        "license_url": source_manifest.get("license_url"),
        "underlying_license_url": source_manifest.get("underlying_license_url"),
        "attribution_text": source_manifest.get("attribution_text"),
        "data_provider": source_manifest.get("data_provider"),
        "dataset_product": source_manifest.get("dataset_product"),
        # Status declaration
        "status": "shadow_only",
        "training_eligible": False,
        "production_eligible": False,
        "production_scoring_eligible": False,
        "operational_grid_coverage": False,
        "coverage_scope": "label_linked_interval_features",
        # Summary counts
        "primary_label_row_count": bundle.get("primary_label_row_count"),
        "covered_primary_label_row_count": bundle.get("covered_primary_label_row_count"),
        "primary_unique_feature_key_count": bundle.get("primary_unique_feature_key_count"),
        "covered_primary_unique_feature_key_count": bundle.get("covered_primary_unique_feature_key_count"),
        # Trust classification
        "trust_classification": "locally_self_consistent",
        "trust_note": (
            "This attestation is locally self-consistent but NOT externally trusted. "
            "It becomes externally trusted only when preserved in a reviewed release "
            "commit or approved immutable store."
        ),
    }

    # Compute attestation hash (over all fields except the hash itself)
    attestation_bytes = json.dumps(
        {k: v for k, v in attestation.items() if k != "attestation_sha256"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    attestation["attestation_sha256"] = hashlib.sha256(attestation_bytes).hexdigest()

    return attestation


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="generate_release_attestation",
        description="Generate a tracked, reviewable release attestation for a shadow artifact. "
                    "The attestation binds the bundle digest, component hashes, source commit, "
                    "generator commit, dependency-lock hash, preflight report hash, and "
                    "licence/attribution references into one reviewable record.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Path to the artifact directory containing bundle_manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the attestation JSON. "
             "Canonical location: docs/MVP4/00_governance/SHADOW_RELEASE_ATTESTATION.json",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root for resolving lock files and git metadata. "
             "Defaults to current working directory.",
    )
    args = parser.parse_args(argv)

    artifact_dir = args.artifact_dir.resolve()
    repo_root = args.repo_root.resolve() if args.repo_root else None
    if not artifact_dir.is_dir():
        print(f"ERROR: artifact directory not found: {artifact_dir}", file=sys.stderr)
        return 1

    attestation = generate_attestation(artifact_dir, repo_root=repo_root)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(attestation, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "attestation_sha256": attestation["attestation_sha256"],
        "bundle_sha256": attestation["bundle_sha256"],
        "source_commit": attestation["source_commit"],
        "generator_commit": attestation["generator_commit"],
        "working_tree_dirty": attestation["working_tree_dirty"],
        "dependency_lock_sha256": attestation["dependency_lock_sha256"],
        "status": attestation["status"],
        "trust_classification": attestation["trust_classification"],
        "output_path": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
