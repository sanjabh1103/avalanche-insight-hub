from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from backend.reproduction.swiss_ravafcast.constants import (
    RF1_RESOURCE_KEY,
    RF2_RESOURCE_KEY,
    USAGE_BOUNDARY,
)


STATION_ID_ALIASES = ('station_id', 'station', 'station_code', 'aws_id', 'stn', 'id')
DATE_ALIASES = ('date', 'datum', 'forecast_date', 'forecast_initial_date', 'timestamp', 'time', 'datetime')
LATITUDE_ALIASES = ('lat', 'latitude', 'y')
LONGITUDE_ALIASES = ('lon', 'lng', 'longitude', 'x')
ELEVATION_ALIASES = ('elevation', 'elevation_m', 'elevation_station', 'altitude', 'altitude_m', 'z')

TARGET_ALIASES = {
    RF1_RESOURCE_KEY: ('D_forecast', 'd_forecast', 'dangerLevel', 'danger_level'),
    RF2_RESOURCE_KEY: ('D_tidy', 'd_tidy', 'dangerLevel', 'danger_level'),
}

SNOWPACK_PROFILE_FEATURE_ALIASES = (
    'Pen_depth',
    'pen_depth',
    'ccl',
    'Sn38',
    'sn38',
    'Sk38',
    'sk38',
    'SSI',
    'ssi',
    'PWL',
    'pwl',
    'PWL_100',
    'pwl_100',
    'pwl_100_15',
    'base_pwl',
    'ssi_pwl',
    'sk38_pwl',
    'sn38_pwl',
    'ccl_pwl',
    'ssi_pwl_100',
    'sk38_pwl_100',
    'sn38_pwl_100',
    'ccl_pwl_100',
    'min_ccl_pen',
)

METEO_FEATURE_HINTS = (
    'hn24',
    'hn72',
    'snow',
    'wind',
    'temp',
    'precip',
    'rain',
)


@dataclass(frozen=True)
class SwissFrameSchemaReport:
    resource_key: str
    row_count: int
    column_count: int
    target_column: str | None
    station_column: str | None
    date_column: str | None
    latitude_column: str | None
    longitude_column: str | None
    elevation_column: str | None
    snowpack_profile_features: tuple[str, ...]
    meteo_feature_candidates: tuple[str, ...]
    missing_required_groups: tuple[str, ...]
    usage_boundary: str = USAGE_BOUNDARY

    @property
    def valid_for_stage1(self) -> bool:
        return not self.missing_required_groups

    @property
    def valid_for_stage2(self) -> bool:
        return self.valid_for_stage1 and all(
            [
                self.latitude_column,
                self.longitude_column,
                self.elevation_column,
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            'resource_key': self.resource_key,
            'row_count': self.row_count,
            'column_count': self.column_count,
            'target_column': self.target_column,
            'station_column': self.station_column,
            'date_column': self.date_column,
            'latitude_column': self.latitude_column,
            'longitude_column': self.longitude_column,
            'elevation_column': self.elevation_column,
            'snowpack_profile_features': list(self.snowpack_profile_features),
            'meteo_feature_candidates': list(self.meteo_feature_candidates),
            'missing_required_groups': list(self.missing_required_groups),
            'valid_for_stage1': self.valid_for_stage1,
            'valid_for_stage2': self.valid_for_stage2,
            'usage_boundary': self.usage_boundary,
        }


def _find_first(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    exact = {column.lower(): column for column in columns}
    for alias in aliases:
        hit = exact.get(alias.lower())
        if hit is not None:
            return hit
    return None


def _find_all_exact(columns: list[str], aliases: tuple[str, ...]) -> tuple[str, ...]:
    exact_aliases = {alias.lower() for alias in aliases}
    return tuple(column for column in columns if column.lower() in exact_aliases)


def _find_contains(columns: list[str], hints: tuple[str, ...]) -> tuple[str, ...]:
    hits: list[str] = []
    lowered_hints = tuple(hint.lower() for hint in hints)
    for column in columns:
        lower = column.lower()
        if any(hint in lower for hint in lowered_hints):
            hits.append(column)
    return tuple(hits)


def load_swiss_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f'Swiss reproduction CSV not found: {path}')
    return pd.read_csv(path)


def inspect_swiss_frame(frame: pd.DataFrame, *, resource_key: str) -> SwissFrameSchemaReport:
    if resource_key not in TARGET_ALIASES:
        raise ValueError(f'unknown Swiss reproduction resource_key: {resource_key}')
    columns = [str(column) for column in frame.columns]
    target_column = _find_first(columns, TARGET_ALIASES[resource_key])
    station_column = _find_first(columns, STATION_ID_ALIASES)
    date_column = _find_first(columns, DATE_ALIASES)
    latitude_column = _find_first(columns, LATITUDE_ALIASES)
    longitude_column = _find_first(columns, LONGITUDE_ALIASES)
    elevation_column = _find_first(columns, ELEVATION_ALIASES)
    snowpack_features = _find_all_exact(columns, SNOWPACK_PROFILE_FEATURE_ALIASES)
    meteo_features = _find_contains(columns, METEO_FEATURE_HINTS)

    missing: list[str] = []
    if target_column is None:
        missing.append('target_label')
    if station_column is None:
        missing.append('station_id')
    if date_column is None:
        missing.append('date')
    if len(snowpack_features) < 3:
        missing.append('snowpack_profile_features_min3')

    return SwissFrameSchemaReport(
        resource_key=resource_key,
        row_count=len(frame),
        column_count=len(columns),
        target_column=target_column,
        station_column=station_column,
        date_column=date_column,
        latitude_column=latitude_column,
        longitude_column=longitude_column,
        elevation_column=elevation_column,
        snowpack_profile_features=snowpack_features,
        meteo_feature_candidates=meteo_features,
        missing_required_groups=tuple(missing),
    )


def validate_swiss_frame(frame: pd.DataFrame, *, resource_key: str) -> SwissFrameSchemaReport:
    report = inspect_swiss_frame(frame, resource_key=resource_key)
    if not report.valid_for_stage1:
        raise ValueError(
            f'Swiss {resource_key} frame is not valid for Stage-1 reproduction: '
            f'{list(report.missing_required_groups)}'
        )
    return report


def load_and_validate(path: Path, *, resource_key: str) -> tuple[pd.DataFrame, SwissFrameSchemaReport]:
    frame = load_swiss_csv(path)
    return frame, validate_swiss_frame(frame, resource_key=resource_key)
