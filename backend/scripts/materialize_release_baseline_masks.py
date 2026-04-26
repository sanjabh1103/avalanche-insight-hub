from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.sar_release_refs import (
    SAR_RELEASE_BUCKET,
    activate_reference_set,
    build_release_asset_ref,
    item_bbox,
    load_reference_bundle,
    parse_storage_ref,
)
from backend.common.storage_io import storage_upload_bytes
from backend.common.supabase_io import rest_upsert
from backend.gee_extractor import GEE_VH_THRESHOLD_DB, GEE_VV_THRESHOLD_DB
from backend.sar_unet_worker import encode_mask_geotiff, load_scene_stack


def _baseline_mask_from_stack(stack: np.ndarray) -> np.ndarray:
    if stack.shape[0] != 2:
        raise ValueError(f'expected 2-channel held-out stack, received {stack.shape}')
    vv = np.asarray(stack[0], dtype=np.float32)
    vh = np.asarray(stack[1], dtype=np.float32)
    return np.asarray((vv < GEE_VV_THRESHOLD_DB) & (vh < GEE_VH_THRESHOLD_DB), dtype=np.float32)


def materialize_baseline_masks(
    *,
    reference_set_key: str,
    bucket: str = SAR_RELEASE_BUCKET,
    activate: bool = True,
) -> dict[str, Any]:
    set_row, items = load_reference_bundle(reference_set_key, authoritative_only=False, status=None)
    updated_rows: list[dict[str, Any]] = []
    for item in items:
        scene_id = str(item.get('external_scene_id') or '')
        region_key = str(item.get('region_key') or 'unknown')
        split = str((item.get('metadata') or {}).get('split') or set_row.get('split_name') or '').strip()
        if not split:
            raise ValueError(f'reference item "{scene_id}" is missing split metadata')
        bbox = item_bbox(item)
        stack = load_scene_stack({
            'scene_id': scene_id,
            'region_key': region_key,
            'stack_ref': item.get('stack_asset_ref'),
        })
        baseline_mask = _baseline_mask_from_stack(stack)
        baseline_asset_ref = build_release_asset_ref(
            dataset_version=str(set_row.get('source_version') or 'unknown'),
            split=split,
            region_key=region_key,
            scene_id=scene_id,
            filename='baseline_mask.tif',
            bucket=bucket,
        )
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
        updated_rows.append({
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
        })
    if updated_rows:
        rest_upsert('sar_release_reference_items', updated_rows, on_conflict='id')
    activated_row = activate_reference_set(reference_set_key) if activate else set_row
    return {
        'status': 'ok',
        'reference_set_key': reference_set_key,
        'scene_count': len(items),
        'baseline_rows_materialized': len(updated_rows),
        'reference_set_status': str(activated_row.get('status') or set_row.get('status') or 'draft'),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Materialize held-out GEE-threshold baseline masks for an authoritative SnowSlide reference set')
    parser.add_argument('--reference-set-key', required=True, help='Registered SnowSlide held-out reference-set key')
    parser.add_argument('--bucket', default=SAR_RELEASE_BUCKET, help='Supabase storage bucket for held-out assets')
    parser.add_argument('--no-activate', action='store_true', help='Do not mark the completed set active after baseline generation')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = materialize_baseline_masks(
        reference_set_key=args.reference_set_key,
        bucket=args.bucket,
        activate=not args.no_activate,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
