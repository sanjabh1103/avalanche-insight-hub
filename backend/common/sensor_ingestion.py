"""F7: Ground Radar Ingestion Layer.

Pluggable sensor ingestion module supporting three modes:
1. File drop (CSV/JSON)
2. Batch export (JSON)
3. REST/JSON API

Handles radar event streams with velocity, mass, depth, impact pressure,
RTSP stream URL, and still image URL. Extensible to geophone/STMET/MPP data.

Based on Gemini v2 North Sikkim radar deployment schema (2022, 3s detection,
2km², all-weather). JSON REST payload schema includes velocity, mass, depth,
impact pressure, RTSP stream, still image URL.
"""
from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SENSOR_FEED_URL = os.getenv('SENSOR_FEED_URL', '')
SENSOR_ENABLED = os.getenv('SENSOR_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}


class SensorType(str, Enum):
    RADAR = "radar"
    GEOPHONE = "geophone"
    STMET = "stmet"
    MPP = "mpp"
    UNKNOWN = "unknown"


SENSOR_TYPE_COLORS: dict[str, str] = {
    "radar": "#ef4444",
    "geophone": "#3b82f6",
    "stmet": "#22c55e",
    "mpp": "#f59e0b",
    "unknown": "#6b7280",
}

SENSOR_TYPE_LABELS: dict[str, str] = {
    "radar": "Ground Radar",
    "geophone": "Geophone",
    "stmet": "STMET",
    "mpp": "MPP Probe",
    "unknown": "Unknown Sensor",
}

REQUIRED_FIELDS = {"event_id", "timestamp", "lat", "lng"}
OPTIONAL_NUMERIC_FIELDS = {
    "velocity_ms",
    "mass_kg",
    "depth_m",
    "impact_pressure_kpa",
}
OPTIONAL_STRING_FIELDS = {"rtsp_url", "image_url"}


@dataclass(frozen=True)
class SensorEvent:
    event_id: str
    timestamp: datetime
    lat: float
    lng: float
    sensor_type: SensorType = SensorType.UNKNOWN
    velocity_ms: float | None = None
    mass_kg: float | None = None
    depth_m: float | None = None
    impact_pressure_kpa: float | None = None
    rtsp_url: str | None = None
    image_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def color(self) -> str:
        return SENSOR_TYPE_COLORS.get(self.sensor_type.value, SENSOR_TYPE_COLORS["unknown"])

    @property
    def label(self) -> str:
        return SENSOR_TYPE_LABELS.get(self.sensor_type.value, SENSOR_TYPE_LABELS["unknown"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "lat": self.lat,
            "lng": self.lng,
            "sensor_type": self.sensor_type.value,
            "velocity_ms": self.velocity_ms,
            "mass_kg": self.mass_kg,
            "depth_m": self.depth_m,
            "impact_pressure_kpa": self.impact_pressure_kpa,
            "rtsp_url": self.rtsp_url,
            "image_url": self.image_url,
            "metadata": dict(self.metadata),
            "color": self.color,
            "label": self.label,
        }


def _parse_timestamp(raw: Any) -> datetime:
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        ts = raw.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ):
            try:
                dt = datetime.strptime(ts, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            pass
    raise ValueError(f"Unparseable timestamp: {raw!r}")


def _parse_sensor_type(raw: Any) -> SensorType:
    if raw is None:
        return SensorType.UNKNOWN
    s = str(raw).strip().lower()
    try:
        return SensorType(s)
    except ValueError:
        return SensorType.UNKNOWN


def _parse_optional_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _parse_optional_str(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    return str(raw)


def _row_to_event(row: dict[str, Any]) -> SensorEvent:
    event_id = str(row.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("Missing required field: event_id")

    timestamp = _parse_timestamp(row.get("timestamp"))
    lat = float(row.get("lat") or row.get("latitude") or 0.0)
    lng = float(row.get("lng") or row.get("longitude") or 0.0)

    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Invalid latitude: {lat}")
    if not (-180.0 <= lng <= 180.0):
        raise ValueError(f"Invalid longitude: {lng}")

    sensor_type = _parse_sensor_type(row.get("sensor_type") or row.get("type"))

    extra: dict[str, Any] = {}
    known_keys = REQUIRED_FIELDS | OPTIONAL_NUMERIC_FIELDS | OPTIONAL_STRING_FIELDS | {"sensor_type", "type", "latitude", "longitude"}
    for k, v in row.items():
        if k not in known_keys and v is not None and v != "":
            extra[k] = v

    return SensorEvent(
        event_id=event_id,
        timestamp=timestamp,
        lat=lat,
        lng=lng,
        sensor_type=sensor_type,
        velocity_ms=_parse_optional_float(row.get("velocity_ms") or row.get("velocity")),
        mass_kg=_parse_optional_float(row.get("mass_kg") or row.get("mass")),
        depth_m=_parse_optional_float(row.get("depth_m") or row.get("depth")),
        impact_pressure_kpa=_parse_optional_float(row.get("impact_pressure_kpa") or row.get("impact_pressure")),
        rtsp_url=_parse_optional_str(row.get("rtsp_url")),
        image_url=_parse_optional_str(row.get("image_url")),
        metadata=extra,
    )


def parse_sensor_csv(data: str) -> list[SensorEvent]:
    """Parse CSV sensor data (file drop mode).

    Expected columns: event_id, timestamp, lat, lng, sensor_type,
    velocity_ms, mass_kg, depth_m, impact_pressure_kpa, rtsp_url, image_url
    """
    reader = csv.DictReader(io.StringIO(data))
    events: list[SensorEvent] = []
    for row in reader:
        try:
            events.append(_row_to_event(row))
        except (ValueError, KeyError):
            continue
    return events


def parse_sensor_json(data: str | bytes | dict[str, Any] | list[Any]) -> list[SensorEvent]:
    """Parse JSON sensor data (batch export mode).

    Accepts a JSON array of event objects or a JSON object with an 'events' key.
    """
    if isinstance(data, (str, bytes)):
        parsed = json.loads(data)
    else:
        parsed = data

    if isinstance(parsed, dict) and "events" in parsed:
        items = parsed["events"]
    elif isinstance(parsed, list):
        items = parsed
    else:
        return []

    events: list[SensorEvent] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            events.append(_row_to_event(item))
        except (ValueError, KeyError):
            continue
    return events


def parse_sensor_rest_payload(payload: dict[str, Any]) -> list[SensorEvent]:
    """Parse REST API response payload.

    Handles common REST response wrappers:
    - { "data": { "events": [...] } }
    - { "data": [...] }
    - { "events": [...] }
    - { "results": [...] }
    - [...] (bare array)
    """
    if not isinstance(payload, dict):
        if isinstance(payload, list):
            return [e for item in payload if isinstance(item, dict) for e in [(_row_to_event(item) if item.get("event_id") else None)] if e is not None]
        return []

    for key in ("events", "results", "data"):
        val = payload.get(key)
        if isinstance(val, list):
            events: list[SensorEvent] = []
            for item in val:
                if not isinstance(item, dict):
                    continue
                try:
                    events.append(_row_to_event(item))
                except (ValueError, KeyError):
                    continue
            return events
        if isinstance(val, dict):
            inner = val.get("events") or val.get("results")
            if isinstance(inner, list):
                events = []
                for item in inner:
                    if not isinstance(item, dict):
                        continue
                    try:
                        events.append(_row_to_event(item))
                    except (ValueError, KeyError):
                        continue
                return events

    return []


def validate_sensor_event(event: SensorEvent) -> list[str]:
    """Validate a sensor event and return a list of validation error messages."""
    errors: list[str] = []
    if not event.event_id:
        errors.append("event_id is required")
    if not (-90.0 <= event.lat <= 90.0):
        errors.append(f"Invalid latitude: {event.lat}")
    if not (-180.0 <= event.lng <= 180.0):
        errors.append(f"Invalid longitude: {event.lng}")
    if event.timestamp is None:
        errors.append("timestamp is required")
    if event.velocity_ms is not None and event.velocity_ms < 0:
        errors.append(f"velocity_ms cannot be negative: {event.velocity_ms}")
    if event.mass_kg is not None and event.mass_kg < 0:
        errors.append(f"mass_kg cannot be negative: {event.mass_kg}")
    if event.depth_m is not None and event.depth_m < 0:
        errors.append(f"depth_m cannot be negative: {event.depth_m}")
    if event.impact_pressure_kpa is not None and event.impact_pressure_kpa < 0:
        errors.append(f"impact_pressure_kpa cannot be negative: {event.impact_pressure_kpa}")
    return errors


def sensor_events_to_geojson(events: list[SensorEvent]) -> dict[str, Any]:
    """Convert sensor events to GeoJSON FeatureCollection for map overlay."""
    features: list[dict[str, Any]] = []
    for event in events:
        properties = event.to_dict()
        properties.pop("lat", None)
        properties.pop("lng", None)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [event.lng, event.lat],
            },
            "properties": properties,
        })
    return {
        "type": "FeatureCollection",
        "features": features,
    }


class SensorIngestionAdapter:
    """Pluggable adapter that auto-detects format and ingests sensor data.

    Modes:
    - 'csv': CSV file drop
    - 'json': JSON batch export
    - 'rest': REST API JSON payload
    - 'auto': Auto-detect format (default)
    """

    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode

    def ingest(self, data: str | bytes | dict[str, Any] | list[Any]) -> list[SensorEvent]:
        if self.mode == "csv":
            if isinstance(data, (str, bytes)):
                return parse_sensor_csv(data if isinstance(data, str) else data.decode("utf-8"))
            return []
        elif self.mode == "json":
            return parse_sensor_json(data)
        elif self.mode == "rest":
            if isinstance(data, dict):
                return parse_sensor_rest_payload(data)
            if isinstance(data, (str, bytes)):
                return parse_sensor_rest_payload(json.loads(data if isinstance(data, str) else data.decode("utf-8")))
            return []
        else:
            return self._auto_detect(data)

    def _auto_detect(self, data: str | bytes | dict[str, Any] | list[Any]) -> list[SensorEvent]:
        if isinstance(data, list):
            return parse_sensor_json(data)
        if isinstance(data, dict):
            return parse_sensor_rest_payload(data)
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        if isinstance(data, str):
            stripped = data.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                return parse_sensor_json(stripped)
            else:
                return parse_sensor_csv(stripped)
        return []


def _validate_sensor_feed_url(url: str) -> bool:
    """Validate that a sensor feed URL is safe to fetch.

    Allows only http/https schemes and rejects localhost/private IPs
    unless explicitly permitted via SENSOR_FEED_ALLOW_PRIVATE env flag.
    """
    import ipaddress
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {'http', 'https'}:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    allow_private = os.getenv('SENSOR_FEED_ALLOW_PRIVATE', 'false').lower() not in {'0', 'false', 'off', 'no'}
    if not allow_private:
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            if hostname in {'localhost', '0.0.0.0'}:
                return False

    return True


def fetch_sensor_events_rest(url: str | None = None) -> list[SensorEvent]:
    """Fetch sensor events from a REST API endpoint.

    Args:
        url: Optional URL override (uses SENSOR_FEED_URL env if not provided)

    Returns:
        List of parsed SensorEvent objects
    """
    import urllib.request

    target_url = url or SENSOR_FEED_URL
    if not target_url:
        return []

    if not _validate_sensor_feed_url(target_url):
        print(f'[sensor_ingestion] Rejected invalid or private feed URL: {target_url}', file=__import__('sys').stderr)
        return []

    try:
        with urllib.request.urlopen(target_url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        return parse_sensor_rest_payload(data)
    except Exception as exc:
        print(f'[sensor_ingestion] REST fetch failed for {target_url}: {exc}', file=__import__('sys').stderr)
        return []
