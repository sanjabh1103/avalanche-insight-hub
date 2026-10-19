from __future__ import annotations

from collections import defaultdict
from typing import Any

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from backend.reproduction.swiss_ravafcast.constants import USAGE_BOUNDARY
from backend.reproduction.swiss_ravafcast.train_rf4 import RF4_LABELS


ELEV_SIMPLE_BANDS = (1200, 1600, 2000, 2400)
DEFAULT_BANDWIDTH_M = 400
RAVAFCAST_REFERENCE_REFINED_THRESHOLDS = (0.5, 1.61, 2.42, 3.44)


def _linear_quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError('expected_danger_values must not be empty')
    clipped_probability = min(max(float(probability), 0.0), 1.0)
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = clipped_probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return (ordered[lower] * (1.0 - weight)) + (ordered[upper] * weight)


def compute_refined_discretization_thresholds(
    expected_danger_values: list[float],
    true_training_labels: list[int],
) -> tuple[float, float, float, float]:
    """Compute RAvaFcast-style thresholds from training/OOB data only.

    The caller must pass training or out-of-bag expected-danger values and labels.
    Validation, test, holdout, or client-final labels must never be used here.
    """
    if len(expected_danger_values) != len(true_training_labels):
        raise ValueError('expected_danger_values and true_training_labels must have equal length')
    if not expected_danger_values:
        raise ValueError('expected_danger_values must not be empty')
    cleaned_expected = [float(value) for value in expected_danger_values]
    cleaned_labels = [int(label) for label in true_training_labels]
    if any(label not in RF4_LABELS for label in cleaned_labels):
        raise ValueError('true_training_labels must be 1, 2, 3, or 4')
    sample_count = len(cleaned_labels)
    cumulative_probabilities = [
        sum(1 for label in cleaned_labels if label <= boundary) / sample_count
        for boundary in (1, 2, 3)
    ]
    thresholds = [0.5]
    for probability in cumulative_probabilities:
        candidate = _linear_quantile(cleaned_expected, probability)
        thresholds.append(max(candidate, thresholds[-1]))
    return tuple(round(value, 6) for value in thresholds)  # type: ignore[return-value]


def discretize_expected_danger(
    expected_danger: float,
    *,
    thresholds: tuple[float, float, float, float] = RAVAFCAST_REFERENCE_REFINED_THRESHOLDS,
) -> int:
    if len(thresholds) != 4:
        raise ValueError('thresholds must contain lower bounds for danger levels 1-4')
    ordered_thresholds = tuple(float(value) for value in thresholds)
    if any(left > right for left, right in zip(ordered_thresholds, ordered_thresholds[1:])):
        raise ValueError('thresholds must be monotonic non-decreasing')
    value = float(expected_danger)
    if value >= ordered_thresholds[3]:
        return 4
    if value >= ordered_thresholds[2]:
        return 3
    if value >= ordered_thresholds[1]:
        return 2
    return 1


def build_full_aggregation_readiness(
    *,
    gp_grid_available: bool,
    warning_region_polygons_available: bool,
) -> dict[str, Any]:
    missing = []
    if not gp_grid_available:
        missing.append('gpxyz_1km_grid')
    if not warning_region_polygons_available:
        missing.append('official_warning_region_polygons')
    decision = 'ready_for_full_ravafcast_aggregation' if not missing else 'blocked_full_aggregation_inputs_required'
    return {
        'schema_version': 'swiss_full_ravafcast_aggregation_readiness_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'stage': 'stage3_full_ravafcast_warning_region_aggregation',
        'decision': decision,
        'missing_required_inputs': missing,
        'elev_simple_bands_m': list(ELEV_SIMPLE_BANDS),
        'bandwidth_m': DEFAULT_BANDWIDTH_M,
        'refined_rounding_required': True,
    }


def nearest_elevation_band(elevation_m: float, *, bands: tuple[int, ...] = ELEV_SIMPLE_BANDS) -> int:
    return int(min(bands, key=lambda band: abs(float(elevation_m) - band)))


def build_elev_simple_aggregation(
    evaluation_rows: list[dict[str, Any]],
    *,
    bands: tuple[int, ...] = ELEV_SIMPLE_BANDS,
    bandwidth_m: int = DEFAULT_BANDWIDTH_M,
    refined_thresholds: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    band_groups: dict[tuple[str, str, int], dict[str, Any]] = {}
    skipped_rows = 0
    for row in evaluation_rows:
        date = row.get('date')
        region = row.get('warnreg')
        elevation = row.get('elevation_station')
        true_danger = row.get('true_danger')
        predicted_danger = row.get('predicted_danger')
        if date is None or region is None or elevation is None or true_danger is None or predicted_danger is None:
            skipped_rows += 1
            continue
        band = nearest_elevation_band(float(elevation), bands=bands)
        key = (str(date), str(region), band)
        group = band_groups.setdefault(
            key,
            {
                'date': str(date),
                'warning_region': str(region),
                'elevation_band_m': band,
                'station_count': 0,
                'true_danger': 1,
                'predicted_danger': 1,
                'expected_danger_max': 1.0,
            },
        )
        group['station_count'] += 1
        group['true_danger'] = max(int(group['true_danger']), int(true_danger))
        group['expected_danger_max'] = max(float(group['expected_danger_max']), float(row.get('expected_danger') or 1.0))
        if refined_thresholds is not None:
            group['predicted_danger'] = discretize_expected_danger(
                float(group['expected_danger_max']),
                thresholds=refined_thresholds,
            )
        else:
            group['predicted_danger'] = max(int(group['predicted_danger']), int(predicted_danger))

    region_day_groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            'date': '',
            'warning_region': '',
            'band_count': 0,
            'station_count': 0,
            'true_danger': 1,
            'predicted_danger': 1,
        }
    )
    for band_group in band_groups.values():
        key = (band_group['date'], band_group['warning_region'])
        day_group = region_day_groups[key]
        day_group['date'] = band_group['date']
        day_group['warning_region'] = band_group['warning_region']
        day_group['band_count'] += 1
        day_group['station_count'] += int(band_group['station_count'])
        day_group['true_danger'] = max(int(day_group['true_danger']), int(band_group['true_danger']))
        day_group['predicted_danger'] = max(int(day_group['predicted_danger']), int(band_group['predicted_danger']))

    region_day_rows = sorted(region_day_groups.values(), key=lambda item: (item['date'], item['warning_region']))
    y_true = [int(row['true_danger']) for row in region_day_rows]
    y_pred = [int(row['predicted_danger']) for row in region_day_rows]
    if y_true:
        per_class_f1 = f1_score(y_true, y_pred, labels=list(RF4_LABELS), average=None, zero_division=0)
        metrics = {
            'accuracy': float(accuracy_score(y_true, y_pred)),
            'macro_f1': float(f1_score(y_true, y_pred, labels=list(RF4_LABELS), average='macro', zero_division=0)),
            'per_class_f1': {str(label): float(score) for label, score in zip(RF4_LABELS, per_class_f1)},
            'confusion_matrix_labels': list(RF4_LABELS),
            'confusion_matrix': confusion_matrix(y_true, y_pred, labels=list(RF4_LABELS)).astype(int).tolist(),
        }
    else:
        metrics = {
            'accuracy': None,
            'macro_f1': None,
            'per_class_f1': {str(label): None for label in RF4_LABELS},
            'confusion_matrix_labels': list(RF4_LABELS),
            'confusion_matrix': [],
        }

    return {
        'schema_version': 'swiss_elev_simple_aggregation_result_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'stage': 'stage3_elev_simple_warning_region_aggregation',
        'bands_m': list(bands),
        'bandwidth_m': bandwidth_m,
        'discretization': {
            'method': (
                'research_refined_expected_danger_thresholds'
                if refined_thresholds is not None
                else 'legacy_predicted_class_max'
            ),
            'thresholds': list(refined_thresholds) if refined_thresholds is not None else None,
            'reference_thresholds': list(RAVAFCAST_REFERENCE_REFINED_THRESHOLDS),
            'leakage_guard': 'refined_thresholds_must_be_computed_from_training_or_oob_data_only',
        },
        'input_rows': int(len(evaluation_rows)),
        'skipped_rows': int(skipped_rows),
        'band_rows': sorted(band_groups.values(), key=lambda item: (item['date'], item['warning_region'], item['elevation_band_m'])),
        'region_day_rows': region_day_rows,
        'metrics': metrics,
        'claim_boundary': 'station_row_baseline_until_gpxyz_grid_and_warning_region_polygons_are_available',
    }


def build_aggregation_from_rf4_result(result: dict[str, Any]) -> dict[str, Any]:
    rows = result.get('evaluation_rows')
    if not isinstance(rows, list):
        raise ValueError('RF4 result does not contain evaluation_rows; rerun train-rf4 with the current code')
    payload = build_elev_simple_aggregation(rows)
    payload['source_rf4_schema_version'] = result.get('schema_version')
    payload['source_rf4_model_key'] = result.get('model_key')
    return payload
