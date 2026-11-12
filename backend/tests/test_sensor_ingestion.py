"""Tests for F7: Ground Radar Ingestion Layer."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.common.sensor_ingestion import (
    SensorEvent,
    SensorIngestionAdapter,
    SensorType,
    parse_sensor_csv,
    parse_sensor_json,
    parse_sensor_rest_payload,
    sensor_events_to_geojson,
    validate_sensor_event,
    SENSOR_TYPE_COLORS,
    SENSOR_TYPE_LABELS,
)


@pytest.fixture
def sample_csv():
    return (
        "event_id,timestamp,lat,lng,sensor_type,velocity_ms,mass_kg,depth_m,impact_pressure_kpa,rtsp_url,image_url\n"
        "evt_001,2024-01-15T06:30:00Z,27.35,88.50,radar,12.5,1500.0,2.3,85.0,rtsp://camera1/stream,https://img.example.com/evt001.jpg\n"
        "evt_002,2024-01-15T07:00:00Z,27.36,88.51,radar,8.0,800.0,1.5,45.0,,\n"
        "evt_003,2024-01-15T07:15:00Z,27.37,88.52,geophone,,,,,,\n"
    )


@pytest.fixture
def sample_json():
    return json.dumps([
        {
            "event_id": "evt_101",
            "timestamp": "2024-01-15T08:00:00Z",
            "lat": 27.40,
            "lng": 88.55,
            "sensor_type": "radar",
            "velocity_ms": 15.0,
            "mass_kg": 2000.0,
            "depth_m": 3.0,
            "impact_pressure_kpa": 120.0,
            "rtsp_url": "rtsp://camera2/stream",
            "image_url": None,
        },
        {
            "event_id": "evt_102",
            "timestamp": "2024-01-15T08:30:00Z",
            "lat": 27.41,
            "lng": 88.56,
            "sensor_type": "geophone",
        },
    ])


@pytest.fixture
def sample_rest_payload():
    return {
        "status": "ok",
        "data": {
            "events": [
                {
                    "event_id": "evt_201",
                    "timestamp": "2024-01-15T09:00:00Z",
                    "lat": 27.45,
                    "lng": 88.60,
                    "sensor_type": "radar",
                    "velocity_ms": 20.0,
                    "mass_kg": 3000.0,
                    "depth_m": 4.0,
                    "impact_pressure_kpa": 200.0,
                },
                {
                    "event_id": "evt_202",
                    "timestamp": "2024-01-15T09:15:00Z",
                    "lat": 27.46,
                    "lng": 88.61,
                    "sensor_type": "stmet",
                    "velocity_ms": 5.0,
                },
            ],
        },
    }


@pytest.fixture
def sample_event():
    return SensorEvent(
        event_id="evt_test",
        timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        lat=27.35,
        lng=88.50,
        sensor_type=SensorType.RADAR,
        velocity_ms=12.5,
        mass_kg=1500.0,
        depth_m=2.3,
        impact_pressure_kpa=85.0,
        rtsp_url="rtsp://camera1/stream",
        image_url="https://img.example.com/evt_test.jpg",
    )


class TestParseSensorCSV:
    def test_parse_radar_events(self, sample_csv):
        events = parse_sensor_csv(sample_csv)
        assert len(events) == 3
        assert events[0].event_id == "evt_001"
        assert events[0].sensor_type == SensorType.RADAR
        assert events[0].velocity_ms == 12.5
        assert events[0].mass_kg == 1500.0
        assert events[0].rtsp_url == "rtsp://camera1/stream"

    def test_parse_handles_missing_optional_fields(self, sample_csv):
        events = parse_sensor_csv(sample_csv)
        evt3 = events[2]
        assert evt3.sensor_type == SensorType.GEOPHONE
        assert evt3.velocity_ms is None
        assert evt3.mass_kg is None
        assert evt3.rtsp_url is None

    def test_parse_skips_invalid_rows(self):
        csv_data = (
            "event_id,timestamp,lat,lng,sensor_type\n"
            "evt_001,2024-01-15T06:30:00Z,27.35,88.50,radar\n"
            ",2024-01-15T06:30:00Z,27.35,88.50,radar\n"
            "evt_002,not-a-timestamp,27.35,88.50,radar\n"
        )
        events = parse_sensor_csv(csv_data)
        assert len(events) == 1
        assert events[0].event_id == "evt_001"

    def test_parse_empty_csv(self):
        events = parse_sensor_csv("event_id,timestamp,lat,lng\n")
        assert len(events) == 0


class TestParseSensorJSON:
    def test_parse_json_array(self, sample_json):
        events = parse_sensor_json(sample_json)
        assert len(events) == 2
        assert events[0].event_id == "evt_101"
        assert events[0].velocity_ms == 15.0
        assert events[1].sensor_type == SensorType.GEOPHONE

    def test_parse_json_with_events_key(self):
        data = json.dumps({
            "events": [
                {"event_id": "e1", "timestamp": "2024-01-15T10:00:00Z", "lat": 27.0, "lng": 88.0, "sensor_type": "radar"},
            ],
        })
        events = parse_sensor_json(data)
        assert len(events) == 1
        assert events[0].event_id == "e1"

    def test_parse_json_dict_input(self):
        data = {"events": [{"event_id": "e2", "timestamp": "2024-01-15T10:00:00Z", "lat": 27.0, "lng": 88.0}]}
        events = parse_sensor_json(data)
        assert len(events) == 1

    def test_parse_empty_json(self):
        events = parse_sensor_json("[]")
        assert len(events) == 0

    def test_parse_mixed_sensor_types(self, sample_json):
        events = parse_sensor_json(sample_json)
        types = {e.sensor_type for e in events}
        assert SensorType.RADAR in types
        assert SensorType.GEOPHONE in types


class TestParseSensorRestPayload:
    def test_parse_rest_with_data_events(self, sample_rest_payload):
        events = parse_sensor_rest_payload(sample_rest_payload)
        assert len(events) == 2
        assert events[0].event_id == "evt_201"
        assert events[0].velocity_ms == 20.0
        assert events[1].sensor_type == SensorType.STMET

    def test_parse_rest_with_results_key(self):
        payload = {
            "results": [
                {"event_id": "r1", "timestamp": "2024-01-15T10:00:00Z", "lat": 27.0, "lng": 88.0, "sensor_type": "mpp"},
            ],
        }
        events = parse_sensor_rest_payload(payload)
        assert len(events) == 1
        assert events[0].event_id == "r1"
        assert events[0].sensor_type == SensorType.MPP

    def test_parse_rest_with_bare_data_list(self):
        payload = {
            "data": [
                {"event_id": "d1", "timestamp": "2024-01-15T10:00:00Z", "lat": 27.0, "lng": 88.0},
            ],
        }
        events = parse_sensor_rest_payload(payload)
        assert len(events) == 1
        assert events[0].event_id == "d1"

    def test_parse_rest_empty(self):
        events = parse_sensor_rest_payload({})
        assert len(events) == 0


class TestValidateSensorEvent:
    def test_valid_event_no_errors(self, sample_event):
        errors = validate_sensor_event(sample_event)
        assert len(errors) == 0

    def test_missing_event_id(self):
        event = SensorEvent(
            event_id="",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
        )
        errors = validate_sensor_event(event)
        assert any("event_id" in e for e in errors)

    def test_invalid_latitude(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=999.0,
            lng=88.0,
        )
        errors = validate_sensor_event(event)
        assert any("latitude" in e for e in errors)

    def test_invalid_longitude(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=27.0,
            lng=999.0,
        )
        errors = validate_sensor_event(event)
        assert any("longitude" in e for e in errors)

    def test_negative_velocity(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
            velocity_ms=-5.0,
        )
        errors = validate_sensor_event(event)
        assert any("velocity" in e for e in errors)

    def test_negative_mass(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
            mass_kg=-100.0,
        )
        errors = validate_sensor_event(event)
        assert any("mass" in e for e in errors)


class TestSensorEventsToGeoJSON:
    def test_geojson_structure(self, sample_event):
        geojson = sensor_events_to_geojson([sample_event])
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [88.50, 27.35]
        assert feature["properties"]["event_id"] == "evt_test"
        assert "lat" not in feature["properties"]
        assert "lng" not in feature["properties"]

    def test_geojson_multiple_events(self, sample_event):
        events = [
            sample_event,
            SensorEvent(
                event_id="evt_2",
                timestamp=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
                lat=27.40,
                lng=88.55,
                sensor_type=SensorType.GEOPHONE,
            ),
        ]
        geojson = sensor_events_to_geojson(events)
        assert len(geojson["features"]) == 2

    def test_geojson_empty(self):
        geojson = sensor_events_to_geojson([])
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 0


class TestSensorIngestionAdapter:
    def test_auto_detect_csv(self, sample_csv):
        adapter = SensorIngestionAdapter(mode="auto")
        events = adapter.ingest(sample_csv)
        assert len(events) == 3
        assert events[0].event_id == "evt_001"

    def test_auto_detect_json(self, sample_json):
        adapter = SensorIngestionAdapter(mode="auto")
        events = adapter.ingest(sample_json)
        assert len(events) == 2
        assert events[0].event_id == "evt_101"

    def test_auto_detect_rest_dict(self, sample_rest_payload):
        adapter = SensorIngestionAdapter(mode="auto")
        events = adapter.ingest(sample_rest_payload)
        assert len(events) == 2
        assert events[0].event_id == "evt_201"

    def test_csv_mode(self, sample_csv):
        adapter = SensorIngestionAdapter(mode="csv")
        events = adapter.ingest(sample_csv)
        assert len(events) == 3

    def test_json_mode(self, sample_json):
        adapter = SensorIngestionAdapter(mode="json")
        events = adapter.ingest(sample_json)
        assert len(events) == 2

    def test_rest_mode(self, sample_rest_payload):
        adapter = SensorIngestionAdapter(mode="rest")
        events = adapter.ingest(sample_rest_payload)
        assert len(events) == 2

    def test_empty_input(self):
        adapter = SensorIngestionAdapter(mode="auto")
        assert adapter.ingest("") == []
        assert adapter.ingest([]) == []


class TestSensorEventProperties:
    def test_color_property(self, sample_event):
        assert sample_event.color == SENSOR_TYPE_COLORS["radar"]

    def test_label_property(self, sample_event):
        assert sample_event.label == SENSOR_TYPE_LABELS["radar"]

    def test_unknown_sensor_color(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
            sensor_type=SensorType.UNKNOWN,
        )
        assert event.color == SENSOR_TYPE_COLORS["unknown"]

    def test_to_dict(self, sample_event):
        d = sample_event.to_dict()
        assert d["event_id"] == "evt_test"
        assert d["sensor_type"] == "radar"
        assert d["velocity_ms"] == 12.5
        assert d["color"] == SENSOR_TYPE_COLORS["radar"]
        assert d["label"] == SENSOR_TYPE_LABELS["radar"]

    def test_metadata_preserved(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
            metadata={"custom_field": "value", "station": "north_sikkim"},
        )
        d = event.to_dict()
        assert d["metadata"]["custom_field"] == "value"
        assert d["metadata"]["station"] == "north_sikkim"


class TestTimestampParsing:
    def test_iso_with_z(self):
        event = SensorEvent(
            event_id="e1",
            timestamp=datetime(2024, 1, 15, 6, 30, 0, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
        )
        assert event.timestamp.tzinfo is not None

    def test_unix_timestamp(self):
        from backend.common.sensor_ingestion import _parse_timestamp
        dt = _parse_timestamp(1705307400)
        assert dt.year == 2024
