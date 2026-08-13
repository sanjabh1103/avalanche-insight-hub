from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class ForecastMode(str, Enum):
    FULL = 'full'
    COLD_START = 'cold_start'
    TRANSFER = 'transfer'


@dataclass(frozen=True)
class ColdStartConfig:
    target_feature_count: int = 10
    pss_floor: float = 0.30
    brier_ceiling: float = 0.20
    min_winters_required: int = 3
    min_positive_events: int = 10
    synthetic_augmentation_multiplier: int = 3
    class_weight: dict[int, int] = None  # type: ignore[assignment]
    rf_trees: int = 200
    min_samples_leaf: int = 3

    def __post_init__(self) -> None:
        if self.class_weight is None:
            object.__setattr__(self, 'class_weight', {0: 1, 1: 6})


def get_cold_start_config() -> ColdStartConfig:
    return ColdStartConfig(
        target_feature_count=int(os.getenv('COLD_START_FEATURE_COUNT', '10')),
        pss_floor=float(os.getenv('COLD_START_PSS_FLOOR', '0.30')),
        brier_ceiling=float(os.getenv('COLD_START_BRIER_CEILING', '0.20')),
        min_winters_required=int(os.getenv('COLD_START_MIN_WINTERS', '3')),
        min_positive_events=int(os.getenv('COLD_START_MIN_POSITIVE_EVENTS', '10')),
        synthetic_augmentation_multiplier=int(os.getenv('COLD_START_AUGMENTATION_MULTIPLIER', '3')),
        rf_trees=int(os.getenv('COLD_START_RF_TREES', '200')),
        min_samples_leaf=int(os.getenv('COLD_START_MIN_SAMPLES_LEAF', '3')),
    )


def resolve_forecast_mode() -> ForecastMode:
    raw = os.getenv('FORECAST_MODE', 'full').strip().lower()
    try:
        return ForecastMode(raw)
    except ValueError:
        return ForecastMode.FULL


def is_cold_start_active() -> bool:
    return resolve_forecast_mode() == ForecastMode.COLD_START


def validate_cold_start_eligible(frame: pd.DataFrame) -> tuple[bool, str]:
    if frame.empty:
        return False, 'Training frame is empty.'

    positive_count = int((frame.get('label', pd.Series(dtype=int)).astype(int) == 1).sum())
    if positive_count < get_cold_start_config().min_positive_events:
        return False, (
            f'Insufficient positive events: {positive_count} '
            f'(need >= {get_cold_start_config().min_positive_events}).'
        )

    if 'timestamp' not in frame.columns:
        return True, 'No timestamp column — skipping winter count validation.'

    timestamps = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce').dropna()
    if timestamps.empty:
        return True, 'No valid timestamps — skipping winter count validation.'

    winter_years = set()
    for ts in timestamps:
        year = ts.year
        if ts.month >= 11:
            winter_years.add(year + 1)
        elif ts.month <= 4:
            winter_years.add(year)
    if len(winter_years) < get_cold_start_config().min_winters_required:
        return False, (
            f'Insufficient winter seasons: {len(winter_years)} '
            f'(need >= {get_cold_start_config().min_winters_required}).'
        )

    return True, f'Cold-start eligible: {positive_count} positive events across {len(winter_years)} winters.'
