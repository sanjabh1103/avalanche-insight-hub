from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.common.european_shadow_sources import build_european_shadow_manifest


def _parse_license_review(value: str) -> tuple[str, str]:
    source_key, sep, review_id = str(value).partition('=')
    if not sep or not source_key.strip() or not review_id.strip():
        raise argparse.ArgumentTypeError('license review must use SOURCE_KEY=REVIEW_ID')
    return source_key.strip(), review_id.strip()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build a shadow-only European avalanche source manifest with license and promotion gates.',
    )
    parser.add_argument(
        '--source',
        action='append',
        dest='sources',
        default=None,
        help='Source key to include. Repeat to build a subset. Defaults to all registry entries.',
    )
    parser.add_argument(
        '--snapshot-id',
        default=None,
        help='Stable manifest snapshot identifier.',
    )
    parser.add_argument(
        '--license-review',
        action='append',
        type=_parse_license_review,
        default=[],
        metavar='SOURCE_KEY=REVIEW_ID',
        help='Mark a source as license-reviewed for shadow/benchmark gates.',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Optional output JSON path. Defaults to stdout.',
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_european_shadow_manifest(
        selected_keys=args.sources,
        snapshot_id=args.snapshot_id,
        license_review_ids=dict(args.license_review),
    )
    payload = json.dumps(manifest, indent=2, sort_keys=True)
    if args.output is None:
        print(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
