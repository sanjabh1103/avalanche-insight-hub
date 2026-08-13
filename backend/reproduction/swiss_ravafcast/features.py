from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from backend.reproduction.swiss_ravafcast.constants import RF1_RESOURCE_KEY, RF2_RESOURCE_KEY
from backend.reproduction.swiss_ravafcast.data_loader import TARGET_ALIASES


FEATURE_SET_AUTO_NUMERIC_CURRENT = 'auto_numeric_current'
FEATURE_SET_PAPER_CANDIDATE_WHITELIST = 'paper_candidate_whitelist'
FEATURE_SET_LEAKAGE_GUARDED = 'leakage_guarded'

FEATURE_SET_NAMES = (
    FEATURE_SET_AUTO_NUMERIC_CURRENT,
    FEATURE_SET_PAPER_CANDIDATE_WHITELIST,
    FEATURE_SET_LEAKAGE_GUARDED,
)

PAPER_CANDIDATE_FEATURES = (
    'elevation_station',
    'Qs',
    'Ql',
    'Qg_mean',
    'TSG',
    'Qg0',
    'Qr',
    'OLWR',
    'ILWR',
    'LWR_net',
    'OSWR',
    'ISWR',
    'Qw',
    'pAlbedo',
    'mAlbedo_mean',
    'ISWR_h',
    'ISWR_diff',
    'ISWR_dir',
    'TA',
    'TSS_mod',
    'TSS_meas',
    'T_bottom',
    'RH',
    'VW',
    'VW_drift',
    'DW',
    'MS_Snow',
    'HS_mod',
    'HS_meas',
    'hoar_size',
    'wind_trans24',
    'wind_trans24_7d',
    'wind_trans24_3d',
    'HN24',
    'HN72_24',
    'HN24_7d',
    'SWE',
    'MS_water',
    'MS_Wind',
    'MS_Rain',
    'MS_SN_Runoff',
    'MS_Soil_Runoff_mean',
    'MS_Sublimation',
    'MS_Evap',
    'TS0',
    'TS1',
    'TS2',
    'TS3_mean',
    'TS4_mean',
    'Sclass2',
    'zSd_mean',
    'Sd',
    'zSn',
    'Sn',
    'zSs',
    'Ss',
    'zS4',
    'S4',
    'zS5',
    'S5',
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
    'Pen_depth',
    'min_ccl_pen',
)

BANNED_FEATURE_COLUMNS = frozenset(
    {
        'dangerlevel',
        'danger_level',
        'd_forecast',
        'd_tidy',
        'set',
        'warnreg',
        'sector_id',
        'unnamed: 0',
        'index',
        'row_id',
        'label',
        'target',
        'production_label',
    }
)


@dataclass(frozen=True)
class FeatureSetReport:
    name: str
    selected_columns: tuple[str, ...]
    dropped_banned_columns: tuple[str, ...]
    missing_whitelist_columns: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            'name': self.name,
            'selected_columns': list(self.selected_columns),
            'feature_count': len(self.selected_columns),
            'dropped_banned_columns': list(self.dropped_banned_columns),
            'missing_whitelist_columns': list(self.missing_whitelist_columns),
        }


def all_target_aliases() -> set[str]:
    aliases = set()
    for resource_key in (RF1_RESOURCE_KEY, RF2_RESOURCE_KEY):
        aliases.update(alias.lower() for alias in TARGET_ALIASES[resource_key])
    return aliases


def normalized_banned_columns(extra_banned_columns: Iterable[str] | None = None) -> set[str]:
    banned = set(BANNED_FEATURE_COLUMNS)
    banned.update(all_target_aliases())
    if extra_banned_columns:
        banned.update(str(column).lower() for column in extra_banned_columns)
    return banned


def validate_no_banned_features(
    feature_columns: Iterable[str],
    *,
    extra_banned_columns: Iterable[str] | None = None,
) -> None:
    banned = normalized_banned_columns(extra_banned_columns)
    hits = sorted(str(column) for column in feature_columns if str(column).lower() in banned)
    if hits:
        raise ValueError(f'feature set contains banned leakage/provenance columns: {hits}')


def select_feature_set(
    frame: pd.DataFrame,
    *,
    feature_set_name: str,
    target_column: str,
    exclude_columns: Iterable[str] | None = None,
) -> FeatureSetReport:
    if feature_set_name not in FEATURE_SET_NAMES:
        raise ValueError(f'unknown Swiss RF4 feature set: {feature_set_name}')

    excluded = {str(column) for column in (exclude_columns or []) if column}
    excluded.add(target_column)
    banned = normalized_banned_columns(excluded)
    numeric_columns = [str(column) for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    dropped_banned = tuple(sorted(column for column in numeric_columns if column.lower() in banned))

    if feature_set_name == FEATURE_SET_PAPER_CANDIDATE_WHITELIST:
        present = [column for column in PAPER_CANDIDATE_FEATURES if column in frame.columns]
        selected = tuple(column for column in present if column.lower() not in banned)
        missing = tuple(column for column in PAPER_CANDIDATE_FEATURES if column not in frame.columns)
    else:
        selected = tuple(column for column in numeric_columns if column.lower() not in banned)
        missing = tuple()

    validate_no_banned_features(selected, extra_banned_columns=excluded)
    if not selected:
        raise ValueError(f'feature set {feature_set_name} selected no usable numeric columns')
    return FeatureSetReport(
        name=feature_set_name,
        selected_columns=selected,
        dropped_banned_columns=dropped_banned,
        missing_whitelist_columns=missing,
    )
