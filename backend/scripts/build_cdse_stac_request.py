#!/usr/bin/env python3
"""Write a bounded direct-CDSE STAC request without making a network call."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.common.cdse_stac_contract import (
    DEFAULT_ITEM_LIMIT,
    CdseStacContractError,
    write_request_bundle,
)
from backend.common.regions import load_regions


def _region_bbox(region_key: str) -> tuple[float, float, float, float]:
    regions = {region.key: region for region in load_regions()}
    try:
        return regions[region_key].bbox
    except KeyError as exc:
        raise CdseStacContractError(
            f"unknown region_key {region_key!r}; expected one of {sorted(regions)}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-key", required=True)
    parser.add_argument("--start", required=True, help="timezone-aware ISO-8601 start")
    parser.add_argument("--end", required=True, help="timezone-aware ISO-8601 end")
    parser.add_argument("--limit", type=int, default=DEFAULT_ITEM_LIMIT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = write_request_bundle(
            args.output_dir,
            region_key=args.region_key,
            region_bbox=_region_bbox(args.region_key),
            start=args.start,
            end=args.end,
            limit=args.limit,
        )
    except CdseStacContractError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "endpoint": manifest["endpoint"],
                "region_key": manifest["region_key"],
                "collection": manifest["collection"],
                "request_sha256": manifest["request_sha256"],
                "manifest_hash": manifest["manifest_hash"],
                "network_fetch_performed": manifest["network_fetch_performed"],
                "training_eligible": manifest["training_eligible"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
