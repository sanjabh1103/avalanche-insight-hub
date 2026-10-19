"""Upload or download a complete, hash-verified POC bundle in Supabase Storage.

Credentials are read from ``SUPABASE_URL`` and
``SUPABASE_SERVICE_ROLE_KEY``. Values are never printed. The canonical
project URL is checked before any network operation.

Examples::

    python -m backend.scripts.supabase_bundle upload \
      --source-dir backend/artifacts/snowpack/bundle \
      --object-prefix "$RUN_ID"

    python -m backend.scripts.supabase_bundle download \
      --output-dir /tmp/snowpack-download \
      --object-prefix "$RUN_ID"

Upload success means only that all objects were accepted by Storage. Download
success additionally means the recursive bundle manifest was verified. The
independent SNOWPACK release gate remains a separate required consumer check.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from backend.common.artifact_round_trip import (
    RoundTripStatus,
    download_supabase_bundle,
    upload_supabase_bundle,
)
from backend.common.supabase_project_identity import (
    SupabaseProjectIdentityError,
    assert_canonical_project_url,
    load_project_target,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('upload', 'download'))
    parser.add_argument('--bucket', default='poc-artifacts')
    parser.add_argument('--object-prefix', required=True)
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--project-manifest', type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        print('ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required', file=sys.stderr)
        return 1
    try:
        target = load_project_target(args.project_manifest)
        assert_canonical_project_url(url, target=target)
    except SupabaseProjectIdentityError as exc:
        print(f'ERROR: Supabase target rejected: {exc}', file=sys.stderr)
        return 1

    if args.action == 'upload':
        if args.source_dir is None:
            print('ERROR: --source-dir is required for upload', file=sys.stderr)
            return 1
        result = upload_supabase_bundle(
            args.source_dir,
            bucket=args.bucket,
            object_prefix=args.object_prefix,
            supabase_url=url,
            service_role_key=key,
        )
        exit_ok = result.status == RoundTripStatus.SUCCESS
    else:
        if args.output_dir is None:
            print('ERROR: --output-dir is required for download', file=sys.stderr)
            return 1
        result = download_supabase_bundle(
            args.output_dir,
            bucket=args.bucket,
            object_prefix=args.object_prefix,
            supabase_url=url,
            service_role_key=key,
        )
        exit_ok = result.status == RoundTripStatus.SUCCESS and result.verified

    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if exit_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
