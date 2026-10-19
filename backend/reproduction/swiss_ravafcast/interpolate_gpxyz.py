from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
from sklearn.preprocessing import StandardScaler

from backend.reproduction.swiss_ravafcast.constants import RF2_RESOURCE_KEY, USAGE_BOUNDARY
from backend.reproduction.swiss_ravafcast.data_loader import inspect_swiss_frame


STATION_METADATA_REQUIRED_COLUMNS = ('station_code', 'latitude', 'longitude', 'elevation_m')
DEFAULT_EXACT_GP_MAX_TRAIN_ROWS = 250


@dataclass(frozen=True)
class GPXYZReadinessReport:
    row_count: int
    station_count: int
    station_column: str | None
    latitude_column: str | None
    longitude_column: str | None
    elevation_column: str | None
    missing_required_columns: tuple[str, ...]
    decision: str
    usage_boundary: str = USAGE_BOUNDARY

    @property
    def ready(self) -> bool:
        return self.decision == 'ready_for_gpxyz'

    def as_dict(self) -> dict[str, Any]:
        return {
            'row_count': self.row_count,
            'station_count': self.station_count,
            'station_column': self.station_column,
            'latitude_column': self.latitude_column,
            'longitude_column': self.longitude_column,
            'elevation_column': self.elevation_column,
            'missing_required_columns': list(self.missing_required_columns),
            'decision': self.decision,
            'ready': self.ready,
            'usage_boundary': self.usage_boundary,
        }


@dataclass(frozen=True)
class StationMetadataReport:
    metadata_rows: int
    source_rows: int
    source_station_count: int
    matched_station_count: int
    missing_required_columns: tuple[str, ...]
    unmatched_station_count: int
    coordinate_missing_row_count: int
    decision: str
    usage_boundary: str = USAGE_BOUNDARY

    @property
    def ready(self) -> bool:
        return self.decision == 'ready_for_gpxyz_metadata_join'

    def as_dict(self) -> dict[str, Any]:
        return {
            'metadata_rows': self.metadata_rows,
            'source_rows': self.source_rows,
            'source_station_count': self.source_station_count,
            'matched_station_count': self.matched_station_count,
            'missing_required_columns': list(self.missing_required_columns),
            'unmatched_station_count': self.unmatched_station_count,
            'coordinate_missing_row_count': self.coordinate_missing_row_count,
            'decision': self.decision,
            'ready': self.ready,
            'usage_boundary': self.usage_boundary,
        }


def inspect_gpxyz_readiness(frame: pd.DataFrame, *, min_station_count: int = 10) -> GPXYZReadinessReport:
    schema = inspect_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)
    missing: list[str] = []
    if schema.station_column is None:
        missing.append('station_id')
    if schema.latitude_column is None:
        missing.append('latitude')
    if schema.longitude_column is None:
        missing.append('longitude')
    if schema.elevation_column is None:
        missing.append('elevation')

    station_count = int(frame[schema.station_column].nunique()) if schema.station_column else 0
    decision = 'ready_for_gpxyz'
    if missing:
        decision = 'blocked_station_coordinates_required'
    elif station_count < min_station_count:
        decision = 'blocked_min_station_count'

    return GPXYZReadinessReport(
        row_count=int(len(frame)),
        station_count=station_count,
        station_column=schema.station_column,
        latitude_column=schema.latitude_column,
        longitude_column=schema.longitude_column,
        elevation_column=schema.elevation_column,
        missing_required_columns=tuple(missing),
        decision=decision,
    )


def build_gpxyz_readiness_payload(frame: pd.DataFrame) -> dict[str, Any]:
    report = inspect_gpxyz_readiness(frame)
    return {
        'schema_version': 'swiss_gpxyz_readiness_report_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'stage': 'stage2_gpxyz_interpolation',
        'readiness': report.as_dict(),
    }


def inspect_station_metadata_join(
    frame: pd.DataFrame,
    metadata_frame: pd.DataFrame | None,
    *,
    station_column: str | None = None,
) -> StationMetadataReport:
    schema = inspect_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)
    source_station_column = station_column or schema.station_column or 'station_code'
    source_stations = set(frame[source_station_column].dropna().astype(str)) if source_station_column in frame.columns else set()
    if metadata_frame is None:
        return StationMetadataReport(
            metadata_rows=0,
            source_rows=int(len(frame)),
            source_station_count=len(source_stations),
            matched_station_count=0,
            missing_required_columns=STATION_METADATA_REQUIRED_COLUMNS,
            unmatched_station_count=len(source_stations),
            coordinate_missing_row_count=len(source_stations),
            decision='blocked_station_coordinates_required',
        )

    missing = tuple(column for column in STATION_METADATA_REQUIRED_COLUMNS if column not in metadata_frame.columns)
    if missing:
        decision = 'blocked_station_metadata_schema_mismatch'
        matched_count = 0
        unmatched_count = len(source_stations)
        coordinate_missing_count = len(source_stations)
    else:
        normalized_metadata = metadata_frame.copy()
        normalized_metadata['station_code'] = normalized_metadata['station_code'].astype(str)
        metadata_stations = set(normalized_metadata['station_code'].dropna().astype(str))
        matched_stations = source_stations & metadata_stations
        matched_count = len(matched_stations)
        unmatched_count = len(source_stations - metadata_stations)
        matched_metadata = normalized_metadata[normalized_metadata['station_code'].isin(matched_stations)]
        required_coordinate_columns = ('latitude', 'longitude', 'elevation_m')
        coordinate_missing_count = int(
            matched_metadata[list(required_coordinate_columns)].isna().any(axis=1).sum()
        )
        decision = 'ready_for_gpxyz_metadata_join'
        if unmatched_count or coordinate_missing_count:
            decision = 'blocked_station_metadata_incomplete'

    return StationMetadataReport(
        metadata_rows=int(len(metadata_frame)),
        source_rows=int(len(frame)),
        source_station_count=len(source_stations),
        matched_station_count=matched_count,
        missing_required_columns=missing,
        unmatched_station_count=unmatched_count,
        coordinate_missing_row_count=coordinate_missing_count,
        decision=decision,
    )


def build_station_metadata_payload(
    frame: pd.DataFrame,
    metadata_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    report = inspect_station_metadata_join(frame, metadata_frame)
    payload = {
        'schema_version': 'swiss_station_metadata_readiness_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'stage': 'stage2_station_metadata_join',
        'readiness': report.as_dict(),
    }
    if metadata_frame is not None and report.ready:
        schema = inspect_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)
        source_station_column = schema.station_column or 'station_code'
        joined = frame.merge(
            metadata_frame[list(STATION_METADATA_REQUIRED_COLUMNS)].drop_duplicates('station_code'),
            left_on=source_station_column,
            right_on='station_code',
            how='left',
            suffixes=('', '_metadata'),
        )
        payload['joined_row_count'] = int(len(joined))
        payload['coordinate_coverage'] = {
            'latitude_non_null_rows': int(joined['latitude'].notna().sum()),
            'longitude_non_null_rows': int(joined['longitude'].notna().sum()),
            'elevation_m_non_null_rows': int(joined['elevation_m'].notna().sum()),
        }
    return payload


def build_station_metadata_template_frame(frame: pd.DataFrame) -> pd.DataFrame:
    schema = inspect_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)
    station_column = schema.station_column or 'station_code'
    if station_column not in frame.columns:
        raise ValueError('station metadata template requires a station column in the RF2 frame')
    date_column = schema.date_column
    elevation_column = schema.elevation_column
    rows = []
    for station_code, group in frame.groupby(station_column, dropna=True):
        elevation_m = None
        if elevation_column and elevation_column in group.columns:
            elevation_values = pd.to_numeric(group[elevation_column], errors='coerce').dropna()
            if not elevation_values.empty:
                elevation_m = float(elevation_values.median())
        active_start = None
        active_end = None
        if date_column and date_column in group.columns:
            parsed = pd.to_datetime(group[date_column], utc=True, errors='coerce').dropna()
            if not parsed.empty:
                active_start = parsed.min().date().isoformat()
                active_end = parsed.max().date().isoformat()
        rows.append(
            {
                'station_code': str(station_code),
                'latitude': None,
                'longitude': None,
                'elevation_m': elevation_m,
                'active_start': active_start,
                'active_end': active_end,
                'source_row_count': int(len(group)),
                'metadata_review_status': 'pending',
                'reviewer_notes': '',
            }
        )
    columns = [
        'station_code',
        'latitude',
        'longitude',
        'elevation_m',
        'active_start',
        'active_end',
        'source_row_count',
        'metadata_review_status',
        'reviewer_notes',
    ]
    return pd.DataFrame(sorted(rows, key=lambda row: row['station_code']), columns=columns)


def write_station_metadata_template(frame: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    template = build_station_metadata_template_frame(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(output_path, index=False)
    return template


def predict_gpxyz(
    train_frame: pd.DataFrame,
    predict_frame: pd.DataFrame,
    *,
    target_column: str = 'expected_danger',
    coordinate_columns: tuple[str, str, str] = ('latitude', 'longitude', 'elevation_m'),
    random_state: int = 20260522,
    max_train_rows: int = DEFAULT_EXACT_GP_MAX_TRAIN_ROWS,
) -> dict[str, Any]:
    missing = [column for column in (*coordinate_columns, target_column) if column not in train_frame.columns]
    missing.extend(column for column in coordinate_columns if column not in predict_frame.columns)
    if missing:
        raise ValueError(f'GPxyz interpolation missing required columns: {sorted(set(missing))}')
    if len(train_frame) > max_train_rows:
        raise ValueError(
            f'blocked_requires_sparse_gp_design: exact GP train rows {len(train_frame)} exceed cap {max_train_rows}'
        )

    x_train_raw = train_frame[list(coordinate_columns)].astype(float).to_numpy()
    y_train = train_frame[target_column].astype(float).to_numpy()
    x_predict_raw = predict_frame[list(coordinate_columns)].astype(float).to_numpy()

    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train_raw)
    x_predict = scaler.transform(x_predict_raw)
    kernel = ConstantKernel(1.0, constant_value_bounds='fixed') * RBF(length_scale=np.ones(3)) + WhiteKernel(
        noise_level=0.1,
        noise_level_bounds='fixed',
    )
    model = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=random_state)
    model.fit(x_train, y_train)
    mean, std = model.predict(x_predict, return_std=True)

    predictions = []
    for idx, (_, row) in enumerate(predict_frame.reset_index(drop=True).iterrows()):
        predictions.append(
            {
                'latitude': float(row[coordinate_columns[0]]),
                'longitude': float(row[coordinate_columns[1]]),
                'elevation_m': float(row[coordinate_columns[2]]),
                'expected_danger_mean': float(np.clip(mean[idx], 1.0, 4.0)),
                'expected_danger_std': float(max(std[idx], 0.0)),
            }
        )

    return {
        'schema_version': 'swiss_gpxyz_interpolation_result_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'target_column': target_column,
        'coordinate_columns': list(coordinate_columns),
        'train_rows': int(len(train_frame)),
        'prediction_rows': int(len(predict_frame)),
        'exact_gp_max_train_rows': int(max_train_rows),
        'predictions': predictions,
    }


def evaluate_gpxyz_loocv(
    frame: pd.DataFrame,
    *,
    target_column: str = 'expected_danger',
    coordinate_columns: tuple[str, str, str] = ('latitude', 'longitude', 'elevation_m'),
    max_train_rows: int = DEFAULT_EXACT_GP_MAX_TRAIN_ROWS,
) -> dict[str, Any]:
    if len(frame) > max_train_rows:
        return {
            'schema_version': 'swiss_gpxyz_loocv_report_v1',
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'model_status_mutation_allowed': False,
            'decision': 'blocked_requires_sparse_gp_design',
            'row_count': int(len(frame)),
            'exact_gp_max_train_rows': int(max_train_rows),
        }
    missing = [column for column in (*coordinate_columns, target_column) if column not in frame.columns]
    if missing:
        return {
            'schema_version': 'swiss_gpxyz_loocv_report_v1',
            'usage_boundary': USAGE_BOUNDARY,
            'production_scoring_allowed': False,
            'model_status_mutation_allowed': False,
            'decision': 'blocked_station_coordinates_required',
            'missing_required_columns': sorted(set(missing)),
        }
    observed = []
    predicted = []
    for holdout_idx in range(len(frame)):
        train = frame.drop(frame.index[holdout_idx]).reset_index(drop=True)
        test = frame.iloc[[holdout_idx]].reset_index(drop=True)
        result = predict_gpxyz(
            train,
            test,
            target_column=target_column,
            coordinate_columns=coordinate_columns,
            max_train_rows=max_train_rows,
        )
        observed.append(float(test[target_column].iloc[0]))
        predicted.append(float(result['predictions'][0]['expected_danger_mean']))
    errors = np.asarray(predicted) - np.asarray(observed)
    return {
        'schema_version': 'swiss_gpxyz_loocv_report_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'decision': 'loocv_complete',
        'row_count': int(len(frame)),
        'exact_gp_max_train_rows': int(max_train_rows),
        'metrics': {
            'me': float(errors.mean()),
            'mae': float(mean_absolute_error(observed, predicted)),
            'rmse': float(mean_squared_error(observed, predicted) ** 0.5),
        },
    }
