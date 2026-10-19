from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.common.european_shadow_ingest import stage_european_source


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Stage reviewed local European avalanche data exports into shadow-only manifests.',
    )
    parser.add_argument('--source-key', required=True, help='European source key from the registry.')
    parser.add_argument('--raw-path', type=Path, required=True, help='Local file, zip, or directory to stage.')
    parser.add_argument('--license-review', required=True, help='Recorded license review identifier.')
    parser.add_argument('--snapshot-id', required=True, help='Stable staging snapshot id.')
    parser.add_argument('--output-root', type=Path, required=True, help='Output root for generated staging artifacts.')
    parser.add_argument('--requested-role', default=None, help='Optional role override. Defaults to the source role.')
    parser.add_argument('--sar-split', default='val', help='Split for generated SAR training scenes when possible.')
    parser.add_argument('--output', type=Path, default=None, help='Optional copy of the staging manifest JSON.')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = stage_european_source(
        source_key=args.source_key,
        raw_path=args.raw_path,
        license_review_id=args.license_review,
        output_root=args.output_root,
        snapshot_id=args.snapshot_id,
        requested_role=args.requested_role,
        sar_split=args.sar_split,
    )
    payload = json.dumps(manifest, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
