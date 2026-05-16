from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.common.european_shadow_benchmarks import (
    build_european_shadow_benchmark_report,
    load_staging_manifest,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build a shadow-only European data benchmark/readiness report from staged manifests.',
    )
    parser.add_argument(
        '--manifest',
        action='append',
        type=Path,
        required=True,
        help='Path to a staged_manifest.json file. Repeat to combine sources.',
    )
    parser.add_argument('--snapshot-id', default=None, help='Optional benchmark snapshot id.')
    parser.add_argument('--output', type=Path, default=None, help='Optional output JSON path.')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_european_shadow_benchmark_report(
        staging_manifests=[load_staging_manifest(path) for path in args.manifest],
        snapshot_id=args.snapshot_id,
    )
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
