from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from backend.common.config import load_settings
from backend.common.sar_release_refs import load_reference_bundle, reference_item_to_scene
from backend.sar_unet_worker import run_segmentation
from backend.scripts.bootstrap_release_gate import load_rollout_env


DEFAULT_PREDICTION_MODEL_VERSION = 'swin_transformer_v2_tiny_coldstart_v1'
DEFAULT_MODEL_FAMILY = 'swinunet_tiny_diff'
DEFAULT_LOCAL_MODEL_PATH = Path('backend/data/models/swin_transformer_v2_tiny_coldstart_v1.pt')
DEFAULT_PREDICTION_MASK_DTYPE = 'uint8'


def _apply_rollout_env(env_file: Path) -> dict[str, str]:
    env = load_rollout_env(env_file)
    missing: list[str] = []
    if not env.supabase_url:
        missing.append('SUPABASE_URL or VITE_SUPABASE_URL')
    if not env.supabase_service_role_key:
        missing.append('SUPABASE_SERVICE_ROLE_KEY')
    if missing:
        raise ValueError(
            'authoritative prediction materialization is blocked until required settings are present: '
            + ', '.join(missing)
        )
    os.environ['SUPABASE_URL'] = env.supabase_url
    os.environ['SUPABASE_SERVICE_ROLE_KEY'] = env.supabase_service_role_key
    return {
        'supabase_url': env.supabase_url,
        'sar_unet_model_version': env.sar_unet_model_version,
        'sar_unet_model_family': env.sar_unet_model_family,
    }


def materialize_authoritative_prediction_masks(
    *,
    env_file: Path,
    reference_set_key: str,
    prediction_model_version: str,
    local_model_path: Path,
    model_family: str,
    artifact_root: Path,
    device: str,
    threshold: float,
    hazard_type: str,
    prediction_mask_dtype: str = DEFAULT_PREDICTION_MASK_DTYPE,
) -> dict[str, Any]:
    _apply_rollout_env(env_file)
    resolved_model_path = local_model_path.expanduser().resolve()
    if not resolved_model_path.exists():
        raise FileNotFoundError(f'local checkpoint not found: {resolved_model_path}')

    set_row, items = load_reference_bundle(
        reference_set_key,
        authoritative_only=True,
        status='active',
    )
    scenes = [
        reference_item_to_scene(
            set_row,
            item,
            model_version=prediction_model_version,
        )
        for item in items
    ]
    summary_rows: list[dict[str, Any]] = []
    uploaded_refs: list[str] = []

    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get('scene_id') or f'scene-{index}')
        print(f'[{index}/{len(scenes)}] materializing prediction mask for {scene_id}', flush=True)
        result = run_segmentation(
            scenes=[scene],
            model_path=resolved_model_path,
            artifact_root=artifact_root,
            threshold=threshold,
            device=device,
            hazard_type=hazard_type,
            persist_events=False,
            promoted=False,
            model_version=prediction_model_version,
            model_family=model_family,
            prediction_mask_dtype=prediction_mask_dtype,
        )
        if str(result.get('status')) != 'ok':
            raise RuntimeError(f'prediction materialization failed for scene "{scene_id}": {json.dumps(result, sort_keys=True)}')
        mask_asset_refs = [ref for ref in (result.get('mask_asset_refs') or []) if isinstance(ref, str) and ref]
        uploaded_refs.extend(mask_asset_refs)
        summary_rows.append({
            'scene_id': scene_id,
            'status': result.get('status'),
            'detections_count': int(result.get('detections_count') or 0),
            'mask_asset_refs': mask_asset_refs,
        })

    return {
        'status': 'ok',
        'reference_set_key': reference_set_key,
        'prediction_model_version': prediction_model_version,
        'prediction_mask_dtype': prediction_mask_dtype,
        'scene_count': len(scenes),
        'uploaded_prediction_masks': len(uploaded_refs),
        'mask_asset_refs': uploaded_refs,
        'scene_results': summary_rows,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description='Materialize authoritative held-out prediction masks into Supabase Storage using a local SAR checkpoint',
    )
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--reference-set-key', required=True)
    parser.add_argument('--prediction-model-version', default=DEFAULT_PREDICTION_MODEL_VERSION)
    parser.add_argument('--local-model-path', type=Path, default=DEFAULT_LOCAL_MODEL_PATH)
    parser.add_argument('--model-family', default=DEFAULT_MODEL_FAMILY)
    parser.add_argument('--artifact-root', type=Path, default=settings.artifact_root)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--threshold', type=float, default=float(os.environ.get('SAR_UNET_SEGMENTATION_THRESHOLD', '0.5')))
    parser.add_argument('--hazard-type', default=settings.hazard_type)
    parser.add_argument('--prediction-mask-dtype', default=DEFAULT_PREDICTION_MASK_DTYPE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = materialize_authoritative_prediction_masks(
        env_file=args.env_file,
        reference_set_key=args.reference_set_key,
        prediction_model_version=args.prediction_model_version,
        local_model_path=args.local_model_path,
        model_family=args.model_family,
        artifact_root=args.artifact_root,
        device=args.device,
        threshold=args.threshold,
        hazard_type=args.hazard_type,
        prediction_mask_dtype=args.prediction_mask_dtype,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
