#!/usr/bin/env python3
"""Prepare a hash-bound, still-pending MVP4 pre-remote approval draft.

The command is a convenience for the human approval step.  It never changes a
decision to ``GO``, invents an approver, promotes a source, or changes remote
state.  It only reads repository-local JSON manifests and emits a draft with
their relative paths and SHA-256 bindings prefilled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_SCHEMA_VERSION = "mvp4_pre_remote_approval_v1"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} does not resolve to a file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON: {path} ({exc})") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def _repo_relative(path: Path, label: str) -> str:
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"{label} must remain inside the repository: {path}") from exc
    return relative.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_draft_approval(
    *,
    scope_manifest: Path,
    snapshot_manifest: Path,
    selected_region_keys: list[str],
) -> dict[str, Any]:
    """Return a pending approval draft bound to two repository-local files."""
    scope = _load_object(scope_manifest, "scope manifest")
    _load_object(snapshot_manifest, "snapshot manifest")
    scope_relative = _repo_relative(scope_manifest, "scope manifest")
    snapshot_relative = _repo_relative(snapshot_manifest, "snapshot manifest")

    selection_hash = scope.get("selection_hash")
    if not isinstance(selection_hash, str) or not SHA256_PATTERN.fullmatch(selection_hash):
        raise ValueError("scope manifest must declare a 64-character selection_hash")
    selected_paths = scope.get("selected_paths")
    if not isinstance(selected_paths, list) or not selected_paths:
        raise ValueError("scope manifest must contain non-empty selected_paths")

    regions = [str(value).strip() for value in selected_region_keys]
    if not regions or any(not value for value in regions) or len(set(regions)) != len(regions):
        raise ValueError("selected_region_keys must be non-empty and duplicate-free")

    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "decision": "PENDING",
        "scope_manifest_path": scope_relative,
        "scope_manifest_sha256": _sha256(scope_manifest),
        "snapshot_manifest_path": snapshot_relative,
        "snapshot_manifest_sha256": _sha256(snapshot_manifest),
        "approved_candidate_selection_hash": selection_hash,
        "selected_region_keys": regions,
        "approved_by": [
            {"role": "scientist", "name": None, "approval_ref": None},
            {"role": "customer", "name": None, "approval_ref": None},
        ],
        "approved_at": None,
        "notes": (
            "Draft only. A named reviewer or privacy-preserving approval_ref, "
            "timezone-aware approved_at, decision GO, and independent source/"
            "threshold/uncertainty approval are still required."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-manifest", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--region-keys", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional new repository-local output path; existing files are never overwritten",
    )
    args = parser.parse_args(argv)
    try:
        regions = [value.strip() for value in args.region_keys.split(",")]
        draft = build_draft_approval(
            scope_manifest=args.scope_manifest,
            snapshot_manifest=args.snapshot_manifest,
            selected_region_keys=regions,
        )
        payload = json.dumps(draft, indent=2, sort_keys=False) + "\n"
        if args.output is None:
            print(payload, end="")
        else:
            output = args.output.expanduser()
            if not output.is_absolute():
                output = ROOT / output
            _repo_relative(output, "approval draft output")
            if output.exists():
                raise ValueError(f"refusing to overwrite existing approval draft: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
            print(f"Wrote pending approval draft: {output}")
    except (OSError, ValueError) as exc:
        print(f"approval draft blocked: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
