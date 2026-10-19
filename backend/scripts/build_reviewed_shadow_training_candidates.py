"""Create a shadow-only candidate pack from exported scientist review data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.reviewed_shadow_training import build_shadow_training_candidate_pack


def _records(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def build_candidate_pack(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept both single-case and sign-off-summary export shapes."""
    cases = _records(payload.get('cases'))
    reviews = _records(payload.get('reviews'))
    if not cases and isinstance(payload.get('case'), dict):
        case = dict(payload['case'])
        cases = [case]
        reviews = _records(payload.get('reviews'))
    if cases:
        nested_reviews = [
            review
            for case in cases
            for review in _records(case.get('reviews'))
        ]
        if nested_reviews:
            reviews = nested_reviews
    return build_shadow_training_candidate_pack(cases, reviews)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build shadow-only training candidates from scientist review exports.',
    )
    parser.add_argument('--input', required=True, help='Scientist validation packet or summary JSON.')
    parser.add_argument('--output', required=True, help='Destination JSON candidate pack.')
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Review export must be a JSON object')
    pack = build_candidate_pack(payload)
    Path(args.output).write_text(json.dumps(pack, indent=2), encoding='utf-8')
    print(json.dumps(pack['summary'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
