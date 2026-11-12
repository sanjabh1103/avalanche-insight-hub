#!/usr/bin/env python3
"""Ingest AAVDS detection events from a configured feed URL.

Reads from AAVDS_FEED_URL env var. Fetches JSON events using
the AAVDS adapter. When AAVDS_FEED_URL is not set, exits with
code 0 (no-op for CI).

Usage:
    python3 scripts/ingest_aavds_feed.py
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    feed_url = os.getenv('AAVDS_FEED_URL', '').strip()
    if not feed_url:
        print('[aavds_ingest] AAVDS_FEED_URL not set — skipping (no-op)')
        return 0

    from backend.common.aavds_adapter import AAVDSAdapter

    import urllib.request

    print(f'[aavds_ingest] Fetching from {feed_url}')
    try:
        with urllib.request.urlopen(feed_url, timeout=30) as response:
            raw = response.read().decode('utf-8')
    except Exception as exc:
        print(f'[aavds_ingest] Fetch failed: {exc}', file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f'[aavds_ingest] Invalid JSON: {exc}', file=sys.stderr)
        return 1

    adapter = AAVDSAdapter()
    if isinstance(data, list):
        events = []
        for item in data:
            try:
                events.append(adapter._parse_event(item))
            except (KeyError, ValueError) as exc:
                print(f'[aavds_ingest] Skipping event: {exc}', file=sys.stderr)
    else:
        try:
            events = [adapter._parse_event(data)]
        except (KeyError, ValueError) as exc:
            print(f'[aavds_ingest] Failed to parse event: {exc}', file=sys.stderr)
            return 1

    if not events:
        print('[aavds_ingest] No events parsed from feed')
        return 0

    print(f'[aavds_ingest] Parsed {len(events)} AAVDS events')
    for evt in events[:5]:
        print(f'  {evt.event_id} @ ({evt.lat:.4f}, {evt.lng:.4f}) conf={evt.detection_confidence:.2f} type={evt.signal_type}')

    if len(events) > 5:
        print(f'  ... and {len(events) - 5} more')

    return 0


if __name__ == '__main__':
    sys.exit(main())
