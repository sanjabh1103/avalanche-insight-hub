#!/usr/bin/env python3
"""Ingest ground sensor / geophone events from a configured feed URL.

Reads from SENSOR_FEED_URL env var. Fetches JSON events using
the sensor_ingestion module. When SENSOR_FEED_URL is not set,
exits with code 0 (no-op for CI).

Usage:
    python3 scripts/ingest_sensor_feed.py
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    feed_url = os.getenv('SENSOR_FEED_URL', '').strip()
    if not feed_url:
        print('[sensor_ingest] SENSOR_FEED_URL not set — skipping (no-op)')
        return 0

    from backend.common.sensor_ingestion import fetch_sensor_events_rest

    print(f'[sensor_ingest] Fetching from {feed_url}')
    events = fetch_sensor_events_rest(feed_url)

    if not events:
        print('[sensor_ingest] No events parsed from feed')
        return 0

    print(f'[sensor_ingest] Parsed {len(events)} sensor events')
    for evt in events[:5]:
        print(f'  {evt.event_id} @ ({evt.lat:.4f}, {evt.lng:.4f}) type={evt.sensor_type.value}')

    if len(events) > 5:
        print(f'  ... and {len(events) - 5} more')

    return 0


if __name__ == '__main__':
    sys.exit(main())
