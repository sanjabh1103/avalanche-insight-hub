from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNOWSLIDE_RESEARCH_GRADE_POLICY_VERSION = 'snowslide_research_grade_v1'
SNOWSLIDE_EXPECTED_SCENE_IDS = (
    'livigno_20240403',
    'livigno_20250129',
    'livigno_20250318',
    'nuuk_20160413',
    'nuuk_20210411',
    'pish_20230221',
    'tromso_20241220',
)
SNOWSLIDE_PRECISION_FLOOR = 0.70
SNOWSLIDE_RECALL_FLOOR = 0.50
SNOWSLIDE_F1_FLOOR = 0.60
SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING = 0.002


@dataclass(frozen=True)
class SnowSlidePolicyFloors:
    precision: float = SNOWSLIDE_PRECISION_FLOOR
    recall: float = SNOWSLIDE_RECALL_FLOOR
    f1: float = SNOWSLIDE_F1_FLOOR
    false_positive_rate: float = SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING

    def as_dict(self) -> dict[str, float]:
        return {
            'precision': self.precision,
            'recall': self.recall,
            'f1': self.f1,
            'false_positive_rate': self.false_positive_rate,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'JSON artifact must contain an object: {path}')
    return payload


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _metric(report: dict[str, Any], key: str) -> float:
    metrics = report.get('metrics') if isinstance(report.get('metrics'), dict) else {}
    return _as_float(report.get(key, metrics.get(key)))


def _scene_ids_from_report(report: dict[str, Any]) -> list[str]:
    coverage = report.get('region_coverage')
    if isinstance(coverage, list):
        return sorted(str(item) for item in coverage if str(item).strip())
    scene_ids = report.get('scene_ids')
    if isinstance(scene_ids, list):
        return sorted(str(item) for item in scene_ids if str(item).strip())
    return []


def _avalcd_sar_metrics(avalcd_benchmark_report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(avalcd_benchmark_report, dict):
        return {}
    for source_report in avalcd_benchmark_report.get('source_reports') or []:
        if isinstance(source_report, dict) and source_report.get('source_key') == 'avalcd_zenodo_v1':
            metrics = source_report.get('sar_prediction_metrics')
            return metrics if isinstance(metrics, dict) else {}
    return {}


def _compare_float(left: Any, right: Any, *, tolerance: float = 1e-6) -> bool:
    return abs(_as_float(left) - _as_float(right)) <= tolerance


def summarize_materialization_results(
    result_dir: Path | None,
    *,
    expected_scene_ids: tuple[str, ...] = SNOWSLIDE_EXPECTED_SCENE_IDS,
) -> dict[str, Any]:
    if result_dir is None:
        return {
            'status': 'missing',
            'result_file_count': 0,
            'ok_result_count': 0,
            'covered_scene_ids': [],
            'missing_scene_ids': list(expected_scene_ids),
            'mask_asset_ref_count': 0,
            'event_persistence_allowed': False,
            'persisted_events': 0,
            'artifact_rows_persisted': 0,
        }
    root = result_dir.expanduser()
    result_files = sorted(root.rglob('sar_segment_result.json')) if root.exists() else []
    covered: set[str] = set()
    mask_refs: list[str] = []
    ok_count = 0
    persisted_events = 0
    artifact_rows_persisted = 0
    failed_results: list[dict[str, Any]] = []
    for path in result_files:
        payload = _load_json(path)
        status = str(payload.get('status') or '')
        if status == 'ok':
            ok_count += 1
            refs = [str(item) for item in payload.get('mask_asset_refs') or [] if str(item).strip()]
            mask_refs.extend(refs)
            for ref in refs:
                for scene_id in expected_scene_ids:
                    if scene_id in ref:
                        covered.add(scene_id)
            persisted_events += _as_int(payload.get('persisted_events'))
            artifact_rows_persisted += _as_int(payload.get('artifact_rows_persisted'))
        else:
            failed_results.append({
                'path': str(path),
                'status': status or 'unknown',
                'reason': payload.get('reason') or payload.get('error'),
            })
    missing = [scene_id for scene_id in expected_scene_ids if scene_id not in covered]
    return {
        'status': 'ok' if result_files and ok_count and not missing else 'incomplete',
        'result_file_count': len(result_files),
        'ok_result_count': ok_count,
        'covered_scene_ids': sorted(covered),
        'missing_scene_ids': missing,
        'mask_asset_ref_count': len(mask_refs),
        'mask_asset_refs': sorted(mask_refs),
        'event_persistence_allowed': False,
        'persisted_events': persisted_events,
        'artifact_rows_persisted': artifact_rows_persisted,
        'failed_results': failed_results,
    }


def evaluate_snowslide_research_grade(
    snow_report: dict[str, Any],
    *,
    avalcd_benchmark_report: dict[str, Any] | None = None,
    materialization_summary: dict[str, Any] | None = None,
    qualification_set_used_for_model_selection: bool = False,
    require_avalcd_provenance: bool = True,
    require_materialization_summary: bool = True,
    expected_scene_ids: tuple[str, ...] = SNOWSLIDE_EXPECTED_SCENE_IDS,
    floors: SnowSlidePolicyFloors = SnowSlidePolicyFloors(),
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    precision = _metric(snow_report, 'precision')
    recall = _metric(snow_report, 'recall')
    f1 = _metric(snow_report, 'f1')
    false_positive_rate = _metric(snow_report, 'false_positive_rate')
    scene_count = _as_int(snow_report.get('scene_count'))
    scene_ids = _scene_ids_from_report(snow_report)
    expected = sorted(expected_scene_ids)
    missing_scene_ids = [scene_id for scene_id in expected if scene_id not in scene_ids]

    if str(snow_report.get('status')) != 'ok':
        blockers.append({'gate': 'status', 'actual': snow_report.get('status'), 'required': 'ok'})
    if snow_report.get('dry_run') is not True:
        blockers.append({'gate': 'dry_run', 'actual': snow_report.get('dry_run'), 'required': True})
    if snow_report.get('production_scoring_allowed') is True:
        blockers.append({'gate': 'production_scoring', 'actual': True, 'required': False})
    if snow_report.get('promotion_result') is not None:
        blockers.append({'gate': 'promotion_result', 'actual': 'present', 'required': None})
    if snow_report.get('beats_baseline') is not True:
        blockers.append({'gate': 'beats_baseline', 'actual': snow_report.get('beats_baseline'), 'required': True})
    if scene_count != len(expected_scene_ids):
        blockers.append({'gate': 'scene_count', 'actual': scene_count, 'required': len(expected_scene_ids)})
    if missing_scene_ids:
        blockers.append({'gate': 'scene_coverage', 'missing_scene_ids': missing_scene_ids, 'required_scene_ids': expected})
    if precision < floors.precision:
        blockers.append({'gate': 'precision_floor', 'actual': precision, 'required': floors.precision})
    if recall < floors.recall:
        blockers.append({'gate': 'recall_floor', 'actual': recall, 'required': floors.recall})
    if f1 < floors.f1:
        blockers.append({'gate': 'f1_floor', 'actual': f1, 'required': floors.f1})
    if false_positive_rate > floors.false_positive_rate:
        blockers.append({
            'gate': 'false_positive_rate_ceiling',
            'actual': false_positive_rate,
            'required_max': floors.false_positive_rate,
        })

    avalcd_metrics = _avalcd_sar_metrics(avalcd_benchmark_report)
    if avalcd_benchmark_report is None and require_avalcd_provenance:
        blockers.append({'gate': 'avalcd_provenance', 'actual': 'missing', 'required': 'scene_blended gate report'})

    if avalcd_benchmark_report is not None:
        promotion = avalcd_benchmark_report.get('promotion_gate_report') if isinstance(avalcd_benchmark_report.get('promotion_gate_report'), dict) else {}
        avalcd_quality = avalcd_metrics.get('quality_gate') if isinstance(avalcd_metrics.get('quality_gate'), dict) else {}
        if avalcd_benchmark_report.get('production_scoring_allowed') is not False:
            blockers.append({'gate': 'avalcd_production_guard', 'actual': avalcd_benchmark_report.get('production_scoring_allowed'), 'required': False})
        if promotion.get('decision') != 'blocked_shadow_only':
            blockers.append({'gate': 'avalcd_promotion_decision', 'actual': promotion.get('decision'), 'required': 'blocked_shadow_only'})
        if avalcd_metrics.get('evaluation_mode') != 'scene_blended':
            blockers.append({'gate': 'avalcd_evaluation_mode', 'actual': avalcd_metrics.get('evaluation_mode'), 'required': 'scene_blended'})
        if not (
            avalcd_quality.get('passed') is True
            and avalcd_quality.get('precision_floor_met') is True
            and avalcd_quality.get('recall_floor_met') is True
        ):
            blockers.append({'gate': 'avalcd_quality_gate', 'actual': avalcd_quality, 'required': 'passed precision and recall'})
        avalcd_metric_values = avalcd_metrics.get('metrics') if isinstance(avalcd_metrics.get('metrics'), dict) else {}
        if not _compare_float(snow_report.get('prediction_threshold'), avalcd_metric_values.get('threshold', avalcd_metrics.get('threshold'))):
            blockers.append({
                'gate': 'decision_rule_threshold',
                'actual': snow_report.get('prediction_threshold'),
                'required': avalcd_metric_values.get('threshold', avalcd_metrics.get('threshold')),
            })
        if _as_int(snow_report.get('postprocess_min_component_area_px')) != _as_int(avalcd_metric_values.get('postprocess_min_component_area_px')):
            blockers.append({
                'gate': 'decision_rule_postprocess_min_component_area_px',
                'actual': snow_report.get('postprocess_min_component_area_px'),
                'required': avalcd_metric_values.get('postprocess_min_component_area_px'),
            })
        if _as_int(snow_report.get('postprocess_opening_size_px')) != _as_int(avalcd_metric_values.get('postprocess_opening_size_px')):
            blockers.append({
                'gate': 'decision_rule_postprocess_opening_size_px',
                'actual': snow_report.get('postprocess_opening_size_px'),
                'required': avalcd_metric_values.get('postprocess_opening_size_px'),
            })

    if materialization_summary is None and require_materialization_summary:
        blockers.append({'gate': 'materialization_summary', 'actual': 'missing', 'required': 'complete dry-run materialization proof'})

    if materialization_summary is not None:
        materialized_missing = list(materialization_summary.get('missing_scene_ids') or [])
        if materialized_missing:
            blockers.append({'gate': 'materialization_scene_coverage', 'missing_scene_ids': materialized_missing})
        if _as_int(materialization_summary.get('persisted_events')) != 0:
            blockers.append({'gate': 'materialization_event_persistence', 'actual': materialization_summary.get('persisted_events'), 'required': 0})
        if _as_int(materialization_summary.get('artifact_rows_persisted')) != 0:
            blockers.append({'gate': 'materialization_artifact_persistence', 'actual': materialization_summary.get('artifact_rows_persisted'), 'required': 0})

    metric_floor_gates = {'precision_floor', 'recall_floor', 'f1_floor', 'false_positive_rate_ceiling'}
    metric_floor_blockers = [blocker['gate'] for blocker in blockers if blocker.get('gate') in metric_floor_gates]
    accepted_metrics = not metric_floor_blockers
    if qualification_set_used_for_model_selection:
        warnings.append({
            'gate': 'fresh_final_holdout',
            'reason': 'SnowSlide was used to select or tune this candidate; use a fresh final hold-out before production promotion.',
        })

    if blockers:
        decision = 'blocked_research_grade'
    elif qualification_set_used_for_model_selection:
        decision = 'requires_fresh_final_holdout'
    else:
        decision = 'accepted_research_grade'

    return {
        'version': 'snowslide_acceptance_report_v1',
        'policy_version': SNOWSLIDE_RESEARCH_GRADE_POLICY_VERSION,
        'generated_at': _now_iso(),
        'decision': decision,
        'accepted_research_grade': decision == 'accepted_research_grade',
        'metric_floors_met': accepted_metrics,
        'requires_fresh_final_holdout': decision == 'requires_fresh_final_holdout',
        'bounded_candidate_warranted': bool(metric_floor_blockers),
        'production_scoring_allowed': False,
        'blockers': blockers,
        'warnings': warnings,
        'provenance_requirements': {
            'avalcd_scene_blended_gate_required': require_avalcd_provenance,
            'materialization_summary_required': require_materialization_summary,
            'qualification_set_used_for_model_selection': qualification_set_used_for_model_selection,
        },
        'floors': floors.as_dict(),
        'metrics': {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'false_positive_rate': false_positive_rate,
            'beats_baseline': bool(snow_report.get('beats_baseline')),
            'baseline_f1_floor_used': snow_report.get('baseline_f1_floor_used'),
        },
        'decision_rule': {
            'prediction_threshold': snow_report.get('prediction_threshold') or snow_report.get('threshold'),
            'postprocess_min_component_area_px': _as_int(snow_report.get('postprocess_min_component_area_px')),
            'postprocess_opening_size_px': _as_int(snow_report.get('postprocess_opening_size_px')),
        },
        'coverage': {
            'scene_count': scene_count,
            'expected_scene_ids': expected,
            'reported_scene_ids': scene_ids,
            'missing_scene_ids': missing_scene_ids,
        },
        'materialization_summary': materialization_summary,
    }


def assert_sar_acceptance_for_promotion(acceptance_report: dict[str, Any] | None) -> None:
    if not isinstance(acceptance_report, dict):
        raise ValueError('SAR promotion requires a SnowSlide research-grade acceptance report')
    if acceptance_report.get('requires_fresh_final_holdout') is True:
        raise ValueError('SAR promotion blocked until a fresh final held-out set passes')
    if acceptance_report.get('decision') != 'accepted_research_grade' or acceptance_report.get('accepted_research_grade') is not True:
        raise ValueError(
            'SAR promotion requires accepted_research_grade=true with decision=accepted_research_grade'
        )
