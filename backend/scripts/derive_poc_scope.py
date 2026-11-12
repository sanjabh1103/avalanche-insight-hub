"""CLI helper for deriving POC scope from the Pir Panjal decision record.

P1-7/P1-8: Replaces inline json.loads(Path(...).read_text()) in workflow YAML.
This helper:
  1. Reads raw bytes
  2. Verifies the externally supplied SHA-256 BEFORE any parsing
  3. Validates the complete decision record
  4. Validates POC scope
  5. Emits only approved region, elevation_band, and headline_horizon_hours

Usage in GitHub Actions:
  python3 -m backend.scripts.derive_poc_scope \
    --decision-record-path docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json \
    --expected-sha256 "$PIR_PANJAL_DECISION_RECORD_SHA256" \
    --emit github-env

Outputs (depending on --emit mode):
  - github-env: writes POC_REGION, POC_ELEVATION_BAND, POC_HEADLINE_HORIZON_HOURS to GITHUB_ENV
  - json: prints JSON to stdout with region_key, elevation_band, headline_horizon_hours
  - shell: prints shell-compatible export statements to stdout

Exit codes:
  0 = scope derived successfully
  1 = hash mismatch, invalid decision record, or invalid scope
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_SHA256_PATTERN = re.compile(r'^[0-9a-fA-F]{64}$')


def _verify_hash(raw_bytes: bytes, expected_sha256: str) -> None:
    """Verify raw bytes against the externally supplied SHA-256."""
    if not _SHA256_PATTERN.fullmatch(expected_sha256):
        print(
            f'ERROR: expected SHA-256 is not a valid 64-character hex string: '
            f'{expected_sha256!r}',
            file=sys.stderr,
        )
        sys.exit(1)
    actual = hashlib.sha256(raw_bytes).hexdigest()
    if actual.lower() != expected_sha256.lower():
        print(
            f'ERROR: decision record hash mismatch. '
            f'Expected {expected_sha256!r}, got {actual!r}. '
            f'The file has been modified or is not the approved version.',
            file=sys.stderr,
        )
        sys.exit(1)


def derive_scope(decision_record_path: Path, expected_sha256: str) -> dict[str, str | int]:
    """Derive POC scope from the decision record after hash verification.

    Returns a dict with:
      region_key: str
      elevation_band: str
      headline_horizon_hours: int
      ensemble_members: int
    """
    # P1-8: Read raw bytes and verify hash BEFORE any parsing
    # R7: Use load_decision_record_from_bytes to eliminate the TOCTOU seam.
    # The file is read exactly once; hash verification and semantic parsing
    # operate on the same immutable byte buffer.
    raw_bytes = decision_record_path.read_bytes()
    _verify_hash(raw_bytes, expected_sha256)

    # Parse and validate the already-read bytes (no second file read)
    from backend.common.pir_panjal_decision_record import load_decision_record_from_bytes
    dr = load_decision_record_from_bytes(
        raw_bytes, expected_sha256=expected_sha256,
        source_path=str(decision_record_path),
    )

    return {
        'region_key': dr.selected_sector,
        'elevation_band': dr.elevation_band,
        'headline_horizon_hours': dr.headline_horizon_hours,
        'ensemble_members': dr.ensemble_members,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Derive POC scope from the Pir Panjal decision record with hash verification.'
    )
    parser.add_argument(
        '--decision-record-path',
        type=Path,
        required=True,
        help='Path to the PIR_PANJAL_POC_DECISION_RECORD.json file.',
    )
    parser.add_argument(
        '--expected-sha256',
        required=True,
        help='Externally supplied SHA-256 of the decision record bytes (trust root).',
    )
    parser.add_argument(
        '--emit',
        choices=['github-env', 'json', 'shell'],
        default='github-env',
        help='Output format. github-env writes to $GITHUB_ENV.',
    )
    args = parser.parse_args()

    scope = derive_scope(args.decision_record_path, args.expected_sha256)

    if args.emit == 'github-env':
        github_env = os.environ.get('GITHUB_ENV')
        if not github_env:
            print('ERROR: GITHUB_ENV is not set', file=sys.stderr)
            sys.exit(1)
        with open(github_env, 'a') as f:
            f.write(f"POC_REGION={scope['region_key']}\n")
            f.write(f"POC_ELEVATION_BAND={scope['elevation_band']}\n")
            f.write(f"POC_HEADLINE_HORIZON_HOURS={scope['headline_horizon_hours']}\n")
        print(
            f"POC scope derived: region={scope['region_key']}, "
            f"band={scope['elevation_band']}, "
            f"horizon={scope['headline_horizon_hours']}h"
        )
    elif args.emit == 'json':
        print(json.dumps(scope, indent=2))
    elif args.emit == 'shell':
        print(f"export POC_REGION={scope['region_key']!r}")
        print(f"export POC_ELEVATION_BAND={scope['elevation_band']!r}")
        print(f"export POC_HEADLINE_HORIZON_HOURS={scope['headline_horizon_hours']!r}")


if __name__ == '__main__':
    main()
