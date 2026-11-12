from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_MATERIALIZATION_ROOT = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v7/by-scene',
)
DEFAULT_SOURCE_EVALUATE_REQUEST = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v7/evaluate_release_request.json',
)
DEFAULT_MATERIALIZATION_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v7-float32',
)
DEFAULT_DRY_RUN_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v7-float32',
)
DEFAULT_MODEL_VERSION = 'avalcd_swinunet_tiny_diff_domain_calibrated_shadow_20260518_v7_scene_blended_float32'
ALLOWED_MASK_DTYPES = {'uint8', 'uint16', 'float32'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required SnowSlide mask-dtype request input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SnowSlide mask-dtype request input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _normalize_mask_dtype(value: str) -> str:
    resolved = str(value).strip().lower()
    if resolved not in ALLOWED_MASK_DTYPES:
        raise ValueError(f'prediction-mask dtype must be one of {sorted(ALLOWED_MASK_DTYPES)}')
    return resolved


def _scene_request_paths(root: Path) -> list[Path]:
    paths = sorted(root.glob('*/sar_segment_request.json'))
    if len(paths) != 7:
        raise ValueError(f'expected 7 by-scene request templates, found {len(paths)} under {root}')
    return paths


def _rewrite_prediction_ref(raw_ref: str, *, model_version: str) -> str:
    marker = '/predictions/'
    if marker not in raw_ref:
        raise ValueError(f'prediction_mask ref does not contain /predictions/: {raw_ref}')
    prefix = raw_ref.split(marker, 1)[0]
    return f'{prefix}{marker}{model_version}/prediction_mask.tif'


def _selected_rule_from_request(request: dict[str, Any]) -> dict[str, Any]:
    threshold = request.get('prediction_threshold')
    if threshold is None:
        threshold = request.get('threshold')
    if threshold is None:
        raise ValueError('source evaluate request is missing prediction_threshold/threshold')
    return {
        'threshold': float(threshold),
        'postprocess_min_component_area_px': int(request.get('postprocess_min_component_area_px') or 0),
        'postprocess_opening_size_px': int(request.get('postprocess_opening_size_px') or 0),
    }


def _rewrite_scene_request(
    template: dict[str, Any],
    *,
    model_version: str,
    mask_dtype: str,
    selected_rule: dict[str, Any],
) -> dict[str, Any]:
    scenes = template.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != 1 or not isinstance(scenes[0], dict):
        raise ValueError('by-scene template must contain exactly one scene')
    scene = dict(scenes[0])
    scene['prediction_mask'] = _rewrite_prediction_ref(str(scene.get('prediction_mask') or ''), model_version=model_version)
    return {
        **template,
        'compact_response': True,
        'dry_run': True,
        'shadow_mode': True,
        'persist_events': False,
        'prediction_model_version': model_version,
        'prediction_mask_dtype': mask_dtype,
        'threshold': selected_rule['threshold'],
        'postprocess_min_component_area_px': selected_rule['postprocess_min_component_area_px'],
        'postprocess_opening_size_px': selected_rule['postprocess_opening_size_px'],
        'scenes': [scene],
    }


def build_snowslide_mask_dtype_requalification_requests(
    *,
    source_materialization_root: Path,
    source_evaluate_request: Path,
    prediction_model_version: str,
    prediction_mask_dtype: str,
    materialization_output_root: Path,
    dry_run_output_root: Path,
) -> dict[str, Any]:
    mask_dtype = _normalize_mask_dtype(prediction_mask_dtype)
    source_eval = _load_json(source_evaluate_request, label='source_evaluate_request')
    selected_rule = _selected_rule_from_request(source_eval)

    scene_request_paths: list[str] = []
    scene_ids: list[str] = []
    for template_path in _scene_request_paths(source_materialization_root):
        template = _load_json(template_path, label=f'scene_template:{template_path.parent.name}')
        request = _rewrite_scene_request(
            template,
            model_version=prediction_model_version,
            mask_dtype=mask_dtype,
            selected_rule=selected_rule,
        )
        scene_id = str(request['scenes'][0].get('scene_id') or template_path.parent.name)
        output_path = materialization_output_root / 'by-scene' / scene_id / 'sar_segment_request.json'
        _write_json(output_path, request)
        scene_request_paths.append(str(output_path))
        scene_ids.append(scene_id)

    evaluation_request = {
        **source_eval,
        'dry_run': True,
        'prediction_model_version': prediction_model_version,
        'prediction_threshold': selected_rule['threshold'],
        'postprocess_min_component_area_px': selected_rule['postprocess_min_component_area_px'],
        'postprocess_opening_size_px': selected_rule['postprocess_opening_size_px'],
    }
    _write_json(dry_run_output_root / 'evaluate_release_request.json', evaluation_request)

    manifest = {
        'version': 'snowslide_mask_dtype_requalification_requests_v1',
        'generated_at': _now_iso(),
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'next_gpu_run_authorized': False,
        'training_authorized': False,
        'prediction_mask_dtype': mask_dtype,
        'prediction_model_version': prediction_model_version,
        'selected_rule': selected_rule,
        'scene_count': len(scene_ids),
        'scene_ids': sorted(scene_ids),
        'scene_request_paths': scene_request_paths,
        'evaluate_release_request_path': str(dry_run_output_root / 'evaluate_release_request.json'),
        'source_materialization_root': str(source_materialization_root),
        'source_evaluate_request': str(source_evaluate_request),
    }
    _write_json(materialization_output_root / 'requalification_request_manifest.json', manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build SnowSlide requalification requests with a new prediction-mask dtype.')
    parser.add_argument('--source-materialization-root', type=Path, default=DEFAULT_SOURCE_MATERIALIZATION_ROOT)
    parser.add_argument('--source-evaluate-request', type=Path, default=DEFAULT_SOURCE_EVALUATE_REQUEST)
    parser.add_argument('--prediction-model-version', default=DEFAULT_MODEL_VERSION)
    parser.add_argument('--prediction-mask-dtype', default='float32')
    parser.add_argument('--materialization-output-root', type=Path, default=DEFAULT_MATERIALIZATION_OUTPUT_ROOT)
    parser.add_argument('--dry-run-output-root', type=Path, default=DEFAULT_DRY_RUN_OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_snowslide_mask_dtype_requalification_requests(
        source_materialization_root=args.source_materialization_root,
        source_evaluate_request=args.source_evaluate_request,
        prediction_model_version=args.prediction_model_version,
        prediction_mask_dtype=args.prediction_mask_dtype,
        materialization_output_root=args.materialization_output_root,
        dry_run_output_root=args.dry_run_output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'scene_count': manifest['scene_count'],
        'prediction_mask_dtype': manifest['prediction_mask_dtype'],
        'selected_rule': manifest['selected_rule'],
        'evaluate_release_request_path': manifest['evaluate_release_request_path'],
        'production_scoring_allowed': manifest['production_scoring_allowed'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
