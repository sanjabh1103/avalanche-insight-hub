#!/usr/bin/env python3
"""Build a deterministic station-free feature snapshot from reviewed rows.

The input JSONL must already contain public-source feature values and explicit
``feature_valid_from``, ``feature_valid_until`` and ``feature_cutoff_at``
fields.  This command does not fetch data, infer historical coverage, or
promote the result into training or production.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.station_free_feature_snapshot import (
    DEFAULT_FEATURE_NAMES,
    build_station_free_feature_snapshot,
    write_station_free_feature_snapshot,
)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"feature row at {path}:{line_number} must be an object")
        rows.append(value)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--region-key", action="append", required=True)
    parser.add_argument("--required-feature", action="append", dest="required_features")
    parser.add_argument("--spatial-bin-km", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    rows = _jsonl(args.input_jsonl)
    required_features = args.required_features or list(DEFAULT_FEATURE_NAMES)
    normalized, manifest = build_station_free_feature_snapshot(
        rows,
        region_keys=args.region_key,
        source_manifest=source_manifest,
        required_feature_names=required_features,
        spatial_bin_km=args.spatial_bin_km,
    )
    write_station_free_feature_snapshot(args.output_dir, normalized, manifest)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "feature_row_count": manifest["feature_row_count"],
                "feature_rows_sha256": manifest["feature_rows_sha256"],
                "manifest_hash": manifest["manifest_hash"],
                "region_keys": manifest["region_keys"],
                "station_data_used": manifest["station_data_used"],
                "training_eligible": manifest["training_eligible"],
                "production_scoring_eligible": manifest["production_scoring_eligible"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
