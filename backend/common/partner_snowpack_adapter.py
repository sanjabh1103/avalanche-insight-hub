"""Partner SNOWPACK 1D output ingestion adapter.

Ingests Partner SNOWPACK 1D output files (CSV/NetCDF) and converts them to
the app's SnowpackProxy format. This allows using Partner's operational
snowpack model outputs instead of the weather-derived proxy fallback.

Env flags:
  Partner_SNOWPACK_INPUT_PATH — path to Partner SNOWPACK output file
  Partner_SNOWPACK_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.snowpack_proxy import SnowpackProxy

Partner_SNOWPACK_ENABLED = os.getenv(
    'Partner_SNOWPACK_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}

Partner_SNOWPACK_INPUT_PATH = os.getenv('Partner_SNOWPACK_INPUT_PATH', '')


@dataclass
class PartnerSnowpackRecord:
    """Single SNOWPACK 1D output record."""
    station_id: str
    timestamp: datetime
    snow_depth_cm: float
    shear_strength_kpa: float
    settlement_index: float
    weak_layer_depth_cm: float | None
    grain_type: str | None
    stability_index: float | None
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    source: str = 'Partner_snowpack_1d'


def parse_snowpack_csv(csv_path: str) -> list[PartnerSnowpackRecord]:
    """Parse a Partner SNOWPACK 1D CSV output file.

    Expected columns: station_id, timestamp, snow_depth_cm, shear_strength_kpa,
    settlement_index, weak_layer_depth_cm, grain_type, stability_index
    """
    records: list[PartnerSnowpackRecord] = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                _lat = float(row['latitude']) if row.get('latitude') else None
                _lon = float(row['longitude']) if row.get('longitude') else None
                _elev = float(row['elevation_m']) if row.get('elevation_m') else None
                records.append(PartnerSnowpackRecord(
                    station_id=row['station_id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    snow_depth_cm=float(row['snow_depth_cm']),
                    shear_strength_kpa=float(row['shear_strength_kpa']),
                    settlement_index=float(row['settlement_index']),
                    weak_layer_depth_cm=float(row['weak_layer_depth_cm']) if row.get('weak_layer_depth_cm') else None,
                    grain_type=row.get('grain_type'),
                    stability_index=float(row['stability_index']) if row.get('stability_index') else None,
                    latitude=_lat,
                    longitude=_lon,
                    elevation_m=_elev,
                ))
            except (KeyError, ValueError):
                continue
    return records


def to_snowpack_proxy(record: PartnerSnowpackRecord) -> SnowpackProxy:
    """Convert a Partner SNOWPACK record to the app's SnowpackProxy format."""
    return SnowpackProxy(
        method='Partner_snowpack_1d',
        estimated_shear_strength=record.shear_strength_kpa,
        snow_settlement_index=record.settlement_index,
        season_start=record.timestamp.strftime('%Y-%m-%d'),
    )


def load_Partner_snowpack(
    csv_path: str | None = None,
) -> list[SnowpackProxy]:
    """Load Partner SNOWPACK outputs and convert to SnowpackProxy list.

    Returns empty list if disabled or no file found.
    """
    if not Partner_SNOWPACK_ENABLED:
        return []

    path = csv_path or Partner_SNOWPACK_INPUT_PATH
    if not path or not Path(path).exists():
        return []

    records = parse_snowpack_csv(path)
    return [to_snowpack_proxy(r) for r in records]


def load_Partner_snowpack_records(
    csv_path: str | None = None,
) -> list[PartnerSnowpackRecord]:
    """Load Partner SNOWPACK outputs as raw records (preserving coordinates).

    Returns empty list if disabled or no file found.
    """
    if not Partner_SNOWPACK_ENABLED:
        return []

    path = csv_path or Partner_SNOWPACK_INPUT_PATH
    if not path or not Path(path).exists():
        return []

    return parse_snowpack_csv(path)
