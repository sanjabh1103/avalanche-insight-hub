from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.avalcd_manifest import AVALCD_SCENE_MANIFEST_FILENAME
from backend.common.sar_release_refs import (
    SAR_RELEASE_BUCKET,
    activate_reference_set,
    build_release_asset_ref,
    item_bbox,
    load_reference_bundle,
    parse_storage_ref,
)
from backend.common.storage_io import storage_download_bytes, storage_upload_bytes
from backend.common.supabase_io import SupabaseError, rest_upsert
from backend.gee_extractor import GEE_VH_THRESHOLD_DB, GEE_VV_THRESHOLD_DB
from backend.sar_unet_worker import encode_mask_geotiff, load_scene_stack


def _baseline_mask_from_stack(stack: np.ndarray) -> np.ndarray:
    if stack.shape[0] != 2:
        raise ValueError(f'expected 2-channel held-out stack, received {stack.shape}')
    vv = np.asarray(stack[0], dtype=np.float32)
    vh = np.asarray(stack[1], dtype=np.float32)
    return np.asarray((vv < GEE_VV_THRESHOLD_DB) & (vh < GEE_VH_THRESHOLD_DB), dtype=np.float32)


def _split_name(item: dict[str, Any], set_row: dict[str, Any]) -> str:
    split = str((item.get('metadata') or {}).get('split') or set_row.get('split_name') or '').strip()
    if not split:
        scene_id = str(item.get('external_scene_id') or '')
        raise ValueError(f'reference item "{scene_id}" is missing split metadata')
    return split


def _local_stack_ref(
    *,
    source_dir: Path,
    split: str,
    region_key: str,
    scene_id: str,
) -> str | None:
    scene_root = source_dir / split / region_key / scene_id
    manifest_path = scene_root / AVALCD_SCENE_MANIFEST_FILENAME
    if manifest_path.exists():
        return str(manifest_path)
    stack_path = scene_root / 'stack.npz'
    if stack_path.exists():
        return str(stack_path)
    return None


def _load_scene_stack_from_item(
    *,
    item: dict[str, Any],
    set_row: dict[str, Any],
    source_dir: Path | None,
) -> np.ndarray:
    scene_id = str(item.get('external_scene_id') or '')
    region_key = str(item.get('region_key') or 'unknown')
    split = _split_name(item, set_row)
    scene = {
        'scene_id': scene_id,
        'region_key': region_key,
        'stack_ref': item.get('stack_asset_ref'),
    }
    if source_dir is not None:
        local_ref = _local_stack_ref(
            source_dir=source_dir,
            split=split,
            region_key=region_key,
            scene_id=scene_id,
        )
        if local_ref:
            scene['stack_ref'] = local_ref
    return load_scene_stack(scene)


def _baseline_asset_exists(asset_ref: str) -> bool:
    asset_ref = str(asset_ref or '').strip()
    if not asset_ref:
        return False
    bucket, object_path = parse_storage_ref(asset_ref)
    try:
        storage_download_bytes(bucket=bucket, object_path=object_path)
    except SupabaseError:
        return False
    return True


def materialize_baseline_masks(
    *,
    reference_set_key: str,
    bucket: str = SAR_RELEASE_BUCKET,
    activate: bool = True,
    source_dir: Path | str | None = None,
) -> dict[str, Any]:
    local_source_dir = Path(source_dir) if source_dir is not None else None
    set_row, items = load_reference_bundle(reference_set_key, authoritative_only=False, status=None)
    completed_count = 0
    for item in items:
        scene_id = str(item.get('external_scene_id') or '')
        region_key = str(item.get('region_key') or 'unknown')
        split = _split_name(item, set_row)
        bbox = item_bbox(item)
        existing_baseline_asset_ref = str(item.get('baseline_mask_asset_ref') or '').strip()
        baseline_asset_ref = existing_baseline_asset_ref or build_release_asset_ref(
            dataset_version=str(set_row.get('source_version') or 'unknown'),
            split=split,
            region_key=region_key,
            scene_id=scene_id,
            filename='baseline_mask.tif',
            bucket=bucket,
        )
        if not (existing_baseline_asset_ref and _baseline_asset_exists(existing_baseline_asset_ref)):
            stack = _load_scene_stack_from_item(
                item=item,
                set_row=set_row,
                source_dir=local_source_dir,
            )
            baseline_mask = _baseline_mask_from_stack(stack)
            upload_bucket, object_path = parse_storage_ref(baseline_asset_ref)
            storage_upload_bytes(
                bucket=upload_bucket,
                object_path=object_path,
                payload=encode_mask_geotiff(baseline_mask, bbox=tuple(float(value) for value in bbox)),
                content_type='image/tiff',
            )
        metadata = dict(item.get('metadata') or {})
        metadata.update({
            'baseline_source_model': 'gee_threshold_baseline_v1',
            'vv_threshold_db': GEE_VV_THRESHOLD_DB,
            'vh_threshold_db': GEE_VH_THRESHOLD_DB,
        })
        rest_upsert('sar_release_reference_items', [{
            'id': item['id'],
            'reference_set_id': item['reference_set_id'],
            'external_scene_id': scene_id,
            'region_key': region_key,
            'scene_time': item.get('scene_time'),
            'bbox': bbox,
            'stack_asset_ref': item['stack_asset_ref'],
            'truth_mask_asset_ref': item['truth_mask_asset_ref'],
            'baseline_mask_asset_ref': baseline_asset_ref,
            'metadata': metadata,
        }], on_conflict='id')
        completed_count += 1
    activated_row = activate_reference_set(reference_set_key) if activate else set_row
    return {
        'status': 'ok',
        'reference_set_key': reference_set_key,
        'scene_count': len(items),
        'baseline_rows_materialized': completed_count,
        'reference_set_status': str(activated_row.get('status') or set_row.get('status') or 'draft'),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Materialize held-out GEE-threshold baseline masks for an authoritative SnowSlide reference set')
    parser.add_argument('--reference-set-key', required=True, help='Registered SnowSlide held-out reference-set key')
    parser.add_argument('--bucket', default=SAR_RELEASE_BUCKET, help='Supabase storage bucket for held-out assets')
    parser.add_argument('--source-dir', type=Path, help='Optional local assembled held-out directory to prefer over remote storage assets')
    parser.add_argument('--no-activate', action='store_true', help='Do not mark the completed set active after baseline generation')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = materialize_baseline_masks(
        reference_set_key=args.reference_set_key,
        bucket=args.bucket,
        activate=not args.no_activate,
        source_dir=args.source_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
