#!/usr/bin/env python3
"""Demo: AAVDS adapter ingesting synthetic detection events.

Generates 3 synthetic AAVDS events (different confidence levels),
calls AAVDSAdapter.ingest_dict(), verifies events stored, prints summary.
Includes adversarial check: invalid lat/lng should be rejected.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from backend.common.aavds_adapter import AAVDSAdapter, AAVDSEvent


def main() -> int:
    print('=== AAVDS Adapter Demo ===\n')

    adapter = AAVDSAdapter()

    # Generate 3 synthetic events
    events_data = [
        {
            'event_id': 'AAVDS-001',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'lat': 28.0,
            'lng': 86.25,
            'detection_confidence': 0.95,
            'signal_type': 'auto_luminescent',
            'victim_id': 'V-001',
            'burial_depth_m': 1.5,
            'signal_strength_db': -42.0,
        },
        {
            'event_id': 'AAVDS-002',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'lat': 34.5,
            'lng': 76.75,
            'detection_confidence': 0.78,
            'signal_type': 'thermal',
            'victim_id': 'V-002',
            'burial_depth_m': 2.0,
            'signal_strength_db': -55.0,
        },
        {
            'event_id': 'AAVDS-003',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'lat': 35.5,
            'lng': 77.75,
            'detection_confidence': 0.62,
            'signal_type': 'rf',
            'burial_depth_m': 0.0,
            'signal_strength_db': -68.0,
        },
    ]

    print(f'Ingesting {len(events_data)} synthetic AAVDS events...')
    for data in events_data:
        event = adapter.ingest_dict(data)
        print(f'  {event.event_id}: lat={event.lat} lng={event.lng} conf={event.detection_confidence:.2f} type={event.signal_type} depth={event.burial_depth_m}m')

    print(f'\nTotal events stored: {len(adapter.events)}')
    if len(adapter.events) != 3:
        print('FAIL: Expected 3 events')
        return 1
    print('PASS: All 3 events ingested successfully')

    # Verify event attributes
    e0 = adapter.events[0]
    print(f'\nEvent details (first):')
    print(f'  event_id: {e0.event_id}')
    print(f'  timestamp: {e0.timestamp}')
    print(f'  lat/lng: ({e0.lat}, {e0.lng})')
    print(f'  confidence: {e0.detection_confidence}')
    print(f'  signal_type: {e0.signal_type}')
    print(f'  victim_id: {e0.victim_id}')
    print(f'  burial_depth_m: {e0.burial_depth_m}')
    print(f'  signal_strength_db: {e0.signal_strength_db}')
    print(f'  source: {e0.source}')

    # Adversarial check: invalid lat should be rejected
    print('\n=== Adversarial Check: Invalid Coordinates ===\n')
    try:
        adapter.ingest_dict({
            'event_id': 'BAD-001',
            'lat': 999.0,
            'lng': 86.25,
            'detection_confidence': 0.5,
        })
        print('FAIL: Invalid latitude was accepted')
        return 1
    except ValueError as e:
        print(f'PASS: Invalid latitude rejected: {e}')

    # Adversarial check: invalid confidence
    try:
        adapter.ingest_dict({
            'event_id': 'BAD-002',
            'lat': 28.0,
            'lng': 86.25,
            'detection_confidence': 1.5,
        })
        print('FAIL: Invalid confidence was accepted')
        return 1
    except ValueError as e:
        print(f'PASS: Invalid confidence rejected: {e}')

    print(f'\nTotal events after adversarial checks: {len(adapter.events)} (should still be 3)')
    if len(adapter.events) != 3:
        print('FAIL: Events count changed after rejected inputs')
        return 1
    print('PASS: Rejected events did not affect stored count')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
