#!/usr/bin/env python3
"""Capture the clean host Git identity used by a containerized ITU run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GIT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


def capture(output: Path) -> dict[str, object]:
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise RuntimeError("unable to determine repository worktree state")
    if not GIT_COMMIT_RE.fullmatch(source_sha):
        raise RuntimeError(f"invalid Git commit SHA: {source_sha!r}")
    if status.stdout.strip():
        raise RuntimeError("source worktree must be clean before native execution")
    status_sha = hashlib.sha256(status.stdout.encode("utf-8")).hexdigest()
    attestation: dict[str, object] = {
        "schema_version": "itu_run_source_attestation_v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_before_native_execution": True,
        "capture_method": "runner_preflight_git_identity",
        "run_source_sha": source_sha,
        "worktree_dirty_at_capture": False,
        "worktree_status_sha256": status_sha,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return attestation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        attestation = capture(args.output.resolve())
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(attestation, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
