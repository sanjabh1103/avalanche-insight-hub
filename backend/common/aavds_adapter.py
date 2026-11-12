"""AAVDS: Auto-Luminescent Victim Detection System Adapter.

Integration scaffold for IIT Kanpur's AAVDS — avalanche victim detection
via auto-luminescent signals. Ingests detection alerts from file or REST API
and produces events for map overlay and search-and-rescue narrative.

Follows the SensorIngestionAdapter pattern from F7 (sensor_ingestion.py).

Env flags:
  AAVDS_ENABLED — master switch (default: false)
  AAVDS_FEED_URL — optional REST endpoint for AAVDS detection events
"""
from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

AAVDS_ENABLED = os.getenv('AAVDS_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
AAVDS_FEED_URL = os.getenv('AAVDS_FEED_URL', '')


@dataclass(frozen=True)
class AAVDSEvent:
    """A single AAVDS detection event."""
    event_id: str
    timestamp: datetime
    lat: float
    lng: float
    detection_confidence: float  # 0-1
    signal_type: str  # 'auto_luminescent', 'thermal', 'rf'
    victim_id: str | None = None
    burial_depth_m: float | None = None
    signal_strength_db: float | None = None
    source: str = 'aavds'


@dataclass
class AAVDSAdapter:
    """Adapter for ingesting AAVDS detection events.

    Supports file-based (JSON) and REST API ingestion modes.
    Follows the SensorIngestionAdapter pattern from F7.
    """
    enabled: bool = field(default_factory=lambda: AAVDS_ENABLED)
    feed_url: str = field(default_factory=lambda: AAVDS_FEED_URL)
    events: list[AAVDSEvent] = field(default_factory=list)

    def ingest_file(self, path: str) -> list[AAVDSEvent]:
        """Ingest AAVDS events from a JSON file.

        Expected format: list of dicts with event_id, timestamp, lat, lng,
        detection_confidence, signal_type, and optional victim_id.

        Args:
            path: Path to JSON file

        Returns:
            List of parsed AAVDSEvent objects
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, dict):
            data = [data]

        events: list[AAVDSEvent] = []
        for item in data:
            try:
                event = self._parse_event(item)
                events.append(event)
            except (KeyError, ValueError) as exc:
                logger.warning('Skipping AAVDS event: %s', exc)

        self.events.extend(events)
        logger.info('Ingested %d AAVDS events from %s', len(events), path)
        return events

    def ingest_rest(self, url: str | None = None) -> list[AAVDSEvent]:
        """Ingest AAVDS events from a REST API endpoint.

        Args:
            url: Optional URL override (uses feed_url if not provided)

        Returns:
            List of parsed AAVDSEvent objects
        """
        import urllib.request

        target_url = url or self.feed_url
        if not target_url:
            logger.warning('No AAVDS feed URL configured')
            return []

        try:
            with urllib.request.urlopen(target_url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            logger.error('Failed to fetch AAVDS feed: %s', exc)
            return []

        if isinstance(data, dict):
            data = [data]

        events: list[AAVDSEvent] = []
        for item in data:
            try:
                event = self._parse_event(item)
                events.append(event)
            except (KeyError, ValueError) as exc:
                logger.warning('Skipping AAVDS event: %s', exc)

        self.events.extend(events)
        logger.info('Ingested %d AAVDS events from REST API', len(events))
        return events

    def ingest_dict(self, data: dict[str, Any]) -> AAVDSEvent:
        """Ingest a single AAVDS event from a dict.

        Args:
            data: Event dict

        Returns:
            Parsed AAVDSEvent

        Raises:
            ValueError: If required fields are missing
        """
        event = self._parse_event(data)
        self.events.append(event)
        return event

    def _parse_event(self, data: dict[str, Any]) -> AAVDSEvent:
        """Parse a dict into an AAVDSEvent.

        Args:
            data: Event dict

        Returns:
            AAVDSEvent

        Raises:
            KeyError: If required fields are missing
            ValueError: If field values are invalid
        """
        event_id = str(data['event_id'])
        lat = float(data['lat'])
        lng = float(data['lng'])
        confidence = float(data.get('detection_confidence', 0.0))
        signal_type = str(data.get('signal_type', 'auto_luminescent'))

        if not (-90 <= lat <= 90):
            raise ValueError(f'Invalid latitude: {lat}')
        if not (-180 <= lng <= 180):
            raise ValueError(f'Invalid longitude: {lng}')
        if not (0 <= confidence <= 1):
            raise ValueError(f'Invalid confidence: {confidence}')

        # Parse timestamp
        ts_raw = data.get('timestamp')
        if isinstance(ts_raw, str):
            timestamp = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
        elif isinstance(ts_raw, (int, float)):
            timestamp = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        return AAVDSEvent(
            event_id=event_id,
            timestamp=timestamp,
            lat=lat,
            lng=lng,
            detection_confidence=confidence,
            signal_type=signal_type,
            victim_id=data.get('victim_id'),
            burial_depth_m=float(data['burial_depth_m']) if 'burial_depth_m' in data else None,
            signal_strength_db=float(data['signal_strength_db']) if 'signal_strength_db' in data else None,
        )

    def get_events_in_bounds(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lng: float,
        max_lng: float,
    ) -> list[AAVDSEvent]:
        """Filter events within geographic bounds.

        Args:
            min_lat, max_lat, min_lng, max_lng: Bounding box

        Returns:
            List of events within bounds
        """
        return [
            e for e in self.events
            if min_lat <= e.lat <= max_lat and min_lng <= e.lng <= max_lng
        ]

    def get_high_confidence_events(self, threshold: float = 0.7) -> list[AAVDSEvent]:
        """Get events above a confidence threshold.

        Args:
            threshold: Minimum confidence (0-1)

        Returns:
            List of high-confidence events
        """
        return [e for e in self.events if e.detection_confidence >= threshold]

    def to_geojson(self) -> dict[str, Any]:
        """Convert events to GeoJSON FeatureCollection for map overlay.

        Returns:
            GeoJSON FeatureCollection
        """
        features: list[dict[str, Any]] = []
        for event in self.events:
            color = '#22c55e' if event.detection_confidence > 0.8 else \
                    '#f59e0b' if event.detection_confidence > 0.5 else '#ef4444'
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [event.lng, event.lat],
                },
                'properties': {
                    'event_id': event.event_id,
                    'timestamp': event.timestamp.isoformat(),
                    'detection_confidence': event.detection_confidence,
                    'signal_type': event.signal_type,
                    'victim_id': event.victim_id,
                    'burial_depth_m': event.burial_depth_m,
                    'color': color,
                    'source': 'aavds',
                },
            })

        return {
            'type': 'FeatureCollection',
            'features': features,
        }

    def clear(self) -> None:
        """Clear all stored events."""
        self.events.clear()

    def get_status(self) -> dict[str, Any]:
        """Get adapter status."""
        return {
            'enabled': self.enabled,
            'feed_url': self.feed_url,
            'event_count': len(self.events),
            'high_confidence_count': len(self.get_high_confidence_events()),
        }
