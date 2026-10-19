#!/usr/bin/env python3
"""Create the non-promoting preparation manifest for interval training evidence.

This command verifies the exact shadow frame and its source/feature hashes.  It
does not fit a model, create negative labels, or grant training eligibility.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.interval_training_preparation import (
    IntervalTrainingPreparationError,
    build_interval_training_preparation_manifest,
    write_interval_training_preparation_manifest,
)


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntervalTrainingPreparationError(f"{label} cannot be read: {path}") from exc
    if not isinstance(value, dict):
        raise IntervalTrainingPreparationError(f"{label} must be a JSON object: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-manifest", required=True, type=Path)
    parser.add_argument("--feature-manifest", required=True, type=Path)
    parser.add_argument("--join-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_interval_training_preparation_manifest(
            label_manifest=_load_object(args.label_manifest, label="label manifest"),
            feature_manifest=_load_object(args.feature_manifest, label="feature manifest"),
            join_report=_load_object(args.join_report, label="join report"),
        )
        written = write_interval_training_preparation_manifest(args.output, manifest)
    except IntervalTrainingPreparationError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "shadow_preparation_written",
                "manifest_hash": written["manifest_hash"],
                "training_path_status": written["training_path_status"],
                "training_eligible": written["training_eligible"],
                "interval_training_ready": written["interval_training_ready"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
