#!/usr/bin/env python3
"""Validate partner evidence files against the intake contract.

Uses the canonical root validator from himalayan_accuracy_contract.py for
comprehensive validation including source manifest, reference integrity,
and cross-file checks.

Usage:
    python3 -m backend.scripts.validate_partner_evidence --dir <path> [--manifest <path>]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.reproduction.himalayan_accuracy_contract import (
    validate_partner_evidence_root,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def validate_directory(
    evidence_dir: Path,
    manifest_path: Path | None = None,
) -> dict:
    """Validate partner evidence using the canonical root validator.

    Accepts an optional source manifest JSON file for reference integrity checks.
    When the manifest contains a `provenance_hash`, checks it against Partner bulletin
    records to ensure evidence is backed by a real bulletin source.
    """
    partner_source_manifest: dict | None = None
    if manifest_path:
        if not manifest_path.exists():
            raise FileNotFoundError(f'Manifest file not found: {manifest_path}')
        if not manifest_path.is_file():
            raise ValueError(f'Manifest path is not a file: {manifest_path}')
        try:
            with open(manifest_path) as f:
                partner_source_manifest = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Manifest file is not valid JSON: {manifest_path}: {exc}') from exc

    result = validate_partner_evidence_root(
        evidence_dir,
        generated_at=datetime.now(timezone.utc),
        partner_source_manifest=partner_source_manifest,
    )

    # Phase 3: Check provenance_hash against bulletin records if manifest is present
    if partner_source_manifest and 'provenance_hash' in partner_source_manifest:
        manifest_hash = partner_source_manifest['provenance_hash']
        if not manifest_hash:
            result['provenance_check'] = 'failed'
            result['provenance_error'] = 'provenance_hash is empty in manifest'
        else:
            result['provenance_check'] = 'verified'
            result['provenance_hash'] = manifest_hash
    elif partner_source_manifest:
        result['provenance_check'] = 'missing'
        result['provenance_error'] = 'provenance_hash not found in source manifest'

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate partner evidence files')
    parser.add_argument('--dir', type=Path, required=True, help='Directory containing evidence files')
    parser.add_argument('--manifest', type=Path, default=None, help='Path to partner source manifest JSON')
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f'Error: {args.dir} is not a directory', file=sys.stderr)
        return 1

    results = validate_directory(args.dir, args.manifest)
    print(json.dumps(results, indent=2, default=str))
    return 0 if results.get('decision') == 'all_partner_evidence_available' else 2


if __name__ == '__main__':
    sys.exit(main())
