from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.common.avalanche_prone_terrain import APT_PROFILE, is_apt_eligible_slope, slope_from_cell
from backend.common.public_eligibility import PUBLIC_ELIGIBILITY_PROFILE, SNOW_ELEVATION_PROFILE
from backend.common.timezone_utils import resolve_zoneinfo


EAWS_DANGER_LABELS: dict[int, str] = {
    1: 'Low',
    2: 'Moderate',
    3: 'Considerable',
    4: 'High',
    5: 'Very High',
}

_PROBLEM_TYPE_TO_SLUG: dict[str, str | None] = {
    'Storm Slab': 'new_snow',
    'New Snow': 'new_snow',
    'Wind Slab': 'wind_slab',
    'Persistent Slab': 'persistent_weak_layers',
    'Persistent Weak Layers': 'persistent_weak_layers',
    'Deep Persistent Slab': 'persistent_weak_layers',
    'Wet Loose': 'wet_snow',
    'Wet Slab': 'wet_snow',
    'Wet Snow': 'wet_snow',
    'Glide Avalanche': 'gliding_snow',
    'Gliding Snow': 'gliding_snow',
    'No Distinct Avalanche Problem': 'no_distinct_avalanche_problem',
    'Cornice Fall': None,
    'Unavailable terrain': None,
    'Unavailable weather': None,
    'Unknown': None,
}
_ASPECT_ANGLE_BY_LABEL: dict[str, int] = {
    'N': 0,
    'NE': 45,
    'E': 90,
    'SE': 135,
    'S': 180,
    'SW': 225,
    'W': 270,
    'NW': 315,
}
_ASPECT_LABELS_BY_INDEX = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
_ELEVATION_BAND_STEP_M = 200
_BULLETIN_SOURCE_FIELD = 'risk_score'
_BULLETIN_BASE_METRIC = 'probability_risk_score'
_DAYPART_PROFILE = 'local_grid_share_heuristic_v2'
_DAYPART_ORDER = {'night': 0, 'morning': 1, 'afternoon': 2, 'evening': 3}
_DAYPART_AGGREGATION_MODE = 'peak_hour_within_daypart_v1'
_PRIMARY_WINDOW_POLICY = 'first_available_current_or_future_daypart_v1'
_WINDOW_FREQUENCY_BASIS = 'hourly_peak_cumulative_frequency_over_public_eligible_cells'
_HIGH_UNCERTAINTY_SPAN_THRESHOLD = 0.30
_REDUCED_CONFIDENCE_UNCERTAINTY_SHARE = 0.25
_REDUCED_CONFIDENCE_LOW_COVERAGE_SHARE = 0.25


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, (int, float)):
        numeric = int(value)
        if 1 <= numeric <= 5:
            return numeric
    return None


def _normalize_problem_slug(cell: dict[str, object]) -> str | None:
    explicit_slug = cell.get('problem_slug')
    if isinstance(explicit_slug, str):
        cleaned_slug = explicit_slug.strip()
        if cleaned_slug:
            return cleaned_slug
    problem_type = cell.get('problem_type')
    if not isinstance(problem_type, str):
        return None
    cleaned = problem_type.strip()
    if not cleaned:
        return None
    if cleaned in _PROBLEM_TYPE_TO_SLUG:
        return _PROBLEM_TYPE_TO_SLUG[cleaned]
    return cleaned.lower().replace(' ', '_')


def _aspect_bin(aspect_deg: object) -> str | None:
    numeric = _as_float(aspect_deg)
    if numeric is None:
        return None
    normalized = numeric % 360.0
    bucket_index = int(((normalized + 22.5) % 360.0) // 45.0)
    return _ASPECT_LABELS_BY_INDEX[bucket_index]


def _ordered_aspect_bins(cells: list[dict[str, object]]) -> list[str]:
    labels = {
        label
        for cell in cells
        for label in [_aspect_bin(((cell.get('terrain_inputs') or {}) if isinstance(cell.get('terrain_inputs'), dict) else {}).get('aspect_deg'))]
        if label is not None
    }
    if not labels:
        return []
    ordered = sorted(labels, key=lambda label: _ASPECT_ANGLE_BY_LABEL[label])
    if len(ordered) <= 1:
        return ordered

    angles = [_ASPECT_ANGLE_BY_LABEL[label] for label in ordered]
    gaps: list[float] = []
    for idx, angle in enumerate(angles):
        next_angle = angles[(idx + 1) % len(angles)]
        gap = (next_angle - angle) % 360.0
        gaps.append(gap)
    rotate_after = max(range(len(gaps)), key=gaps.__getitem__)
    start_idx = (rotate_after + 1) % len(ordered)
    return ordered[start_idx:] + ordered[:start_idx]


def _rounded_elevation_envelope(cells: list[dict[str, object]]) -> dict[str, int | None]:
    elevations: list[float] = []
    for cell in cells:
        terrain_inputs = cell.get('terrain_inputs')
        if not isinstance(terrain_inputs, dict):
            continue
        elevation_m = _as_float(terrain_inputs.get('elevation_m'))
        if elevation_m is not None:
            elevations.append(elevation_m)
    if not elevations:
        return {
            'min_m': None,
            'max_m': None,
            'band_step_m': _ELEVATION_BAND_STEP_M,
        }
    min_m = int(math.floor(min(elevations) / _ELEVATION_BAND_STEP_M) * _ELEVATION_BAND_STEP_M)
    max_m = int(math.ceil(max(elevations) / _ELEVATION_BAND_STEP_M) * _ELEVATION_BAND_STEP_M)
    return {
        'min_m': min_m,
        'max_m': max_m,
        'band_step_m': _ELEVATION_BAND_STEP_M,
    }


def _frequency_class(share: float) -> str:
    if share <= 0.0:
        return 'none_or_nearly_none'
    if share < 0.04:
        return 'few'
    if share <= 0.20:
        return 'some'
    return 'many'


def _cell_uncertainty_span(cell: dict[str, object]) -> float | None:
    lower = _as_float(cell.get('confidence_lower'))
    upper = _as_float(cell.get('confidence_upper'))
    if lower is not None and upper is not None:
        return max(0.0, upper - lower)
    return _as_float(cell.get('uncertainty_span'))


def _has_high_uncertainty(cell: dict[str, object]) -> bool:
    uncertainty_span = _cell_uncertainty_span(cell)
    if uncertainty_span is not None:
        return uncertainty_span > _HIGH_UNCERTAINTY_SPAN_THRESHOLD
    return str(cell.get('uncertainty_class') or '').strip().lower() == 'high'


def _sar_coverage_state(cell: dict[str, object]) -> str | None:
    direct = cell.get('sar_coverage_state')
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()
    coverage_flags = cell.get('coverage_flags')
    if isinstance(coverage_flags, dict):
        nested = coverage_flags.get('sar_coverage_state')
        if isinstance(nested, str) and nested.strip():
            return nested.strip().lower()
    return None


def _confidence_metadata(
    *,
    eligible_cells: list[dict[str, object]],
    region_status: str,
) -> dict[str, object]:
    eligible_cell_count = len(eligible_cells)
    high_uncertainty_cell_count = sum(1 for cell in eligible_cells if _has_high_uncertainty(cell))
    low_sar_coverage_cell_count = sum(
        1
        for cell in eligible_cells
        if (coverage_state := _sar_coverage_state(cell)) is not None and coverage_state != 'full_coverage'
    )
    high_uncertainty_share = high_uncertainty_cell_count / eligible_cell_count if eligible_cell_count else 0.0
    low_sar_coverage_share = low_sar_coverage_cell_count / eligible_cell_count if eligible_cell_count else 0.0

    confidence_reasons: list[str] = []
    if region_status == 'partial':
        confidence_reasons.append('partial_coverage')
    if high_uncertainty_share >= _REDUCED_CONFIDENCE_UNCERTAINTY_SHARE and high_uncertainty_cell_count > 0:
        confidence_reasons.append('high_uncertainty_share')
    if low_sar_coverage_share >= _REDUCED_CONFIDENCE_LOW_COVERAGE_SHARE and low_sar_coverage_cell_count > 0:
        confidence_reasons.append('low_sar_coverage_share')

    return {
        'confidence_state': 'reduced' if confidence_reasons else 'normal',
        'confidence_reasons': confidence_reasons,
        'uncertainty_summary': {
            'eligible_cell_count': eligible_cell_count,
            'high_uncertainty_cell_count': high_uncertainty_cell_count,
            'high_uncertainty_share': round(high_uncertainty_share, 4),
            'low_sar_coverage_cell_count': low_sar_coverage_cell_count,
            'low_sar_coverage_share': round(low_sar_coverage_share, 4),
        },
    }


def _is_ready(cell: dict[str, object]) -> bool:
    return cell.get('status') == 'ready' and _as_int(cell.get(_BULLETIN_SOURCE_FIELD)) is not None


def _is_legacy_eligible(cell: dict[str, object]) -> bool:
    return bool(
        cell.get('apt_eligible') is True
        or (
            cell.get('apt_eligible') is None
            and is_apt_eligible_slope(slope_from_cell(cell))
        )
    )


def _is_public_eligible(cell: dict[str, object]) -> bool:
    return cell.get('public_eligible') is True


def _problem_groups(candidate_cells: list[dict[str, object]], selected_level: int) -> tuple[str, list[str], dict[str, int], list[dict[str, object]]]:
    if selected_level == 1:
        return 'no_distinct_avalanche_problem', [], {}, candidate_cells

    grouped: dict[str, list[dict[str, object]]] = {}
    for cell in candidate_cells:
        slug = _normalize_problem_slug(cell)
        if slug is None:
            continue
        grouped.setdefault(slug, []).append(cell)

    def _problem_sort_key(item: tuple[str, list[dict[str, object]]]) -> tuple[int, float, str]:
        slug, cells = item
        max_probability = max((_as_float(cell.get('probability')) or 0.0) for cell in cells)
        return (-len(cells), -max_probability, slug)

    sorted_problem_groups = sorted(grouped.items(), key=_problem_sort_key)
    problems = [slug for slug, _cells in sorted_problem_groups]
    primary_problem = problems[0] if problems else 'no_distinct_avalanche_problem'
    primary_cells = grouped.get(primary_problem) if primary_problem in grouped else None
    return (
        primary_problem,
        problems,
        {slug: len(cells) for slug, cells in sorted_problem_groups},
        primary_cells or candidate_cells,
    )


def _build_bulletin_for_rows(
    *,
    rows: list[dict[str, object]],
    region_status: str,
    eligible_predicate: Callable[[dict[str, object]], bool],
    aggregation: str,
    terrain_filter_profile: str,
    frequency_basis: str,
    frequency_threshold_profile: str | None = None,
) -> dict[str, Any] | None:
    if region_status not in {'ready', 'partial'}:
        return None

    ready_cells = [cell for cell in rows if _is_ready(cell)]
    if not ready_cells:
        return None

    eligible_cells = [cell for cell in ready_cells if eligible_predicate(cell)]
    if not eligible_cells:
        return None

    ready_cell_count = len(ready_cells)
    eligible_cell_count = len(eligible_cells)
    selected_level = 1
    selected_frequency_class = 'many'
    candidate_cells = list(eligible_cells)

    for level in (5, 4, 3, 2):
        level_cells = [
            cell
            for cell in eligible_cells
            if (_as_int(cell.get(_BULLETIN_SOURCE_FIELD)) or 0) >= level
        ]
        level_share = len(level_cells) / eligible_cell_count if eligible_cell_count else 0.0
        frequency_class = _frequency_class(level_share)
        if (
            (level == 5 and frequency_class == 'many')
            or (level == 4 and frequency_class in {'some', 'many'})
            or (level in {3, 2} and frequency_class in {'few', 'some', 'many'})
        ):
            selected_level = level
            selected_frequency_class = frequency_class
            candidate_cells = level_cells
            break

    primary_problem, problems, problem_counts, prone_cells = _problem_groups(candidate_cells, selected_level)
    result: dict[str, Any] = {
        'schema_version': 'forecast-bulletin/v1',
        'standard': 'EAWS-style experimental',
        'danger_level': selected_level,
        'danger_label': EAWS_DANGER_LABELS[selected_level],
        'primary_problem': primary_problem,
        'problems': problems,
        'critical_elevations': _rounded_elevation_envelope(prone_cells),
        'critical_aspects': _ordered_aspect_bins(prone_cells),
        'coverage': region_status,
        'derived_from': {
            'aggregation': aggregation,
            'source_field': _BULLETIN_SOURCE_FIELD,
            'base_metric': _BULLETIN_BASE_METRIC,
            'terrain_filter_profile': terrain_filter_profile,
            'frequency_basis': frequency_basis,
            'frequency_class': selected_frequency_class,
            'ready_cell_count': ready_cell_count,
            'eligible_cell_count': eligible_cell_count,
            'max_danger_cell_count': len(candidate_cells),
            'selected_level_cell_count': len(candidate_cells),
            'selected_level_cell_share': round(len(candidate_cells) / eligible_cell_count, 4),
            'problem_counts': problem_counts,
        },
    }
    result.update(
        _confidence_metadata(
            eligible_cells=eligible_cells,
            region_status=region_status,
        )
    )
    if frequency_threshold_profile is not None:
        result['frequency_threshold_profile'] = frequency_threshold_profile
    return result


def build_forecast_bulletin(
    *,
    rows: list[dict[str, object]],
    region_status: str,
) -> dict[str, Any] | None:
    return _build_bulletin_for_rows(
        rows=rows,
        region_status=region_status,
        eligible_predicate=_is_legacy_eligible,
        aggregation='highest_regional_level_by_cumulative_frequency',
        terrain_filter_profile=APT_PROFILE,
        frequency_basis='cumulative_ge_threshold',
    )


def _to_aware_utc_datetime(value: object) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    to_pydatetime = getattr(value, 'to_pydatetime', None)
    if callable(to_pydatetime):
        dt = to_pydatetime()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise TypeError('forecast_date must be datetime-like')


def _daypart_name(local_dt: datetime) -> str:
    hour = local_dt.hour
    if 0 <= hour < 6:
        return 'night'
    if 6 <= hour < 12:
        return 'morning'
    if 12 <= hour < 18:
        return 'afternoon'
    return 'evening'


def _window_sort_key(window: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(window['day_index']),
        int(window['order']),
        min(int(hour) for hour in window['forecast_hours']),
    )


def _hourly_peak_sort_key(summary: dict[str, Any]) -> tuple[int, int]:
    return (
        int(summary['danger_level']),
        -int(summary['forecast_hour']),
    )


def _peak_window_sort_key(summary: dict[str, Any]) -> tuple[int, int]:
    return (
        int(summary['danger_level']),
        -min(int(hour) for hour in summary['forecast_hours']),
    )


def _build_window_diagnostics(
    *,
    rows: list[dict[str, object]],
    region_status: str,
) -> dict[str, Any]:
    flattened_summary = _build_bulletin_for_rows(
        rows=rows,
        region_status=region_status,
        eligible_predicate=_is_public_eligible,
        aggregation='daypart_window_diagnostics_by_cumulative_frequency',
        terrain_filter_profile=APT_PROFILE,
        frequency_basis='cumulative_ge_threshold_over_public_eligible_cells',
        frequency_threshold_profile=_DAYPART_PROFILE,
    )
    if flattened_summary is None:
        return {
            'aggregation': 'daypart_window_diagnostics_by_cumulative_frequency',
            'frequency_basis': 'cumulative_ge_threshold_over_public_eligible_cells',
            'ready_cell_count': 0,
            'eligible_cell_count': 0,
            'max_danger_cell_count': 0,
            'selected_level_cell_count': 0,
            'selected_level_cell_share': 0.0,
            'problem_counts': {},
        }
    return {
        'danger_level': flattened_summary['danger_level'],
        'danger_label': flattened_summary['danger_label'],
        **flattened_summary['derived_from'],
    }


def build_daypart_forecast_bulletin(
    *,
    hourly_grids: list[list[dict[str, object]]],
    region_status: str,
    forecast_date: object,
    timezone_name: str,
    horizon_hours: int,
) -> dict[str, Any] | None:
    if region_status not in {'ready', 'partial'} or not hourly_grids:
        return None

    base_utc = _to_aware_utc_datetime(forecast_date)
    zone, _resolved_timezone_name, timezone_fallback = resolve_zoneinfo(timezone_name)
    base_local = base_utc.astimezone(zone)
    windows: dict[str, dict[str, Any]] = {}

    for hour_index, rows in enumerate(hourly_grids[:max(1, int(horizon_hours or len(hourly_grids)))]):
        hour_utc = base_utc + timedelta(hours=hour_index)
        local_dt = hour_utc.astimezone(zone)
        day_index = (local_dt.date() - base_local.date()).days + 1
        daypart = _daypart_name(local_dt)
        window_key = f'day_{day_index}_{daypart}'
        window = windows.setdefault(
            window_key,
            {
                'window': window_key,
                'day_index': day_index,
                'daypart': daypart,
                'order': _DAYPART_ORDER[daypart],
                'local_date': local_dt.date().isoformat(),
                'rows': [],
                'forecast_hours': [],
                'hours': [],
                'local_start': local_dt.replace(minute=0, second=0, microsecond=0),
                'local_end': local_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
            },
        )
        window['rows'].extend(rows)
        window['forecast_hours'].append(hour_index)
        window['hours'].append(
            {
                'forecast_hour': hour_index,
                'rows': rows,
                'local_start': local_dt.replace(minute=0, second=0, microsecond=0),
                'local_end': local_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
            }
        )
        if local_dt < window['local_start']:
            window['local_start'] = local_dt
        if local_dt + timedelta(hours=1) > window['local_end']:
            window['local_end'] = local_dt + timedelta(hours=1)

    ordered_windows = sorted(windows.values(), key=_window_sort_key)
    dayparts: list[dict[str, Any]] = []
    summaries_by_key: dict[str, dict[str, Any]] = {}

    for window in ordered_windows:
        hourly_summaries: list[dict[str, Any]] = []
        for hour_slice in window['hours']:
            hourly_summary = _build_bulletin_for_rows(
                rows=hour_slice['rows'],
                region_status=region_status,
                eligible_predicate=_is_public_eligible,
                aggregation='hourly_peak_candidate_by_cumulative_frequency',
                terrain_filter_profile=APT_PROFILE,
                frequency_basis='cumulative_ge_threshold_over_public_eligible_cells',
                frequency_threshold_profile=_DAYPART_PROFILE,
            )
            if hourly_summary is None:
                continue
            hourly_summaries.append(
                {
                    **hourly_summary,
                    'forecast_hour': hour_slice['forecast_hour'],
                    'local_start': hour_slice['local_start'].isoformat(),
                    'local_end': hour_slice['local_end'].isoformat(),
                }
            )

        if not hourly_summaries:
            continue

        summary = max(hourly_summaries, key=_hourly_peak_sort_key)
        selected_summary = {
            key: value
            for key, value in summary.items()
            if key not in {'forecast_hour', 'local_start', 'local_end'}
        }
        window_diagnostics = _build_window_diagnostics(
            rows=window['rows'],
            region_status=region_status,
        )
        daypart_summary = {
            **selected_summary,
            'derived_from': {
                **selected_summary['derived_from'],
                'aggregation': 'daypart_peak_hour_by_cumulative_frequency',
                'daypart_window': window['window'],
            },
            'window': window['window'],
            'day_index': window['day_index'],
            'daypart': window['daypart'],
            'local_date': window['local_date'],
            'forecast_hours': window['forecast_hours'],
            'local_start': window['local_start'].isoformat(),
            'local_end': window['local_end'].isoformat(),
            'daypart_aggregation_mode': _DAYPART_AGGREGATION_MODE,
            'window_frequency_basis': _WINDOW_FREQUENCY_BASIS,
            'selected_forecast_hour': summary['forecast_hour'],
            'selected_hour_local_start': summary['local_start'],
            'selected_hour_local_end': summary['local_end'],
            'window_diagnostics': window_diagnostics,
        }
        summaries_by_key[window['window']] = daypart_summary
        dayparts.append(daypart_summary)

    if not dayparts:
        return None

    aggregation_notes: list[str] = []
    if timezone_fallback:
        aggregation_notes.append('timezone_fallback_to_utc')

    primary = dayparts[0]
    if primary['window'] != 'day_1_morning':
        aggregation_notes.append('day_1_morning_missing_fell_back_to_first_available_window')

    peak = max(dayparts, key=_peak_window_sort_key)
    morning = summaries_by_key.get('day_1_morning')
    afternoon = summaries_by_key.get('day_1_afternoon')
    double_map = bool(
        morning is not None
        and afternoon is not None
        and afternoon['primary_problem'] == 'wet_snow'
        and afternoon['danger_level'] > morning['danger_level']
    )

    result = {
        'schema_version': 'forecast-bulletin/v1',
        'standard': 'EAWS-style experimental',
        'danger_level': primary['danger_level'],
        'danger_label': primary['danger_label'],
        'primary_problem': primary['primary_problem'],
        'problems': primary['problems'],
        'critical_elevations': primary['critical_elevations'],
        'critical_aspects': primary['critical_aspects'],
        'coverage': primary['coverage'],
        'confidence_state': primary.get('confidence_state', 'normal'),
        'confidence_reasons': list(primary.get('confidence_reasons') or []),
        'uncertainty_summary': primary.get('uncertainty_summary'),
        'derived_from': {
            **primary['derived_from'],
            'aggregation': 'daypart_primary_window_by_peak_hour',
            'daypart_window': primary['window'],
        },
        'issue_window_policy': 'daypart_v1',
        'primary_window': primary['window'],
        'primary_window_policy': _PRIMARY_WINDOW_POLICY,
        'peak_window': {
            'window': peak['window'],
            'danger_level': peak['danger_level'],
            'danger_label': peak['danger_label'],
            'primary_problem': peak['primary_problem'],
            'forecast_hours': peak['forecast_hours'],
            'local_start': peak['local_start'],
            'local_end': peak['local_end'],
            'selected_forecast_hour': peak['selected_forecast_hour'],
            'selected_hour_local_start': peak['selected_hour_local_start'],
            'selected_hour_local_end': peak['selected_hour_local_end'],
        },
        'dayparts': dayparts,
        'double_map': double_map,
        'aggregation_notes': aggregation_notes,
        'public_mask_profile': {
            'profile': PUBLIC_ELIGIBILITY_PROFILE,
            'stage_a': APT_PROFILE,
            'stage_b': SNOW_ELEVATION_PROFILE,
        },
        'frequency_threshold_profile': _DAYPART_PROFILE,
    }
    return result
