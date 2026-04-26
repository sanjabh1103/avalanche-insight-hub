from __future__ import annotations

import argparse
import csv
import contextlib
import io
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import requests

from backend.common.sar_release_refs import (
    SAR_RELEASE_BUCKET,
    SAR_RELEASE_PREFIX,
    SAR_RELEASE_PURPOSE,
    SAR_RELEASE_SOURCE_NAME,
    build_release_asset_ref,
)
from backend.common.storage_io import storage_upload_bytes, storage_upsert_json
from backend.common.supabase_io import rest_upsert
from backend.sar_unet_worker import _normalize_stack

try:  # pragma: no cover - optional dependency at runtime
    from rasterio.io import MemoryFile
except Exception:  # pragma: no cover - optional dependency
    MemoryFile = None


SUPPORTED_SPLITS = {'validation', 'val', 'test'}
TRUTH_SUFFIXES = {'.tif', '.tiff'}
STACK_SUFFIXES = {'.npz', '.npy'}
SAR_STACK_SUFFIXES = STACK_SUFFIXES | TRUTH_SUFFIXES
OPTICAL_SUFFIXES = {'.jpg', '.jpeg', '.png'}


@dataclass(frozen=True)
class ArchivedScene:
    external_scene_id: str
    split: str
    region_key: str
    truth_member: str
    stack_member: str | None = None
    vv_member: str | None = None
    vh_member: str | None = None
    scene_time: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any] | None = None
    optical_members: tuple[str, ...] = ()


def _normalize_split(value: str) -> str:
    split = value.strip().lower()
    if split == 'val':
        return 'validation'
    if split not in {'validation', 'test'}:
        raise ValueError(f'unsupported split "{value}"; only validation/test are allowed')
    return split


def _normalize_bbox(value: Any, *, scene_id: str) -> list[float] | None:
    if value in (None, '', []):
        return None
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 4:
        raise ValueError(f'scene "{scene_id}" bbox must be a 4-element list')
    return [float(item) for item in parsed]


def _normalize_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in values:
        key, sep, value = raw.partition(':')
        if not sep or not key.strip():
            raise ValueError(f'invalid --header value "{raw}" (expected "Key: Value")')
        headers[key.strip()] = value.strip()
    return headers


def _download_source_archive_to_tempfile(
    *,
    source_url: str,
    headers: dict[str, str],
    timeout: int,
) -> Path:
    response = requests.get(source_url, headers=headers, timeout=timeout, stream=True)
    response.raise_for_status()
    handle = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    try:
        with handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    finally:
        response.close()
    return Path(handle.name)


@contextlib.contextmanager
def _open_archive_from_args(args: argparse.Namespace) -> Any:
    temp_archive_path: Path | None = None
    if args.source_zip:
        archive_path = args.source_zip
    elif args.source_url:
        temp_archive_path = _download_source_archive_to_tempfile(
            source_url=args.source_url,
            headers=_normalize_headers(args.header or []),
            timeout=args.timeout,
        )
        archive_path = temp_archive_path
    else:
        raise ValueError('Provide either --source-url or --source-zip')

    try:
        with zipfile.ZipFile(archive_path) as archive:
            yield archive
    finally:
        if temp_archive_path is not None:
            temp_archive_path.unlink(missing_ok=True)


def _candidate_registry_members(names: list[str]) -> list[str]:
    candidates: list[str] = []
    for name in names:
        lowered = name.lower()
        if lowered.endswith(('.json', '.csv')) and any(token in lowered for token in ('registry', 'scene', 'manifest', 'index', 'metadata')):
            candidates.append(name)
    return candidates


def _read_registry_member(archive: zipfile.ZipFile, member_name: str) -> list[dict[str, Any]]:
    payload = archive.read(member_name)
    suffix = Path(member_name).suffix.lower()
    if suffix == '.json':
        parsed = json.loads(payload.decode('utf-8'))
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        if isinstance(parsed, dict) and isinstance(parsed.get('scenes'), list):
            return [row for row in parsed['scenes'] if isinstance(row, dict)]
        raise ValueError(f'registry member "{member_name}" must contain a list of scenes')
    if suffix == '.csv':
        text = io.StringIO(payload.decode('utf-8'))
        return [dict(row) for row in csv.DictReader(text)]
    raise ValueError(f'unsupported registry member "{member_name}"')


def _record_member(
    record: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lstrip('./')
    return None


def _scene_id_from_path(path: PurePosixPath) -> str:
    parts = [part for part in path.parts if part]
    if len(parts) >= 2:
        return parts[-2]
    return path.stem


def _region_from_path(path: PurePosixPath, split: str) -> str:
    parts = [part for part in path.parts if part]
    for idx, part in enumerate(parts):
        normalized = part.lower()
        if normalized in {split, 'val' if split == 'validation' else split} and idx + 1 < len(parts):
            return parts[idx + 1]
    if len(parts) >= 3:
        return parts[-3]
    raise ValueError(f'could not infer region_key from archive path "{path}"')


def _infer_split_from_path(member_name: str) -> str | None:
    lowered_parts = [part.lower() for part in PurePosixPath(member_name).parts]
    for part in lowered_parts:
        if part in SUPPORTED_SPLITS:
            return _normalize_split(part)
    return None


def _normalize_scene_record(
    record: dict[str, Any],
    *,
    default_split: str | None = None,
) -> ArchivedScene:
    scene_id = str(
        record.get('external_scene_id')
        or record.get('scene_id')
        or record.get('id')
        or ''
    ).strip()
    split_value = str(record.get('split') or default_split or '').strip()
    if not scene_id:
        raise ValueError('every registry scene must include scene_id/external_scene_id')
    if not split_value:
        raise ValueError(f'scene "{scene_id}" is missing split')
    split = _normalize_split(split_value)
    region_key = str(record.get('region_key') or record.get('region') or '').strip()
    if not region_key:
        raise ValueError(f'scene "{scene_id}" is missing region_key')
    truth_member = _record_member(record, keys=('truth_member', 'truth_mask_member', 'truth_mask_path', 'mask_path', 'label_path'))
    if not truth_member:
        raise ValueError(f'scene "{scene_id}" is missing truth mask member path')
    stack_member = _record_member(record, keys=('stack_member', 'stack_path', 'stack_archive_path'))
    vv_member = _record_member(record, keys=('vv_member', 'vv_path'))
    vh_member = _record_member(record, keys=('vh_member', 'vh_path'))
    bbox = _normalize_bbox(record.get('bbox'), scene_id=scene_id)
    metadata = dict(record)
    optical_members = tuple(
        str(item).strip()
        for item in record.get('optical_members', ())
        if isinstance(item, str) and item.strip()
    )
    if not stack_member and not (vv_member and vh_member) and not optical_members:
        raise ValueError(f'scene "{scene_id}" must include stack_member or both vv_member and vh_member')
    for key in ('external_scene_id', 'scene_id', 'id', 'split', 'region_key', 'region', 'truth_member', 'truth_mask_member', 'truth_mask_path', 'mask_path', 'label_path', 'stack_member', 'stack_path', 'stack_archive_path', 'vv_member', 'vv_path', 'vh_member', 'vh_path', 'bbox', 'optical_members'):
        metadata.pop(key, None)
    return ArchivedScene(
        external_scene_id=scene_id,
        split=split,
        region_key=region_key,
        truth_member=truth_member,
        stack_member=stack_member,
        vv_member=vv_member,
        vh_member=vh_member,
        scene_time=str(record.get('scene_time') or record.get('timestamp') or '').strip() or None,
        bbox=bbox,
        metadata=metadata,
        optical_members=optical_members,
    )


def _infer_scenes_from_archive(
    archive: zipfile.ZipFile,
    *,
    default_split: str | None = None,
) -> list[ArchivedScene]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    normalized_default_split = _normalize_split(default_split) if default_split else None
    for member_name in archive.namelist():
        info = archive.getinfo(member_name)
        if info.is_dir():
            continue
        split = _infer_split_from_path(member_name) or normalized_default_split
        if split is None:
            continue
        path = PurePosixPath(member_name)
        scene_id = _scene_id_from_path(path)
        region_key = _region_from_path(path, split)
        key = (split, region_key, scene_id)
        entry = grouped.setdefault(key, {
            'external_scene_id': scene_id,
            'split': split,
            'region_key': region_key,
            'metadata': {},
            'optical_members': [],
        })
        lowered = path.name.lower()
        suffix = path.suffix.lower()
        if suffix in TRUTH_SUFFIXES and any(token in lowered for token in ('truth', 'mask', 'label', 'target')):
            entry['truth_member'] = member_name
        elif suffix in STACK_SUFFIXES and 'stack' in lowered:
            entry['stack_member'] = member_name
        elif suffix in STACK_SUFFIXES and re.search(r'(^|[_-])vv([_.-]|$)', lowered):
            entry['vv_member'] = member_name
        elif suffix in STACK_SUFFIXES and re.search(r'(^|[_-])vh([_.-]|$)', lowered):
            entry['vh_member'] = member_name
        elif suffix in OPTICAL_SUFFIXES:
            entry['optical_members'].append(member_name)
    scenes = [_normalize_scene_record(entry, default_split=normalized_default_split) for entry in grouped.values()]
    if not scenes:
        raise ValueError('archive does not contain an inferable validation/test split with truth and stack refs')
    return scenes


def _load_archive_scenes(
    archive: zipfile.ZipFile,
    *,
    registry_member: str | None = None,
    default_split: str | None = None,
) -> list[ArchivedScene]:
    normalized_default_split = _normalize_split(default_split) if default_split else None
    if registry_member:
        records = _read_registry_member(archive, registry_member)
        return [_normalize_scene_record(record, default_split=normalized_default_split) for record in records]
    candidates = _candidate_registry_members(archive.namelist())
    if len(candidates) == 1:
        records = _read_registry_member(archive, candidates[0])
        return [_normalize_scene_record(record, default_split=normalized_default_split) for record in records]
    return _infer_scenes_from_archive(archive, default_split=normalized_default_split)


def _load_array_from_member_payload(payload: bytes, suffix: str) -> np.ndarray:
    if suffix == '.npz':
        loaded = np.load(io.BytesIO(payload))
        if 'stack' in loaded:
            return np.asarray(loaded['stack'], dtype=np.float32)
        return np.asarray(loaded[loaded.files[0]], dtype=np.float32)
    if suffix == '.npy':
        return np.asarray(np.load(io.BytesIO(payload)), dtype=np.float32)
    if suffix in {'.tif', '.tiff'}:
        if MemoryFile is None:
            raise RuntimeError('rasterio is required to convert GeoTIFF SAR stack members')
        with MemoryFile(payload) as memory_file:
            with memory_file.open() as dataset:
                return np.asarray(dataset.read(), dtype=np.float32)
    raise ValueError(f'unsupported stack member suffix "{suffix}"')


def _single_band_array(array: np.ndarray, *, scene: ArchivedScene, member_name: str) -> np.ndarray:
    normalized = np.asarray(array, dtype=np.float32)
    if normalized.ndim == 2:
        return normalized
    if normalized.ndim == 3 and normalized.shape[0] == 1:
        return np.asarray(normalized[0], dtype=np.float32)
    raise ValueError(
        f'scene "{scene.external_scene_id}" member "{member_name}" must resolve to a single VV or VH band; '
        f'received shape {normalized.shape}',
    )


def _derived_split_name(splits: list[str], *, fallback: str | None) -> str:
    normalized_fallback = str(fallback or '').strip()
    if splits:
        return '+'.join(splits) if len(splits) > 1 else splits[0]
    if normalized_fallback:
        return normalized_fallback
    return 'validation'


def _scene_has_optical_only_payload(scene: ArchivedScene) -> bool:
    return bool(scene.optical_members) and not scene.stack_member and not (scene.vv_member and scene.vh_member)


def _validate_scene_is_sar_compatible(archive: zipfile.ZipFile, scene: ArchivedScene) -> None:
    if _scene_has_optical_only_payload(scene):
        raise ValueError(
            f'scene "{scene.external_scene_id}" contains optical/webcam imagery ({", ".join(scene.optical_members)}) '
            'but no Sentinel-1 SAR stack or VV/VH members; optical datasets are invalid for the pinned SAR gate',
        )

    truth_suffix = Path(scene.truth_member).suffix.lower()
    if truth_suffix not in TRUTH_SUFFIXES:
        raise ValueError(
            f'scene "{scene.external_scene_id}" truth member must be GeoTIFF (.tif/.tiff); '
            f'received "{scene.truth_member}"',
        )

    if scene.stack_member:
        stack_suffix = Path(scene.stack_member).suffix.lower()
        if stack_suffix in OPTICAL_SUFFIXES:
            raise ValueError(
                f'scene "{scene.external_scene_id}" stack member "{scene.stack_member}" is optical imagery; '
                'a Sentinel-1 SAR archive must provide a 2-channel stack or VV/VH bands',
            )
        if stack_suffix not in SAR_STACK_SUFFIXES:
            raise ValueError(
                f'scene "{scene.external_scene_id}" stack member "{scene.stack_member}" uses unsupported suffix '
                f'"{stack_suffix}"; expected .npz, .npy, .tif, or .tiff',
            )
        stack = _load_array_from_member_payload(archive.read(scene.stack_member), stack_suffix)
        _normalize_stack(stack)
        return

    if not scene.vv_member or not scene.vh_member:
        raise ValueError(
            f'scene "{scene.external_scene_id}" is missing a Sentinel-1 SAR stack or paired VV/VH members; '
            'optical or incomplete archives are invalid for the pinned SAR gate',
        )

    for member_name in (scene.vv_member, scene.vh_member):
        suffix = Path(member_name).suffix.lower()
        if suffix in OPTICAL_SUFFIXES:
            raise ValueError(
                f'scene "{scene.external_scene_id}" member "{member_name}" is optical imagery; '
                'a Sentinel-1 SAR archive must provide VV/VH raster bands',
            )
        if suffix not in SAR_STACK_SUFFIXES:
            raise ValueError(
                f'scene "{scene.external_scene_id}" member "{member_name}" uses unsupported suffix "{suffix}"; '
                'expected .npz, .npy, .tif, or .tiff',
            )

    vv = _single_band_array(
        _load_array_from_member_payload(archive.read(scene.vv_member), Path(scene.vv_member).suffix.lower()),
        scene=scene,
        member_name=scene.vv_member,
    )
    vh = _single_band_array(
        _load_array_from_member_payload(archive.read(scene.vh_member), Path(scene.vh_member).suffix.lower()),
        scene=scene,
        member_name=scene.vh_member,
    )
    _normalize_stack(np.stack([vv, vh], axis=0))


def _inspect_archive(
    archive: zipfile.ZipFile,
    *,
    registry_member: str | None = None,
    default_split: str | None = None,
) -> tuple[list[ArchivedScene], list[str], str]:
    scenes = _ensure_validation_or_test_scenes(
        _load_archive_scenes(archive, registry_member=registry_member, default_split=default_split),
    )
    for scene in scenes:
        _validate_scene_is_sar_compatible(archive, scene)
    splits = sorted({scene.split for scene in scenes if scene.split})
    return scenes, splits, _derived_split_name(splits, fallback=default_split)


def _canonical_stack_payload(archive: zipfile.ZipFile, scene: ArchivedScene) -> bytes:
    if scene.stack_member:
        payload = archive.read(scene.stack_member)
        stack = _load_array_from_member_payload(payload, Path(scene.stack_member).suffix.lower())
    else:
        if not scene.vv_member or not scene.vh_member:
            raise ValueError(f'scene "{scene.external_scene_id}" is missing stack or vv/vh members')
        vv = _single_band_array(
            _load_array_from_member_payload(archive.read(scene.vv_member), Path(scene.vv_member).suffix.lower()),
            scene=scene,
            member_name=scene.vv_member,
        )
        vh = _single_band_array(
            _load_array_from_member_payload(archive.read(scene.vh_member), Path(scene.vh_member).suffix.lower()),
            scene=scene,
            member_name=scene.vh_member,
        )
        stack = np.stack([vv, vh], axis=0)
    normalized = _normalize_stack(stack)
    buffer = io.BytesIO()
    np.savez_compressed(buffer, stack=normalized.astype(np.float32))
    return buffer.getvalue()


def _truth_payload(archive: zipfile.ZipFile, scene: ArchivedScene) -> bytes:
    suffix = Path(scene.truth_member).suffix.lower()
    if suffix not in TRUTH_SUFFIXES:
        raise ValueError(
            f'scene "{scene.external_scene_id}" truth member must be GeoTIFF (.tif/.tiff); '
            f'received "{scene.truth_member}"',
        )
    return archive.read(scene.truth_member)


def _ensure_validation_or_test_scenes(scenes: list[ArchivedScene]) -> list[ArchivedScene]:
    normalized = [scene for scene in scenes if scene.split in {'validation', 'test'}]
    if not normalized:
        raise ValueError('archive does not contain validation/test scenes')
    return normalized


def _upload_scene_assets(
    archive: zipfile.ZipFile,
    scenes: list[ArchivedScene],
    *,
    dataset_version: str,
    bucket: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    registry_rows: list[dict[str, Any]] = []
    for scene in scenes:
        truth_asset_ref = build_release_asset_ref(
            dataset_version=dataset_version,
            split=scene.split,
            region_key=scene.region_key,
            scene_id=scene.external_scene_id,
            filename='truth_mask.tif',
            bucket=bucket,
            prefix=SAR_RELEASE_PREFIX,
        )
        stack_asset_ref = build_release_asset_ref(
            dataset_version=dataset_version,
            split=scene.split,
            region_key=scene.region_key,
            scene_id=scene.external_scene_id,
            filename='stack.npz',
            bucket=bucket,
            prefix=SAR_RELEASE_PREFIX,
        )
        _, truth_object_path = truth_asset_ref.split('/', 1)
        _, stack_object_path = stack_asset_ref.split('/', 1)
        storage_upload_bytes(
            bucket=bucket,
            object_path=truth_object_path,
            payload=_truth_payload(archive, scene),
            content_type='image/tiff',
        )
        storage_upload_bytes(
            bucket=bucket,
            object_path=stack_object_path,
            payload=_canonical_stack_payload(archive, scene),
            content_type='application/octet-stream',
        )
        metadata = {
            'split': scene.split,
            'archive_truth_member': scene.truth_member,
            'archive_stack_member': scene.stack_member,
            'archive_vv_member': scene.vv_member,
            'archive_vh_member': scene.vh_member,
            **(scene.metadata or {}),
        }
        row = {
            'external_scene_id': scene.external_scene_id,
            'region_key': scene.region_key,
            'scene_time': scene.scene_time,
            'bbox': scene.bbox or [],
            'stack_asset_ref': stack_asset_ref,
            'truth_mask_asset_ref': truth_asset_ref,
            'baseline_mask_asset_ref': None,
            'metadata': metadata,
        }
        items.append(row)
        registry_rows.append({
            'external_scene_id': scene.external_scene_id,
            'split': scene.split,
            'region_key': scene.region_key,
            'scene_time': scene.scene_time,
            'bbox': scene.bbox or [],
            'stack_asset_ref': stack_asset_ref,
            'truth_mask_asset_ref': truth_asset_ref,
        })
    return items, registry_rows


def seed_snowslide_truth(args: argparse.Namespace) -> dict[str, Any]:
    with _open_archive_from_args(args) as archive:
        scenes, splits, split_name = _inspect_archive(
            archive,
            registry_member=args.registry_member,
            default_split=getattr(args, 'split', None),
        )
        items, registry_rows = _upload_scene_assets(
            archive,
            scenes,
            dataset_version=args.source_version,
            bucket=args.bucket,
        )

    set_rows = rest_upsert('sar_release_reference_sets', [{
        'set_key': args.set_key,
        'source_name': SAR_RELEASE_SOURCE_NAME,
        'source_version': args.source_version,
        'split_name': split_name,
        'hazard_type': args.hazard_type,
        'purpose': SAR_RELEASE_PURPOSE,
        'authoritative': True,
        'status': 'draft',
        'notes': args.notes,
    }], on_conflict='set_key')
    if not set_rows:
        raise RuntimeError('failed to create or update sar_release_reference_sets row')
    reference_set = set_rows[0]
    reference_set_id = str(reference_set['id'])

    upsert_rows = [
        {
            **item,
            'reference_set_id': reference_set_id,
        }
        for item in items
    ]
    rest_upsert(
        'sar_release_reference_items',
        upsert_rows,
        on_conflict='reference_set_id,external_scene_id',
    )

    registry_payload = {
        'set_key': args.set_key,
        'source_name': SAR_RELEASE_SOURCE_NAME,
        'source_version': args.source_version,
        'hazard_type': args.hazard_type,
        'scene_count': len(upsert_rows),
        'generated_from': args.source_url or str(args.source_zip),
        'scenes': registry_rows,
    }
    registry_asset_ref = storage_upsert_json(
        bucket=args.bucket,
        object_path=f'{SAR_RELEASE_PREFIX}/{args.source_version}/reference_sets/{args.set_key}/registry.json',
        payload=registry_payload,
    )
    updated_rows = rest_upsert('sar_release_reference_sets', [{
        'id': reference_set_id,
        'set_key': args.set_key,
        'source_version': args.source_version,
        'split_name': split_name,
        'registry_asset_ref': registry_asset_ref,
        'status': 'draft',
        'authoritative': True,
        'notes': args.notes,
    }], on_conflict='id')

    return {
        'status': 'ok',
        'set_key': args.set_key,
        'reference_set_id': reference_set_id,
        'scene_count': len(upsert_rows),
        'splits': splits,
        'registry_asset_ref': registry_asset_ref,
        'reference_set_status': str((updated_rows[0] if updated_rows else reference_set).get('status') or 'draft'),
    }


def validate_snowslide_archive(args: argparse.Namespace) -> dict[str, Any]:
    with _open_archive_from_args(args) as archive:
        scenes, splits, split_name = _inspect_archive(
            archive,
            registry_member=args.registry_member,
            default_split=getattr(args, 'split', None),
        )
    return {
        'status': 'ok',
        'set_key': args.set_key,
        'scene_count': len(scenes),
        'splits': splits,
        'split_name': split_name,
        'source_version': args.source_version,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Seed authoritative SnowSlide held-out truth into sar-masks + Supabase registry')
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--source-url', help='Operator-provided SnowSlide archive URL')
    source_group.add_argument('--source-zip', type=Path, help='Local SnowSlide archive zip path')
    parser.add_argument('--registry-member', help='Optional JSON/CSV member inside the archive describing scenes')
    parser.add_argument('--header', action='append', default=[], help='Optional HTTP header for --source-url, e.g. "Authorization: Bearer ..."')
    parser.add_argument('--timeout', type=int, default=300, help='Download timeout in seconds for --source-url')
    parser.add_argument('--set-key', required=True, help='Reference-set key to create/update')
    parser.add_argument('--source-version', required=True, help='External dataset version identifier')
    parser.add_argument('--bucket', default=SAR_RELEASE_BUCKET, help='Supabase storage bucket for held-out assets')
    parser.add_argument('--hazard-type', default='avalanche', help='Hazard type for the reference set')
    parser.add_argument('--split', default='validation', help='Deprecated fallback split when the archive does not contain validation/test split metadata')
    parser.add_argument('--notes', default='SnowSlide held-out truth seed', help='Optional registry notes')
    parser.add_argument('--validate-only', action='store_true', help='Inspect the archive and enforce the SAR-only contract without mutating storage or Supabase')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate_snowslide_archive(args) if args.validate_only else seed_snowslide_truth(args)
    except (ValueError, RuntimeError) as exc:
        if args.validate_only:
            print(json.dumps({
                'status': 'invalid_archive',
                'reason': str(exc),
            }, indent=2, sort_keys=True))
            return 1
        raise
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
