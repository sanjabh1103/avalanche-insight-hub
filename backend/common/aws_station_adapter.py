"""AWS (Automatic Weather Station) live feed adapter.

Builds on the existing eDMRG adapter field mapping to ingest live AWS
station CSV/JSON feeds. Designed for Partner pilot data contract.

Env flags:
  AWS_STATION_FEED_URL — URL for live AWS station feed
  AWS_STATION_FEED_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

AWS_STATION_FEED_ENABLED = os.getenv(
    'AWS_STATION_FEED_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}

AWS_STATION_FEED_URL = os.getenv('AWS_STATION_FEED_URL', '')


def fetch_aws_feed(
    feed_url: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch and parse AWS station observations from a live feed.

    Supports CSV and JSON formats (auto-detected from Content-Type).
    Returns empty list if disabled or fetch fails.
    """
    if not AWS_STATION_FEED_ENABLED:
        return []

    url = feed_url or AWS_STATION_FEED_URL
    if not url:
        return []

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AvalancheInsightHub/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get('Content-Type', '')
            data = resp.read().decode('utf-8', errors='ignore')

        if 'json' in content_type or url.endswith('.json'):
            return _parse_json_feed(data)
        else:
            return _parse_csv_feed(data)
    except Exception:
        return []


def _parse_csv_feed(data: str) -> list[dict[str, Any]]:
    """Parse CSV-format AWS station feed.

    Rejects rows where required numeric fields are missing or non-numeric
    instead of defaulting to 0.
    """
    records: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(data))
    numeric_fields = [
        'air_temp_c', 'snow_depth_cm', 'snowfall_cm',
        'wind_speed_ms', 'wind_dir_deg', 'precipitation_mm',
    ]
    for row in reader:
        station_id = (row.get('station_id') or '').strip()
        observed_at = (row.get('observed_at') or '').strip()
        if not station_id or not observed_at:
            continue
        record: dict[str, Any] = {
            'station_id': station_id,
            'observed_at': observed_at,
            'source': 'aws_live_feed',
        }
        has_any_numeric = False
        skip_row = False
        for field_name in numeric_fields:
            raw_val = row.get(field_name)
            if raw_val is None or raw_val == '':
                continue
            try:
                record[field_name] = float(raw_val)
                has_any_numeric = True
            except (TypeError, ValueError):
                skip_row = True
                break
        if skip_row or not has_any_numeric:
            continue
        for opt_field in ('latitude', 'longitude', 'elevation_m'):
            raw_val = row.get(opt_field)
            if raw_val is None or raw_val == '':
                continue
            try:
                record[opt_field] = float(raw_val)
            except (TypeError, ValueError):
                pass
        records.append(record)
    return records


def _parse_json_feed(data: str) -> list[dict[str, Any]]:
    """Parse JSON-format AWS station feed."""
    try:
        payload = json.loads(data)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and 'observations' in payload:
            return payload['observations']
        return [payload] if isinstance(payload, dict) else []
    except (json.JSONDecodeError, TypeError):
        return []


def validate_aws_feed_schema(records: list[dict[str, Any]]) -> list[str]:
    """Validate that AWS feed records have required fields.

    Returns list of validation errors (empty = valid).
    """
    required_fields = {'station_id', 'observed_at'}
    errors: list[str] = []
    for i, record in enumerate(records):
        missing = required_fields - set(record.keys())
        if missing:
            errors.append(f'Record {i}: missing fields {missing}')
            continue
        has_numeric = any(
            isinstance(record.get(k), (int, float))
            for k in ('air_temp_c', 'snow_depth_cm', 'snowfall_cm',
                      'wind_speed_ms', 'wind_dir_deg', 'precipitation_mm')
        )
        if not has_numeric:
            errors.append(f'Record {i}: no numeric measurement fields present')
    return errors
