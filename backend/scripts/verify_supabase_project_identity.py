"""Verify a Supabase URL against the canonical project manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.common.supabase_project_identity import (
    SupabaseProjectIdentityError,
    assert_canonical_project_url,
    load_project_target,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Supabase URL to verify")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional canonical project manifest path",
    )
    args = parser.parse_args()
    try:
        target = load_project_target(args.manifest)
        assert_canonical_project_url(args.url, target=target)
    except SupabaseProjectIdentityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "pass",
        "project_ref": target.project_ref,
        "supabase_url": target.supabase_url,
        "evidence_class": "project_identity_only",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
