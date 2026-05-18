from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_V6_ROOT = Path(
    'backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16/research-v6',
)
DEFAULT_V5_MATERIALIZATION_ROOT = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v5/by-scene',
)
DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v6',
)
DEFAULT_DRY_RUN_ROOT = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v6',
)
DEFAULT_MODEL_VERSION = 'avalcd_swinunet_tiny_diff_research_gate_shadow_20260518_v6_scene_blended'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required SnowSlide v6 request input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SnowSlide v6 request input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _metric_value(first_gate_plan: dict[str, Any], key: str) -> Any:
    metrics = first_gate_plan.get('metrics') if isinstance(first_gate_plan.get('metrics'), dict) else {}
    return metrics.get(key)


def _selected_rule(first_gate_plan: dict[str, Any]) -> dict[str, Any]:
    threshold = _metric_value(first_gate_plan, 'threshold')
    if threshold is None:
        raise ValueError('AvalCD first gate plan is missing selected threshold')
    return {
        'threshold': float(threshold),
        'postprocess_min_component_area_px': int(_metric_value(first_gate_plan, 'postprocess_min_component_area_px') or 0),
        'postprocess_opening_size_px': int(_metric_value(first_gate_plan, 'postprocess_opening_size_px') or 0),
    }


def _assert_avalcd_benchmark_allows_phase5(report: dict[str, Any]) -> None:
    if report.get('production_scoring_allowed') is not False:
        raise ValueError('AvalCD benchmark must remain production_scoring_allowed=false')
    promotion = report.get('promotion_gate_report') if isinstance(report.get('promotion_gate_report'), dict) else {}
    if promotion.get('decision') != 'blocked_shadow_only':
        raise ValueError('AvalCD benchmark must remain blocked_shadow_only')
    source_reports = report.get('source_reports')
    if not isinstance(source_reports, list):
        raise ValueError('AvalCD benchmark has no source_reports')
    avalcd = next((item for item in source_reports if isinstance(item, dict) and item.get('source_key') == 'avalcd_zenodo_v1'), None)
    if avalcd is None:
        raise ValueError('AvalCD benchmark missing avalcd_zenodo_v1 report')
    metrics = avalcd.get('sar_prediction_metrics') if isinstance(avalcd.get('sar_prediction_metrics'), dict) else {}
    gate = metrics.get('quality_gate') if isinstance(metrics.get('quality_gate'), dict) else {}
    if metrics.get('evaluation_mode') != 'scene_blended':
        raise ValueError('AvalCD benchmark must use scene_blended evaluation')
    if not (gate.get('passed') is True and gate.get('precision_floor_met') is True and gate.get('recall_floor_met') is True):
        raise ValueError('AvalCD benchmark quality gate must pass precision and recall floors')


def _scene_prediction_ref(raw_ref: str, *, model_version: str) -> str:
    marker = '/predictions/'
    if marker not in raw_ref:
        raise ValueError(f'prediction_mask ref does not contain /predictions/: {raw_ref}')
    prefix = raw_ref.split(marker, 1)[0]
    return f'{prefix}{marker}{model_version}/prediction_mask.tif'


def _v5_scene_templates(root: Path) -> list[Path]:
    paths = sorted(root.glob('*/sar_segment_request.json'))
    if len(paths) != 7:
        raise ValueError(f'expected 7 v5 by-scene request templates, found {len(paths)} under {root}')
    return paths


def _phase5_scene_request(
    template: dict[str, Any],
    *,
    model_path: str,
    model_version: str,
    selected_rule: dict[str, Any],
) -> dict[str, Any]:
    scenes = template.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != 1 or not isinstance(scenes[0], dict):
        raise ValueError('by-scene template must contain exactly one scene')
    scene = dict(scenes[0])
    scene['prediction_mask'] = _scene_prediction_ref(str(scene.get('prediction_mask') or ''), model_version=model_version)
    return {
        **template,
        'compact_response': True,
        'dry_run': True,
        'shadow_mode': True,
        'persist_events': False,
        'model_path': model_path,
        'prediction_model_version': model_version,
        'model_family': 'swinunet_tiny_diff',
        'threshold': selected_rule['threshold'],
        'postprocess_min_component_area_px': selected_rule['postprocess_min_component_area_px'],
        'postprocess_opening_size_px': selected_rule['postprocess_opening_size_px'],
        'scenes': [scene],
    }


def build_snowslide_v6_qualification_requests(
    *,
    avalcd_benchmark_report: Path,
    first_gate_plan: Path,
    v5_by_scene_request_root: Path,
    materialization_output_root: Path,
    dry_run_output_root: Path,
    model_path: str = '/artifacts/20260518T103347Z/sar_model.pt',
    model_version: str = DEFAULT_MODEL_VERSION,
) -> dict[str, Any]:
    avalcd_benchmark = _load_json(avalcd_benchmark_report, label='avalcd_benchmark_report')
    first_gate = _load_json(first_gate_plan, label='first_gate_plan')
    _assert_avalcd_benchmark_allows_phase5(avalcd_benchmark)
    selected_rule = _selected_rule(first_gate)

    scene_request_paths: list[str] = []
    scene_ids: list[str] = []
    for template_path in _v5_scene_templates(v5_by_scene_request_root):
        template = _load_json(template_path, label=f'v5_scene_template:{template_path.parent.name}')
        request = _phase5_scene_request(
            template,
            model_path=model_path,
            model_version=model_version,
            selected_rule=selected_rule,
        )
        scene_id = str(request['scenes'][0].get('scene_id') or template_path.parent.name)
        output_path = materialization_output_root / 'by-scene' / scene_id / 'sar_segment_request.json'
        _write_json(output_path, request)
        scene_request_paths.append(str(output_path))
        scene_ids.append(scene_id)

    evaluation_request = {
        'authoritative_only': True,
        'baseline_margin': 0.05,
        'dry_run': True,
        'hazard_type': 'avalanche',
        'prediction_model_version': model_version,
        'prediction_threshold': selected_rule['threshold'],
        'postprocess_min_component_area_px': selected_rule['postprocess_min_component_area_px'],
        'postprocess_opening_size_px': selected_rule['postprocess_opening_size_px'],
        'reference_set_key': 'snowslide-heldout-v1',
    }
    _write_json(dry_run_output_root / 'evaluate_release_request.json', evaluation_request)
    manifest = {
        'version': 'snowslide_v6_qualification_requests_v1',
        'generated_at': _now_iso(),
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'reference_set_key': 'snowslide-heldout-v1',
        'model_path': model_path,
        'prediction_model_version': model_version,
        'selected_rule': selected_rule,
        'scene_count': len(scene_ids),
        'scene_ids': sorted(scene_ids),
        'scene_request_paths': scene_request_paths,
        'evaluate_release_request_path': str(dry_run_output_root / 'evaluate_release_request.json'),
        'avalcd_benchmark_report': str(avalcd_benchmark_report),
    }
    _write_json(materialization_output_root / 'qualification_request_manifest.json', manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build SnowSlide v6 materialization and dry-run requests.')
    parser.add_argument('--avalcd-benchmark-report', type=Path, default=Path('backend/artifacts/european-shadow-real-benchmarks/european-shadow-real-avalcd-scene-blended-v6-2026-05-18/european_shadow_benchmark_report.json'))
    parser.add_argument('--first-gate-plan', type=Path, default=DEFAULT_V6_ROOT / 'avalcd-first-gate' / 'avalcd_first_gate_plan.json')
    parser.add_argument('--v5-by-scene-request-root', type=Path, default=DEFAULT_V5_MATERIALIZATION_ROOT)
    parser.add_argument('--materialization-output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--dry-run-output-root', type=Path, default=DEFAULT_DRY_RUN_ROOT)
    parser.add_argument('--model-path', default='/artifacts/20260518T103347Z/sar_model.pt')
    parser.add_argument('--model-version', default=DEFAULT_MODEL_VERSION)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_snowslide_v6_qualification_requests(
        avalcd_benchmark_report=args.avalcd_benchmark_report,
        first_gate_plan=args.first_gate_plan,
        v5_by_scene_request_root=args.v5_by_scene_request_root,
        materialization_output_root=args.materialization_output_root,
        dry_run_output_root=args.dry_run_output_root,
        model_path=args.model_path,
        model_version=args.model_version,
    )
    print(json.dumps({
        'status': 'ok',
        'scene_count': manifest['scene_count'],
        'selected_rule': manifest['selected_rule'],
        'evaluate_release_request_path': manifest['evaluate_release_request_path'],
        'production_scoring_allowed': manifest['production_scoring_allowed'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
