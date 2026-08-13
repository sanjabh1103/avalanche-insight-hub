"""F20: eDMRG-Compatible Data Ingestion Adapter.

Parses Partner eDMRG telemetry from manned (3-hour) and AWS (1-hour) stations,
maps field names via a configurable JSON mapping file, and produces weather
sample dicts compatible with ``build_real_feature_row`` and
``sequence_matrix_from_samples``.

The eDMRG architecture is: Oracle DB → SNOWPACK 1D engine → MySQL → Partner intranet.
Stations report on two cadences:
  - Manned observatories: every 3 hours (synoptic)
  - Automatic Weather Stations (AWS): every 1 hour

This adapter provides the interoperability layer so that eDMRG telemetry can
feed the existing inference pipeline without changes to downstream code.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from backend.common.sequence_features import (
    DEFAULT_DAILY_STEPS,
    DEFAULT_HOURLY_STEPS,
    DYNAMIC_SEQUENCE_FEATURES,
    STATIC_SEQUENCE_FEATURES,
    SequenceBranches,
    extract_static_vector,
    extract_zone_onehot,
    sequence_matrix_from_samples,
)


EDMRG_DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[2] / 'config' / 'edmrg_field_mapping.json'

# Canonical field names used by our pipeline (build_real_feature_row / _dynamic_feature_snapshot)
PIPELINE_WEATHER_KEYS = {
    'temperature_2m',
    'windspeed_10m',
    'winddirection_10m',
    'snowfall_24h',
    'snowfall',
    'precipitation_24h',
    'precipitation',
    'snow_depth',
    'freezing_level_height',
}

# Mapping from eDMRG logical names → pipeline weather_sample keys
EDMRG_TO_PIPELINE = {
    'temperature_c': 'temperature_2m',
    'snow_depth_cm': 'snow_depth',
    'new_snow_cm': 'snowfall_24h',
    'wind_speed_ms': 'windspeed_10m',
    'wind_direction_deg': 'winddirection_10m',
    'precipitation_mm': 'precipitation_24h',
}


@dataclass(frozen=True)
class EdmrgRecord:
    """Single eDMRG telemetry observation from one station at one timestamp."""
    station_id: str
    timestamp: datetime
    cadence: str  # 'manned_3h' or 'aws_1h'
    fields: dict[str, float] = field(default_factory=dict)


def load_field_mapping(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """Load the eDMRG → pipeline field mapping from JSON.

    Returns a dict with keys ``manned_3h`` and ``aws_1h``, each mapping
    eDMRG logical field names to raw column names in the source data.
    """
    mapping_path = Path(path) if path else EDMRG_DEFAULT_MAPPING_PATH
    if not mapping_path.exists():
        raise FileNotFoundError(f'eDMRG field mapping not found: {mapping_path}')
    raw = json.loads(mapping_path.read_text(encoding='utf-8'))
    for cadence in ('manned_3h', 'aws_1h'):
        if cadence not in raw:
            raise ValueError(f'eDMRG mapping missing required cadence key: {cadence}')
        if not isinstance(raw[cadence], dict):
            raise ValueError(f'eDMRG mapping for {cadence} must be an object')
    return raw


def _parse_timestamp(value: str | Any) -> datetime:
    """Parse a timestamp from string or datetime."""
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        # Try ISO format first
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            # Try common eDMRG formats
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M'):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f'Cannot parse timestamp: {raw}')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any) -> float:
    """Convert value to float, returning 0.0 for None/empty/invalid."""
    if value is None:
        return 0.0
    try:
        f = float(value)
        if not np.isfinite(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def _extract_fields(
    row: dict[str, Any],
    mapping: dict[str, str],
) -> dict[str, float]:
    """Extract mapped fields from a raw data row using the field mapping.

    The mapping goes: eDMRG logical name → raw column name in source data.
    Then we convert eDMRG logical names to pipeline weather keys.
    """
    result: dict[str, float] = {}
    for edmrg_name, source_col in mapping.items():
        if edmrg_name in ('station_id', 'timestamp'):
            continue
        raw_value = row.get(source_col)
        if raw_value is not None and str(raw_value).strip() != '':
            result[edmrg_name] = _safe_float(raw_value)
    return result


def parse_edmrg_csv(
    data: str | bytes,
    mapping: dict[str, str],
    cadence: str,
) -> list[EdmrgRecord]:
    """Parse eDMRG CSV data into EdmrgRecord list.

    Args:
        data: CSV content as string or bytes.
        mapping: Field mapping for this cadence (e.g. mapping['manned_3h']).
        cadence: 'manned_3h' or 'aws_1h'.

    Returns:
        List of EdmrgRecord sorted by timestamp.
    """
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    reader = csv.DictReader(io.StringIO(data))
    records: list[EdmrgRecord] = []
    station_col = mapping.get('station_id', 'station_id')
    timestamp_col = mapping.get('timestamp', 'timestamp')
    for row in reader:
        station_id = str(row.get(station_col, 'unknown')).strip()
        ts_raw = row.get(timestamp_col)
        if not ts_raw:
            continue
        try:
            timestamp = _parse_timestamp(ts_raw)
        except ValueError:
            continue
        fields = _extract_fields(row, mapping)
        records.append(EdmrgRecord(
            station_id=station_id,
            timestamp=timestamp,
            cadence=cadence,
            fields=fields,
        ))
    records.sort(key=lambda r: r.timestamp)
    return records


def parse_edmrg_json(
    data: str | bytes | list[dict[str, Any]],
    mapping: dict[str, str],
    cadence: str,
) -> list[EdmrgRecord]:
    """Parse eDMRG JSON array into EdmrgRecord list.

    Args:
        data: JSON string, bytes, or pre-parsed list of dicts.
        mapping: Field mapping for this cadence.
        cadence: 'manned_3h' or 'aws_1h'.

    Returns:
        List of EdmrgRecord sorted by timestamp.
    """
    if isinstance(data, (str, bytes)):
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        parsed = json.loads(data)
    else:
        parsed = data
    if not isinstance(parsed, list):
        raise ValueError('eDMRG JSON data must be an array of objects')
    records: list[EdmrgRecord] = []
    station_col = mapping.get('station_id', 'station_id')
    timestamp_col = mapping.get('timestamp', 'timestamp')
    for row in parsed:
        if not isinstance(row, dict):
            continue
        station_id = str(row.get(station_col, 'unknown')).strip()
        ts_raw = row.get(timestamp_col)
        if not ts_raw:
            continue
        try:
            timestamp = _parse_timestamp(ts_raw)
        except ValueError:
            continue
        fields = _extract_fields(row, mapping)
        records.append(EdmrgRecord(
            station_id=station_id,
            timestamp=timestamp,
            cadence=cadence,
            fields=fields,
        ))
    records.sort(key=lambda r: r.timestamp)
    return records


def merge_cadences(
    manned: list[EdmrgRecord],
    aws: list[EdmrgRecord],
) -> list[EdmrgRecord]:
    """Merge manned 3-hour and AWS 1-hour records into a unified timeline.

    When both cadences have a record at the same timestamp, AWS (finer) wins
    for fields it covers; manned fields fill gaps.
    """
    by_ts: dict[datetime, EdmrgRecord] = {}
    for record in manned:
        by_ts[record.timestamp] = record
    for record in aws:
        existing = by_ts.get(record.timestamp)
        if existing is None:
            by_ts[record.timestamp] = record
        else:
            merged_fields = dict(existing.fields)
            merged_fields.update(record.fields)
            by_ts[record.timestamp] = EdmrgRecord(
                station_id=record.station_id or existing.station_id,
                timestamp=record.timestamp,
                cadence='merged',
                fields=merged_fields,
            )
    return sorted(by_ts.values(), key=lambda r: r.timestamp)


def edmrg_to_weather_samples(records: list[EdmrgRecord]) -> list[dict[str, float]]:
    """Convert EdmrgRecord list to weather sample dicts for build_real_feature_row.

    Maps eDMRG logical field names to pipeline weather_sample keys:
      temperature_c → temperature_2m
      wind_speed_ms → windspeed_10m
      wind_direction_deg → winddirection_10m
      new_snow_cm → snowfall_24h
      precipitation_mm → precipitation_24h
      snow_depth_cm → snow_depth
    """
    samples: list[dict[str, float]] = []
    for record in records:
        sample: dict[str, float] = {'timestamp': record.timestamp.isoformat()}
        for edmrg_name, value in record.fields.items():
            pipeline_key = EDMRG_TO_PIPELINE.get(edmrg_name)
            if pipeline_key:
                # Convert snow_depth from cm to m (pipeline expects meters)
                if edmrg_name == 'snow_depth_cm':
                    sample[pipeline_key] = value / 100.0
                else:
                    sample[pipeline_key] = value
        samples.append(sample)
    return samples


def edmrg_to_sequence_branches(
    records: list[EdmrgRecord],
    terrain: dict[str, float],
    static_feature_row: dict[str, float],
    *,
    zone_type: str | None = None,
    hourly_steps: int = DEFAULT_HOURLY_STEPS,
    daily_steps: int = DEFAULT_DAILY_STEPS,
    dynamic_features: list[str] | None = None,
    static_features: list[str] | None = None,
) -> SequenceBranches:
    """Convert eDMRG records into SequenceBranches for MTS-LSTM inference.

    Uses the same sequence_matrix_from_samples infrastructure as the existing
    Open-Meteo pipeline, but with eDMRG-derived weather samples.
    """
    weather_samples = edmrg_to_weather_samples(records)
    hourly_matrix, daily_matrix = sequence_matrix_from_samples(
        hourly_samples=weather_samples,
        daily_samples=weather_samples,
        terrain=terrain,
        dynamic_features=dynamic_features,
        hourly_steps=hourly_steps,
        daily_steps=daily_steps,
    )
    base_static = extract_static_vector(static_feature_row, static_features=static_features)
    zone_onehot = extract_zone_onehot(zone_type)
    static_vector = np.concatenate([base_static, zone_onehot])
    return SequenceBranches(hourly=hourly_matrix, daily=daily_matrix, static=static_vector)
