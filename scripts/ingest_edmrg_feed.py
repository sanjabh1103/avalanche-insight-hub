#!/usr/bin/env python3
"""Ingest eDMRG telemetry from a configured feed URL.

Reads from EDMRG_FEED_URL env var. Parses CSV or JSON data using
the eDMRG adapter and converts to weather sample dicts. When
EDMRG_FEED_URL is not set, exits with code 0 (no-op for CI).

Usage:
    python3 scripts/ingest_edmrg_feed.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def main() -> int:
    feed_url = os.getenv('EDMRG_FEED_URL', '').strip()
    if not feed_url:
        print('[edmrg_ingest] EDMRG_FEED_URL not set — skipping (no-op)')
        return 0

    from backend.common.edmrg_adapter import (
        load_field_mapping,
        parse_edmrg_csv,
        parse_edmrg_json,
        edmrg_to_weather_samples,
    )

    import urllib.request

    print(f'[edmrg_ingest] Fetching from {feed_url}')
    try:
        with urllib.request.urlopen(feed_url, timeout=30) as response:
            raw = response.read().decode('utf-8')
    except Exception as exc:
        print(f'[edmrg_ingest] Fetch failed: {exc}', file=sys.stderr)
        return 1

    mapping = load_field_mapping()

    records = []
    if feed_url.endswith('.csv') or ',' in raw[:200]:
        records = parse_edmrg_csv(raw, mapping=mapping)
    else:
        try:
            data = json.loads(raw)
            records = parse_edmrg_json(data, mapping=mapping)
        except json.JSONDecodeError:
            records = parse_edmrg_csv(raw, mapping=mapping)

    if not records:
        print('[edmrg_ingest] No records parsed from feed')
        return 0

    samples = edmrg_to_weather_samples(records)
    print(f'[edmrg_ingest] Parsed {len(records)} records → {len(samples)} weather samples')

    for rec in records[:5]:
        print(f'  {rec.station_id} @ {rec.timestamp.isoformat()} cadence={rec.cadence}')

    if len(records) > 5:
        print(f'  ... and {len(records) - 5} more')

    return 0


if __name__ == '__main__':
    sys.exit(main())
