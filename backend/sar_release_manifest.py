from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.sar_release_refs import (
    SAR_RELEASE_ACTIVE_STATUS,
    load_reference_bundle,
    reference_item_to_scene,
)


DEFAULT_HELDOUT_PREFIX = 'heldout'
SUPPORTED_TRUTH_SUFFIXES = {'.npy', '.npz', '.tif', '.tiff'}


@dataclass(frozen=True)
class ReleaseManifestOptions:
    split: str | None = None
    bucket: str = 'sar-masks'
    heldout_prefix: str = DEFAULT_HELDOUT_PREFIX
    baseline_margin: float = 0.05
    validate_refs: bool = True
    prediction_model_version: str = 'sar_unet_resnet34_shadow_v1'
    reference_set_key: str | None = None
    authoritative_only: bool = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_suffix(value: str) -> str:
    suffix = value.strip().lower()
    if not suffix.startswith('.'):
        suffix = f'.{suffix}'
    if suffix not in SUPPORTED_TRUTH_SUFFIXES:
        raise ValueError(
            f'unsupported truth_mask_format "{value}". '
            'Use one of: .npy, .npz, .tif, .tiff',
        )
    return suffix


def _default_mask_ref(
    *,
    bucket: str,
    heldout_prefix: str,
    split: str,
    region_key: str,
    scene_id: str,
    filename: str,
) -> str:
    return f'{bucket}/{heldout_prefix}/{split}/{region_key}/{scene_id}/{filename}'


def _load_scene_registry(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == '.json':
        payload = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            scenes = payload.get('scenes')
            if isinstance(scenes, list):
                return [item for item in scenes if isinstance(item, dict)]
        raise ValueError('scene registry JSON must be a list of scenes or an object with scenes[]')

    if suffix == '.csv':
        with path.open('r', encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    raise ValueError(f'unsupported scene registry format "{path.suffix}". Use .json or .csv')


def _parse_optional_json(value: Any, *, field_name: str) -> dict[str, Any] | None:
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f'{field_name} must be a JSON object')


def _normalize_scene_record(
    raw: dict[str, Any],
    *,
    options: ReleaseManifestOptions,
) -> dict[str, Any]:
    scene_id = str(raw.get('scene_id') or raw.get('sceneName') or raw.get('id') or '').strip()
    region_key = str(raw.get('region_key') or raw.get('region') or '').strip()
    if not scene_id:
        raise ValueError('every registry scene must include scene_id')
    if not region_key:
        raise ValueError(f'scene "{scene_id}" is missing region_key')

    prediction_mask = raw.get('prediction_mask')
    if not isinstance(prediction_mask, str) or not prediction_mask.strip():
        prediction_mask = _default_mask_ref(
            bucket=options.bucket,
            heldout_prefix=options.heldout_prefix,
            split=options.split,
            region_key=region_key,
            scene_id=scene_id,
            filename='prediction_mask.tif',
        )

    truth_mask = raw.get('truth_mask')
    if isinstance(truth_mask, str) and truth_mask.strip():
        normalized_truth_mask = truth_mask.strip()
    else:
        truth_mask_format = raw.get('truth_mask_format')
        if not isinstance(truth_mask_format, str) or not truth_mask_format.strip():
            raise ValueError(
                f'scene "{scene_id}" must include truth_mask or truth_mask_format so the held-out truth ref can be derived',
            )
        suffix = _normalize_suffix(truth_mask_format)
        normalized_truth_mask = _default_mask_ref(
            bucket=options.bucket,
            heldout_prefix=options.heldout_prefix,
            split=options.split,
            region_key=region_key,
            scene_id=scene_id,
            filename=f'truth_mask{suffix}',
        )

    baseline_mask = raw.get('baseline_mask')
    baseline_metrics = _parse_optional_json(raw.get('baseline_metrics'), field_name='baseline_metrics')
    baseline_f1_floor_raw = raw.get('baseline_f1_floor')
    baseline_f1_floor = float(baseline_f1_floor_raw) if baseline_f1_floor_raw not in (None, '') else None
    if baseline_mask in (None, '') and baseline_metrics is None and baseline_f1_floor is None:
        baseline_mask = _default_mask_ref(
            bucket=options.bucket,
            heldout_prefix=options.heldout_prefix,
            split=options.split,
            region_key=region_key,
            scene_id=scene_id,
            filename='baseline_mask.tif',
        )

    scene: dict[str, Any] = {
        'scene_id': scene_id,
        'region_key': region_key,
        'prediction_mask': str(prediction_mask).strip(),
        'truth_mask': normalized_truth_mask,
    }
    if isinstance(baseline_mask, str) and baseline_mask.strip():
        scene['baseline_mask'] = baseline_mask.strip()
    if baseline_metrics is not None:
        scene['baseline_metrics'] = baseline_metrics
    if baseline_f1_floor is not None:
        scene['baseline_f1_floor'] = baseline_f1_floor
    if isinstance(raw.get('scene_time'), str) and raw['scene_time'].strip():
        scene['scene_time'] = raw['scene_time'].strip()
    return scene


def _validate_scene_uniqueness(scenes: list[dict[str, Any]]) -> None:
    by_scene_id: dict[str, str] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for scene in scenes:
        scene_id = str(scene['scene_id'])
        region_key = str(scene['region_key'])
        pair = (region_key, scene_id)
        if pair in seen_pairs:
            raise ValueError(f'duplicate held-out scene entry for region_key="{region_key}" scene_id="{scene_id}"')
        seen_pairs.add(pair)
        prior_region = by_scene_id.get(scene_id)
        if prior_region is not None and prior_region != region_key:
            raise ValueError(
                f'scene_id "{scene_id}" appears in multiple regions ("{prior_region}" and "{region_key}")',
            )
        by_scene_id[scene_id] = region_key


def _validate_scene_refs(scenes: list[dict[str, Any]]) -> None:
    from backend.sar_unet_worker import _load_mask_array

    for scene in scenes:
        _load_mask_array(scene['prediction_mask'])
        _load_mask_array(scene['truth_mask'])
        if scene.get('baseline_mask') is not None:
            _load_mask_array(scene['baseline_mask'])


def build_release_manifest(
    registry: list[dict[str, Any]],
    *,
    options: ReleaseManifestOptions,
) -> dict[str, Any]:
    if not options.split:
        raise ValueError('split is required when building a release manifest from an ad hoc registry')
    scenes = [_normalize_scene_record(raw, options=options) for raw in registry]
    _validate_scene_uniqueness(scenes)
    if options.validate_refs:
        _validate_scene_refs(scenes)
    return {
        'split': options.split,
        'baseline_margin': options.baseline_margin,
        'generated_at': _utc_now_iso(),
        'scenes': scenes,
    }


def build_release_manifest_from_reference_set(
    *,
    reference_set_key: str,
    options: ReleaseManifestOptions,
) -> dict[str, Any]:
    set_row, items = load_reference_bundle(
        reference_set_key,
        authoritative_only=options.authoritative_only,
        status=SAR_RELEASE_ACTIVE_STATUS if options.authoritative_only else None,
    )
    scenes = [
        reference_item_to_scene(
            set_row,
            item,
            model_version=options.prediction_model_version,
        )
        for item in items
    ]
    _validate_scene_uniqueness(scenes)
    for scene in scenes:
        if not scene.get('truth_mask'):
            raise ValueError(f'reference set "{reference_set_key}" contains a scene without truth_mask')
        if not scene.get('baseline_mask'):
            raise ValueError(f'reference set "{reference_set_key}" contains a scene without baseline_mask')
        if not scene.get('prediction_mask'):
            raise ValueError(f'reference set "{reference_set_key}" contains a scene without prediction_mask')
    if options.validate_refs:
        _validate_scene_refs(scenes)
    return {
        'reference_set_key': reference_set_key,
        'source_name': set_row.get('source_name'),
        'source_version': set_row.get('source_version'),
        'split': set_row.get('split_name'),
        'baseline_margin': options.baseline_margin,
        'generated_at': _utc_now_iso(),
        'authoritative': bool(set_row.get('authoritative')),
        'prediction_model_version': options.prediction_model_version,
        'scenes': scenes,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a held-out SAR release evaluation manifest')
    parser.add_argument('--registry', type=Path, help='Scene registry in JSON or CSV format')
    parser.add_argument('--reference-set-key', help='Authoritative held-out SnowSlide reference-set key from Supabase')
    parser.add_argument('--split', help='Held-out split name, used in default storage refs for ad hoc registries')
    parser.add_argument('--bucket', default='sar-masks', help='Storage bucket for derived mask refs')
    parser.add_argument('--heldout-prefix', default=DEFAULT_HELDOUT_PREFIX, help='Storage prefix under the bucket')
    parser.add_argument('--baseline-margin', type=float, default=0.05, help='Baseline margin for evaluate-release')
    parser.add_argument('--prediction-model-version', default='sar_unet_resnet34_shadow_v1', help='Model version used to derive held-out prediction mask refs')
    parser.add_argument('--authoritative-only', dest='authoritative_only', action='store_true', default=True, help='Require the reference set to be authoritative (default)')
    parser.add_argument('--allow-non-authoritative', dest='authoritative_only', action='store_false', help='Allow draft/non-authoritative reference sets')
    parser.add_argument('--output', type=Path, help='Optional output path for the generated manifest JSON')
    parser.add_argument('--skip-validate-refs', action='store_true', help='Skip worker-side mask ref validation')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.registry and not args.reference_set_key:
        raise SystemExit('Provide either --registry or --reference-set-key')
    if args.registry and args.reference_set_key:
        raise SystemExit('Use either --registry or --reference-set-key, not both')

    options = ReleaseManifestOptions(
        split=args.split,
        bucket=args.bucket,
        heldout_prefix=args.heldout_prefix,
        baseline_margin=args.baseline_margin,
        validate_refs=not args.skip_validate_refs,
        prediction_model_version=args.prediction_model_version,
        reference_set_key=args.reference_set_key,
        authoritative_only=bool(args.authoritative_only),
    )
    if args.reference_set_key:
        manifest = build_release_manifest_from_reference_set(
            reference_set_key=args.reference_set_key,
            options=options,
        )
    else:
        registry = _load_scene_registry(args.registry)
        manifest = build_release_manifest(
            registry,
            options=options,
        )
    payload = json.dumps(manifest, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(payload + '\n', encoding='utf-8')
    else:
        print(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
