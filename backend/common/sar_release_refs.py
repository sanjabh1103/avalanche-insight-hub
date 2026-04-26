from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.common.supabase_io import rest_get, rest_upsert


SAR_RELEASE_SOURCE_NAME = 'snowslide_slf'
SAR_RELEASE_PURPOSE = 'sar_release_gate'
SAR_RELEASE_BUCKET = 'sar-masks'
SAR_RELEASE_PREFIX = 'heldout/snowslide'
SAR_RELEASE_ACTIVE_STATUS = 'active'


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_jsonish(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def normalize_reference_set(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized['authoritative'] = bool(row.get('authoritative', False))
    return normalized


def normalize_reference_item(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized['bbox'] = _decode_jsonish(row.get('bbox'), [])
    normalized['metadata'] = _decode_jsonish(row.get('metadata'), {})
    return normalized


def build_release_object_path(
    *,
    dataset_version: str,
    split: str,
    region_key: str,
    scene_id: str,
    filename: str,
    prefix: str = SAR_RELEASE_PREFIX,
) -> str:
    return f'{prefix}/{dataset_version}/{split}/{region_key}/{scene_id}/{filename}'


def build_release_asset_ref(
    *,
    dataset_version: str,
    split: str,
    region_key: str,
    scene_id: str,
    filename: str,
    bucket: str = SAR_RELEASE_BUCKET,
    prefix: str = SAR_RELEASE_PREFIX,
) -> str:
    return f'{bucket}/{build_release_object_path(dataset_version=dataset_version, split=split, region_key=region_key, scene_id=scene_id, filename=filename, prefix=prefix)}'


def build_prediction_asset_ref(
    *,
    dataset_version: str,
    split: str,
    region_key: str,
    scene_id: str,
    model_version: str,
    bucket: str = SAR_RELEASE_BUCKET,
    prefix: str = SAR_RELEASE_PREFIX,
) -> str:
    return build_release_asset_ref(
        dataset_version=dataset_version,
        split=split,
        region_key=region_key,
        scene_id=scene_id,
        filename=f'predictions/{model_version}/prediction_mask.tif',
        bucket=bucket,
        prefix=prefix,
    )


def parse_storage_ref(asset_ref: str) -> tuple[str, str]:
    bucket, sep, object_path = str(asset_ref).partition('/')
    if not sep or not bucket or not object_path:
        raise ValueError(f'invalid storage ref "{asset_ref}"')
    return bucket, object_path


def load_reference_set(
    set_key: str,
    *,
    authoritative_only: bool = True,
    status: str | None = SAR_RELEASE_ACTIVE_STATUS,
) -> dict[str, Any]:
    params = {
        'select': '*',
        'set_key': f'eq.{set_key}',
        'limit': '1',
    }
    if authoritative_only:
        params['authoritative'] = 'eq.true'
    if status:
        params['status'] = f'eq.{status}'
    rows = rest_get('sar_release_reference_sets', params=params)
    if not rows:
        qualifier = f' authoritative status={status}' if status else ' authoritative'
        raise ValueError(f'no{qualifier} reference set found for set_key="{set_key}"')
    return normalize_reference_set(rows[0])


def load_reference_items(reference_set_id: str) -> list[dict[str, Any]]:
    rows = rest_get('sar_release_reference_items', params={
        'select': '*',
        'reference_set_id': f'eq.{reference_set_id}',
        'order': 'scene_time.asc,external_scene_id.asc',
        'limit': '10000',
    })
    return [normalize_reference_item(row) for row in rows]


def load_reference_bundle(
    set_key: str,
    *,
    authoritative_only: bool = True,
    status: str | None = SAR_RELEASE_ACTIVE_STATUS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    set_row = load_reference_set(set_key, authoritative_only=authoritative_only, status=status)
    items = load_reference_items(str(set_row['id']))
    if not items:
        raise ValueError(f'reference set "{set_key}" has no registered scenes')
    return set_row, items


def item_split(item: dict[str, Any], set_row: dict[str, Any]) -> str:
    metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
    split = metadata.get('split')
    if isinstance(split, str) and split.strip():
        return split.strip()
    split_name = str(set_row.get('split_name') or '').strip()
    if split_name:
        return split_name
    raise ValueError(f'reference item "{item.get("external_scene_id")}" is missing split metadata')


DEFAULT_MOCK_BBOX = [-107.0, 39.0, -106.0, 40.0]


def item_bbox(item: dict[str, Any]) -> list[float]:
    bbox = item.get('bbox')
    if not isinstance(bbox, list) or len(bbox) != 4:
        metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
        fallback = metadata.get('bbox')
        if isinstance(fallback, list) and len(fallback) == 4:
            return [float(value) for value in fallback]
        return list(DEFAULT_MOCK_BBOX)
    return [float(value) for value in bbox]


def reference_item_to_scene(
    set_row: dict[str, Any],
    item: dict[str, Any],
    *,
    model_version: str,
) -> dict[str, Any]:
    split = item_split(item, set_row)
    scene_id = str(item.get('external_scene_id') or '')
    if not scene_id:
        raise ValueError('reference item is missing external_scene_id')
    stack_asset_ref = str(item.get('stack_asset_ref') or '').strip()
    truth_mask_asset_ref = str(item.get('truth_mask_asset_ref') or '').strip()
    baseline_mask_asset_ref = str(item.get('baseline_mask_asset_ref') or '').strip()
    if not stack_asset_ref or not truth_mask_asset_ref:
        raise ValueError(f'reference item "{scene_id}" is missing stack or truth refs')
    return {
        'scene_id': scene_id,
        'external_scene_id': scene_id,
        'region_key': str(item.get('region_key') or 'unknown'),
        'scene_time': item.get('scene_time'),
        'bbox': item_bbox(item),
        'stack_ref': stack_asset_ref,
        'truth_mask': truth_mask_asset_ref,
        'baseline_mask': baseline_mask_asset_ref or None,
        'prediction_mask': build_prediction_asset_ref(
            dataset_version=str(set_row.get('source_version') or 'unknown'),
            split=split,
            region_key=str(item.get('region_key') or 'unknown'),
            scene_id=scene_id,
            model_version=model_version,
        ),
    }


def activate_reference_set(set_key: str) -> dict[str, Any]:
    target = load_reference_set(set_key, authoritative_only=False, status=None)
    active_rows = rest_get('sar_release_reference_sets', params={
        'select': 'id,set_key',
        'hazard_type': f"eq.{target.get('hazard_type') or 'avalanche'}",
        'purpose': f"eq.{target.get('purpose') or SAR_RELEASE_PURPOSE}",
        'authoritative': 'eq.true',
        'status': f'eq.{SAR_RELEASE_ACTIVE_STATUS}',
        'limit': '100',
    })
    retire_rows = [
        {'id': row['id'], 'status': 'retired', 'updated_at': _utc_now_iso()}
        for row in active_rows
        if str(row.get('id')) != str(target.get('id'))
    ]
    if retire_rows:
        rest_upsert('sar_release_reference_sets', retire_rows, on_conflict='id')
    updated = rest_upsert('sar_release_reference_sets', [{
        **target,
        'authoritative': True,
        'status': SAR_RELEASE_ACTIVE_STATUS,
        'updated_at': _utc_now_iso(),
    }], on_conflict='id')
    return normalize_reference_set(updated[0] if updated else target)
