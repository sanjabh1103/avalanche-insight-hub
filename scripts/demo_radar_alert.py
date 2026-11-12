#!/usr/bin/env python3
"""Demo: Ground-based radar alert ingestion using Partner's JSON schema.

Creates a RadarAlertAdapter that parses Partner ground radar alert JSON,
extracts detection events, and converts them to pipeline-compatible format.

Uses the exact JSON schema from Partner's Sikkim ground-based radar integration
as documented in DR_Geminiv2.md research.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RadarAlertEvent:
    """Single radar detection event from Partner ground radar."""
    alert_id: str
    timestamp: datetime
    lat: float
    lng: float
    radar_type: str        # 'ground_based_xband', 'ground_based_kuband'
    detection_type: str    # 'avalanche', 'debris_flow', 'rockfall'
    confidence: float      # 0-1
    range_m: float         # distance from radar
    azimuth_deg: float     # bearing from radar
    velocity_ms: float | None = None
    volume_m3: float | None = None
    source: str = 'Partner_radar'


@dataclass
class RadarAlertAdapter:
    """Adapter for ingesting Partner ground-based radar alerts."""
    events: list[RadarAlertEvent] = field(default_factory=list)

    def ingest_json(self, data: str | bytes | dict[str, Any]) -> list[RadarAlertEvent]:
        """Ingest radar alert from Partner JSON format.

        Expected Partner JSON schema:
        {
            "alert_id": "RADAR-2026-001",
            "timestamp": "2026-01-15T08:30:00Z",
            "radar_type": "ground_based_xband",
            "station_id": "Sikkim-R1",
            "detections": [
                {
                    "detection_type": "avalanche",
                    "lat": 27.5,
                    "lng": 88.5,
                    "confidence": 0.92,
                    "range_m": 1200,
                    "azimuth_deg": 45.0,
                    "velocity_ms": 25.0,
                    "volume_m3": 50000
                }
            ]
        }
        """
        if isinstance(data, (str, bytes)):
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            parsed = json.loads(data)
        else:
            parsed = data

        alert_id = str(parsed.get('alert_id', ''))
        if not alert_id:
            raise ValueError('Missing alert_id')

        ts_raw = parsed.get('timestamp')
        if isinstance(ts_raw, str):
            timestamp = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
        else:
            timestamp = datetime.now(timezone.utc)

        radar_type = str(parsed.get('radar_type', 'ground_based_xband'))
        detections = parsed.get('detections', [])
        if not isinstance(detections, list):
            raise ValueError('detections must be a list')

        new_events = []
        for i, det in enumerate(detections):
            if not isinstance(det, dict):
                continue
            event = RadarAlertEvent(
                alert_id=f'{alert_id}-{i}',
                timestamp=timestamp,
                lat=float(det['lat']),
                lng=float(det['lng']),
                radar_type=radar_type,
                detection_type=str(det.get('detection_type', 'avalanche')),
                confidence=float(det.get('confidence', 0.0)),
                range_m=float(det.get('range_m', 0.0)),
                azimuth_deg=float(det.get('azimuth_deg', 0.0)),
                velocity_ms=float(det.get('velocity_ms')) if det.get('velocity_ms') is not None else None,
                volume_m3=float(det.get('volume_m3')) if det.get('volume_m3') is not None else None,
            )
            self.events.append(event)
            new_events.append(event)

        return new_events

    def to_pipeline_events(self) -> list[dict[str, Any]]:
        """Convert stored events to pipeline-compatible detection dicts."""
        return [
            {
                'event_id': e.alert_id,
                'timestamp': e.timestamp.isoformat(),
                'lat': e.lat,
                'lng': e.lng,
                'source': e.source,
                'detection_type': e.detection_type,
                'confidence': e.confidence,
                'radar_type': e.radar_type,
                'range_m': e.range_m,
                'azimuth_deg': e.azimuth_deg,
                'velocity_ms': e.velocity_ms,
                'volume_m3': e.volume_m3,
            }
            for e in self.events
        ]


def main() -> int:
    print('=== Ground Radar Alert Ingestion Demo (Partner JSON Schema) ===\n')

    adapter = RadarAlertAdapter()

    # Synthetic Partner radar alert (Sikkim X-band)
    alert_json = json.dumps({
        'alert_id': 'RADAR-2026-001',
        'timestamp': '2026-01-15T08:30:00Z',
        'radar_type': 'ground_based_xband',
        'station_id': 'Sikkim-R1',
        'detections': [
            {
                'detection_type': 'avalanche',
                'lat': 27.5,
                'lng': 88.5,
                'confidence': 0.92,
                'range_m': 1200,
                'azimuth_deg': 45.0,
                'velocity_ms': 25.0,
                'volume_m3': 50000,
            },
            {
                'detection_type': 'avalanche',
                'lat': 27.52,
                'lng': 88.48,
                'confidence': 0.85,
                'range_m': 1800,
                'azimuth_deg': 52.0,
                'velocity_ms': 18.0,
                'volume_m3': 30000,
            },
            {
                'detection_type': 'debris_flow',
                'lat': 27.48,
                'lng': 88.52,
                'confidence': 0.78,
                'range_m': 2500,
                'azimuth_deg': 38.0,
                'velocity_ms': 12.0,
                'volume_m3': None,
            },
        ],
    })

    print(f'Ingesting Partner radar alert JSON...')
    events = adapter.ingest_json(alert_json)
    print(f'Parsed {len(events)} detection events from alert RADAR-2026-001')

    if len(events) != 3:
        print('FAIL: Expected 3 events')
        return 1
    print('PASS: 3 events ingested')

    print(f'\nEvent details:')
    for e in events:
        print(f'  {e.alert_id}: type={e.detection_type} lat={e.lat} lng={e.lng} '
              f'conf={e.confidence:.2f} range={e.range_m}m vel={e.velocity_ms}m/s vol={e.volume_m3}m3')

    # Convert to pipeline format
    print(f'\nPipeline-compatible format:')
    pipeline_events = adapter.to_pipeline_events()
    for pe in pipeline_events:
        print(f'  {pe["event_id"]}: {json.dumps(pe, indent=2)}')

    # Adversarial: missing alert_id
    print('\n=== Adversarial Check: Missing alert_id ===\n')
    try:
        adapter.ingest_json('{"detections": []}')
        print('FAIL: Missing alert_id was accepted')
        return 1
    except ValueError as e:
        print(f'PASS: Missing alert_id rejected: {e}')

    # Adversarial: empty detections
    print('\n=== Adversarial Check: Empty Detections ===\n')
    empty_events = adapter.ingest_json('{"alert_id": "RADAR-002", "detections": []}')
    print(f'Empty detections: {len(empty_events)} events')
    if empty_events:
        print('FAIL: Should return 0 events')
        return 1
    print('PASS: Empty detections returns 0 events')

    # Verify total events
    print(f'\nTotal events stored: {len(adapter.events)} (should be 3)')
    if len(adapter.events) != 3:
        print('FAIL: Event count mismatch')
        return 1
    print('PASS: Total events correct')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
