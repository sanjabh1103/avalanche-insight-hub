#!/usr/bin/env python3
"""Build a region-bounded, reviewed interval-label staging snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.common.interval_source_adapter import (
    build_interval_label_staging,
    write_interval_label_staging,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", action="append", type=Path, required=True)
    parser.add_argument("--overlap-report", type=Path, required=True)
    parser.add_argument("--region-key", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    rows, manifest, overlap_payload = build_interval_label_staging(
        args.source_dir,
        overlap_report_path=args.overlap_report,
        region_keys=args.region_key,
    )
    write_interval_label_staging(args.output_dir, rows, manifest, overlap_payload)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "included_record_count": manifest["included_record_count"],
        "event_rows_sha256": manifest["event_rows_sha256"],
        "source_keys": manifest["source_keys"],
        "positive_season_count": manifest["positive_season_count"],
        "positive_seasons_by_region": manifest["positive_seasons_by_region"],
        "training_eligible": manifest["training_eligible"],
        "interval_training_ready": manifest["interval_training_ready"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
