"""Manual live-bulletin conformance command.

Fetches a live Partner bulletin PDF, parses it with the provenance-backed parser,
and reports completeness, row count, and parse errors. Exits non-zero if the
bulletin fails completeness validation.

Usage:
    python3 -m backend.scripts.bulletin_conformance [--url URL] [--days N]

Exit codes:
    0 — bulletin parsed successfully with complete rows
    1 — bulletin parsed but incomplete (missing date or no complete rows)
    2 — fetch or parse error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def run_conformance(url: str | None = None, days: int = 7) -> dict:
    """Fetch and validate a live Partner bulletin.

    If url is provided, fetches that specific bulletin.
    Otherwise, lists recent bulletins and checks the first one found.
    """
    from backend.common.Partner_bulletin_adapter import (
        Partner_BULLETIN_VALIDATION_ENABLED,
        fetch_bulletin,
        list_recent_bulletins,
    )
    import backend.common.Partner_bulletin_adapter as da

    original = da.Partner_BULLETIN_VALIDATION_ENABLED
    da.Partner_BULLETIN_VALIDATION_ENABLED = True
    try:
        if url:
            result = fetch_bulletin(url)
        else:
            bulletins = list_recent_bulletins(days=days)
            if not bulletins:
                return {
                    'status': 'no_bulletins_found',
                    'days_searched': days,
                    'exit_code': 2,
                }
            result = bulletins[0]

        report = {
            'bulletin_id': result.record.bulletin_id if result.record else None,
            'is_complete': result.is_complete,
            'parse_error': result.parse_error,
            'complete_row_count': result.complete_row_count,
            'total_row_count': len(result.record.rows) if result.record else 0,
            'issue_date': result.record.issue_date.isoformat() if result.record and result.record.issue_date else None,
            'provenance_hash': result.provenance_hash,
            'source_url': result.record.source_url if result.record else None,
            'exit_code': 0 if result.is_complete else 1,
        }
        return report
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'exit_code': 2,
        }
    finally:
        da.Partner_BULLETIN_VALIDATION_ENABLED = original


def main() -> int:
    parser = argparse.ArgumentParser(description='Manual live-bulletin conformance check')
    parser.add_argument('--url', type=str, default=None, help='Specific bulletin URL to check')
    parser.add_argument('--days', type=int, default=7, help='Days to search for recent bulletins (default: 7)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    report = run_conformance(url=args.url, days=args.days)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"[bulletin_conformance] bulletin_id={report.get('bulletin_id', 'N/A')}")
        print(f"  is_complete:     {report.get('is_complete', 'N/A')}")
        print(f"  parse_error:     {report.get('parse_error', 'N/A')}")
        print(f"  complete_rows:   {report.get('complete_row_count', 0)}")
        print(f"  total_rows:      {report.get('total_row_count', 0)}")
        print(f"  issue_date:      {report.get('issue_date', 'N/A')}")
        print(f"  provenance_hash: {report.get('provenance_hash', 'N/A')}")
        if report.get('exit_code', 2) != 0:
            print(f"  status:          {report.get('status', 'failed')}")

    return report.get('exit_code', 2)


if __name__ == '__main__':
    sys.exit(main())
