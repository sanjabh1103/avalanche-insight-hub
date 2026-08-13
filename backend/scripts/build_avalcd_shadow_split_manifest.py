from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


DEFAULT_TRAIN_SCENES = {
    'livigno_20240403',
    'livigno_20250129',
    'nuuk_20160413',
    'pish_20230221',
    'tromso_20241220',
}
DEFAULT_VAL_SCENES = {
    'livigno_20250318',
    'nuuk_20210411',
}
DEFAULT_MODEL_FAMILY = 'swinunet_tiny_diff'
DEFAULT_PATCH_SIZE = 128
DEFAULT_STRIDE = 64
DEFAULT_EPOCHS = 8
DEFAULT_BATCH_SIZE = 8
DEFAULT_LEARNING_RATE = 0.0001
DEFAULT_LOSS = 'focal_tversky'
DEFAULT_F_BETA = 1.5
DEFAULT_PRECISION_FLOOR = 0.60
DEFAULT_MATERIALIZED_DATASET_ROOT = '/tmp/avalcd-shadow-train5-val2'
DEFAULT_CANDIDATE_MODEL_VERSION = 'avalcd_swinunet_tiny_diff_shadow_20260516_v1'


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR training manifest must be a JSON object: {path}')
    scenes = payload.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError(f'SAR training manifest must contain non-empty scenes[]: {path}')
    return payload


def _runtime_ref(value: str, *, local_root: Path, runtime_root: PurePosixPath) -> str:
    path = Path(value).expanduser().resolve()
    try:
        relative = path.relative_to(local_root)
    except ValueError as exc:
        raise ValueError(f'AvalCD ref is outside --local-assembled-root: {value}') from exc
    return str(runtime_root.joinpath(*relative.parts))


def build_avalcd_shadow_split_manifest(
    *,
    source_manifest: Path,
    local_assembled_root: Path,
    runtime_assembled_root: str,
    snapshot_id: str,
    license_review_id: str,
    output: Path,
    candidate_model_version: str = DEFAULT_CANDIDATE_MODEL_VERSION,
) -> dict[str, Any]:
    source = _load_manifest(source_manifest)
    local_root = local_assembled_root.expanduser().resolve()
    if not local_root.exists():
        raise FileNotFoundError(f'local assembled root does not exist: {local_root}')
    runtime_root = PurePosixPath(runtime_assembled_root)
    if not runtime_root.is_absolute():
        raise ValueError('--runtime-assembled-root must be an absolute Modal runtime path')
    if not str(license_review_id or '').strip():
        raise ValueError('--license-review is required')

    source_scenes = {
        str(scene.get('scene_id') or '').strip(): scene
        for scene in source['scenes']
        if isinstance(scene, dict)
    }
    expected = DEFAULT_TRAIN_SCENES | DEFAULT_VAL_SCENES
    missing = sorted(expected - set(source_scenes))
    if missing:
        raise ValueError(f'source manifest is missing required AvalCD scenes: {", ".join(missing)}')

    split_scenes: list[dict[str, Any]] = []
    for scene_id in sorted(expected):
        scene = dict(source_scenes[scene_id])
        split = 'train' if scene_id in DEFAULT_TRAIN_SCENES else 'val'
        scene['split'] = split
        scene['stack_ref'] = _runtime_ref(str(scene['stack_ref']), local_root=local_root, runtime_root=runtime_root)
        scene['truth_mask_ref'] = _runtime_ref(str(scene['truth_mask_ref']), local_root=local_root, runtime_root=runtime_root)
        metadata = scene.get('metadata') if isinstance(scene.get('metadata'), dict) else {}
        scene['metadata'] = {
            **metadata,
            'shadow_split_policy': 'avalcd_train5_val2_v1',
            'license_review_id': license_review_id,
        }
        split_scenes.append(scene)

    manifest = {
        'version': 'sar_training_manifest_v1',
        'dataset_version': f'{snapshot_id}-sar',
        'snapshot_id': snapshot_id,
        'license_review_id': license_review_id,
        'split_policy': {
            'name': 'avalcd_train5_val2_v1',
            'train_scene_ids': sorted(DEFAULT_TRAIN_SCENES),
            'val_scene_ids': sorted(DEFAULT_VAL_SCENES),
            'authoritative_test_scene_ids': [],
        },
        'scenes': split_scenes,
    }
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    request = {
        'training_manifest_path': '/artifacts/european-shadow-sar/avalcd-shadow-v1/manifests/avalcd_shadow_train5_val2.json',
        'source_key': 'avalcd_zenodo_v1',
        'license_review_id': license_review_id,
        'model_family': DEFAULT_MODEL_FAMILY,
        'patch_size': DEFAULT_PATCH_SIZE,
        'stride': DEFAULT_STRIDE,
        'epochs': DEFAULT_EPOCHS,
        'batch_size': DEFAULT_BATCH_SIZE,
        'learning_rate': DEFAULT_LEARNING_RATE,
        'loss': DEFAULT_LOSS,
        'f_beta': DEFAULT_F_BETA,
        'precision_floor': DEFAULT_PRECISION_FLOOR,
        'materialized_dataset_root': DEFAULT_MATERIALIZED_DATASET_ROOT,
        'candidate_model_version': candidate_model_version,
        'export_validation_prediction_artifact': True,
        'train_scene_ids': sorted(DEFAULT_TRAIN_SCENES),
        'validation_scene_ids': sorted(DEFAULT_VAL_SCENES),
    }
    request_path = output.parent / 'train_sar_unet_request.json'
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    return {
        'status': 'ok',
        'manifest_path': str(output),
        'request_path': str(request_path),
        'snapshot_id': snapshot_id,
        'train_scene_count': len(DEFAULT_TRAIN_SCENES),
        'val_scene_count': len(DEFAULT_VAL_SCENES),
        'license_review_id': license_review_id,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a governed AvalCD train/val SAR shadow manifest.')
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--local-assembled-root', type=Path, required=True)
    parser.add_argument('--runtime-assembled-root', required=True)
    parser.add_argument('--snapshot-id', required=True)
    parser.add_argument('--license-review', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-model-version', default=DEFAULT_CANDIDATE_MODEL_VERSION)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_avalcd_shadow_split_manifest(
        source_manifest=args.source_manifest,
        local_assembled_root=args.local_assembled_root,
        runtime_assembled_root=args.runtime_assembled_root,
        snapshot_id=args.snapshot_id,
        license_review_id=args.license_review,
        output=args.output,
        candidate_model_version=args.candidate_model_version,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
