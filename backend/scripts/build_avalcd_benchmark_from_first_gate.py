from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.european_shadow_benchmarks import (
    EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
    build_european_shadow_benchmark_report,
    load_staging_manifest,
)


DEFAULT_V6_ROOT = Path(
    'backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/research-v6',
)
DEFAULT_STAGED_MANIFEST = Path(
    'backend/artifacts/european-shadow-staging/'
    'european-shadow-real-avalcd-assembled-2026-05-16/avalcd_zenodo_v1/staged_manifest.json',
)
DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-real-benchmarks/'
    'european-shadow-real-avalcd-scene-blended-v6-2026-05-18',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required AvalCD benchmark bridge input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'AvalCD benchmark bridge input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _metrics(evaluation_result: dict[str, Any]) -> dict[str, Any]:
    metrics = evaluation_result.get('validation_metrics')
    if not isinstance(metrics, dict):
        raise ValueError('AvalCD evaluation result is missing validation_metrics')
    return dict(metrics)


def _quality_gate(first_gate_plan: dict[str, Any], evaluation_result: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    precision_floor = float(first_gate_plan.get('precision_floor') or 0.6)
    recall_floor = float(first_gate_plan.get('recall_floor') or 0.5)
    precision = float(metrics.get('precision') or 0.0)
    recall = float(metrics.get('recall') or 0.0)
    passed = (
        evaluation_result.get('status') == 'ok'
        and evaluation_result.get('evaluation_mode') == 'scene_blended'
        and evaluation_result.get('quality_gate_passed') is True
        and precision >= precision_floor
        and recall >= recall_floor
    )
    return {
        'passed': passed,
        'blocked_gate': None if passed else 'avalcd_scene_blended_floor',
        'failures': list(evaluation_result.get('scene_gate_failures') or []),
        'precision_floor': precision_floor,
        'recall_floor': recall_floor,
        'precision_floor_met': precision >= precision_floor,
        'recall_floor_met': recall >= recall_floor,
        'joint_floor_met': precision >= precision_floor and recall >= recall_floor,
        'selected_precision': precision,
        'selected_recall': recall,
        'selected_threshold': metrics.get('threshold') or evaluation_result.get('best_threshold'),
        'source': 'avalcd_first_gate_plan_v1',
    }


def _prediction_artifact(
    *,
    first_gate_plan: dict[str, Any],
    evaluation_result: dict[str, Any],
    evaluation_request: dict[str, Any],
) -> dict[str, Any]:
    metrics = _metrics(evaluation_result)
    return {
        'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
        'source_key': evaluation_request.get('source_key') or 'avalcd_zenodo_v1',
        'dataset_version': evaluation_result.get('dataset_version'),
        'model_family': evaluation_result.get('model_family') or evaluation_request.get('model_family'),
        'model_version': evaluation_result.get('candidate_model_version') or evaluation_request.get('candidate_model_version'),
        'candidate_model_version': evaluation_result.get('candidate_model_version') or evaluation_request.get('candidate_model_version'),
        'evaluation_mode': evaluation_result.get('evaluation_mode'),
        'split': 'val',
        'threshold': metrics.get('threshold') or evaluation_result.get('best_threshold'),
        'generated_at': _now_iso(),
        'license_review_id': evaluation_request.get('license_review_id'),
        'metrics': {
            'threshold': metrics.get('threshold') or evaluation_result.get('best_threshold'),
            'auprc': evaluation_result.get('validation_auprc'),
            **metrics,
        },
        'postprocess_evaluation': evaluation_result.get('postprocess_evaluation'),
        'scene_breakdown': evaluation_result.get('scene_breakdown') or [],
        'region_breakdown': evaluation_result.get('region_breakdown') or {},
        'evaluated_scene_ids': evaluation_result.get('val_events') or [],
        'train_events': evaluation_result.get('train_events') or [],
        'val_events': evaluation_result.get('val_events') or [],
        'quality_gate': _quality_gate(first_gate_plan, evaluation_result, metrics),
    }


def build_avalcd_benchmark_from_first_gate(
    *,
    first_gate_plan: Path,
    evaluation_result: Path,
    evaluation_request: Path,
    staged_manifest: Path,
    output_root: Path,
    snapshot_id: str = 'european-shadow-real-avalcd-scene-blended-v6-2026-05-18',
) -> dict[str, Any]:
    first_gate = _load_json(first_gate_plan, label='first_gate_plan')
    evaluation = _load_json(evaluation_result, label='evaluation_result')
    request = _load_json(evaluation_request, label='evaluation_request')
    artifact = _prediction_artifact(
        first_gate_plan=first_gate,
        evaluation_result=evaluation,
        evaluation_request=request,
    )
    report = build_european_shadow_benchmark_report(
        staging_manifests=[load_staging_manifest(staged_manifest)],
        sar_prediction_artifacts=[artifact],
        snapshot_id=snapshot_id,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'european_sar_prediction_artifact.json', artifact)
    _write_json(output_root / 'european_shadow_benchmark_report.json', report)
    return {
        'status': 'ok',
        'prediction_artifact': artifact,
        'benchmark_report': report,
        'prediction_artifact_path': str(output_root / 'european_sar_prediction_artifact.json'),
        'benchmark_report_path': str(output_root / 'european_shadow_benchmark_report.json'),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a benchmark-compatible AvalCD v6 report from the first-gate result.')
    parser.add_argument('--first-gate-plan', type=Path, default=DEFAULT_V6_ROOT / 'avalcd-first-gate' / 'avalcd_first_gate_plan.json')
    parser.add_argument('--evaluation-result', type=Path, default=DEFAULT_V6_ROOT / 'avalcd-first-gate' / 'evaluate_sar_checkpoint_result.json')
    parser.add_argument('--evaluation-request', type=Path, default=DEFAULT_V6_ROOT / 'avalcd-first-gate' / 'evaluate_sar_checkpoint_request.json')
    parser.add_argument('--staged-manifest', type=Path, default=DEFAULT_STAGED_MANIFEST)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--snapshot-id', default='european-shadow-real-avalcd-scene-blended-v6-2026-05-18')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_avalcd_benchmark_from_first_gate(
        first_gate_plan=args.first_gate_plan,
        evaluation_result=args.evaluation_result,
        evaluation_request=args.evaluation_request,
        staged_manifest=args.staged_manifest,
        output_root=args.output_root,
        snapshot_id=args.snapshot_id,
    )
    report = result['benchmark_report']
    source_report = report['source_reports'][0]
    metrics = source_report['sar_prediction_metrics']['metrics']
    print(json.dumps({
        'status': 'ok',
        'benchmark_report_path': result['benchmark_report_path'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'promotion_decision': report['promotion_gate_report']['decision'],
        'evaluation_mode': source_report['sar_prediction_metrics']['evaluation_mode'],
        'quality_gate': source_report['sar_prediction_metrics']['quality_gate'],
        'precision': metrics.get('precision'),
        'recall': metrics.get('recall'),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
