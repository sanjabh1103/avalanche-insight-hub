from __future__ import annotations

import json
import io
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlparse

import numpy as np


AVALCD_SCENE_MANIFEST_FORMAT = 'avalcd_scene_manifest_v1'
AVALCD_SCENE_MANIFEST_FILENAME = 'stack_manifest.json'
AVALCD_PATCH_DIRECTORY = 'patches'
AVALCD_PATCH_SIZE = 128
AVALCD_PATCH_STRIDE = 64
AVALCD_BLEND_MODE = 'gaussian'
AVALCD_PADDING_MODE = 'reflect'
AVALCD_BASELINE_CHANNELS = 'post_vv_post_vh'
AVALCD_CHANNELS = ['pre_vv', 'pre_vh', 'post_vv', 'post_vh']


def avalcd_gaussian_sigma(*, patch_size: int = AVALCD_PATCH_SIZE) -> float:
    return float(patch_size) / 6.0


def is_avalcd_manifest_name(value: str | Path | PurePosixPath) -> bool:
    return PurePosixPath(str(value)).name == AVALCD_SCENE_MANIFEST_FILENAME


def _normalize_patch_origins(length: int, *, patch_size: int, stride: int) -> list[int]:
    if length <= patch_size:
        return [0]
    origins = list(range(0, max(length - patch_size, 0) + 1, stride))
    last_origin = length - patch_size
    if origins[-1] != last_origin:
        origins.append(last_origin)
    return origins


def _padding_mode_for_shape(shape: tuple[int, int], requested_mode: str) -> str:
    if requested_mode != 'reflect':
        return requested_mode
    height, width = shape
    if height < 2 or width < 2:
        return 'edge'
    return 'reflect'


def _normalize_four_channel_stack(stack: Any) -> np.ndarray:
    array = np.asarray(stack, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f'expected a 4-channel AvalCD scene stack, received shape {array.shape}')
    if array.shape[0] != 4 and array.shape[-1] == 4:
        array = np.moveaxis(array, -1, 0)
    if array.shape[0] != 4:
        raise ValueError(f'expected a 4-channel AvalCD scene stack, received shape {array.shape}')
    return np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def build_avalcd_scene_manifest(
    stack: Any,
    *,
    bbox: tuple[float, float, float, float],
    patch_size: int = AVALCD_PATCH_SIZE,
    stride: int = AVALCD_PATCH_STRIDE,
    padding_mode: str = AVALCD_PADDING_MODE,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = _normalize_four_channel_stack(stack)
    _, height, width = normalized.shape
    pad_height = max(0, patch_size - height)
    pad_width = max(0, patch_size - width)
    padded = normalized
    if pad_height or pad_width:
        padded = np.pad(
            normalized,
            ((0, 0), (0, pad_height), (0, pad_width)),
            mode=_padding_mode_for_shape((height, width), padding_mode),
        )

    patch_entries: list[dict[str, Any]] = []
    manifest_patches: list[dict[str, Any]] = []
    row_origins = _normalize_patch_origins(height, patch_size=patch_size, stride=stride)
    col_origins = _normalize_patch_origins(width, patch_size=patch_size, stride=stride)
    for row in row_origins:
        for col in col_origins:
            valid_height = min(patch_size, height - row)
            valid_width = min(patch_size, width - col)
            filename = f'{AVALCD_PATCH_DIRECTORY}/r{row:06d}_c{col:06d}.npz'
            patch_stack = padded[:, row:row + patch_size, col:col + patch_size]
            patch_entries.append({
                'filename': filename,
                'row': int(row),
                'col': int(col),
                'valid_window': [0, 0, int(valid_height), int(valid_width)],
                'stack': patch_stack.astype(np.float32),
            })
            manifest_patches.append({
                'asset_ref': filename,
                'row': int(row),
                'col': int(col),
                'valid_window': [0, 0, int(valid_height), int(valid_width)],
            })

    manifest = {
        'format': AVALCD_SCENE_MANIFEST_FORMAT,
        'layout': 'bitemporal_patches',
        'channels': list(AVALCD_CHANNELS),
        'full_shape': [int(height), int(width)],
        'bbox': [float(value) for value in bbox],
        'patch_size': int(patch_size),
        'stride': int(stride),
        'blend_mode': AVALCD_BLEND_MODE,
        'gaussian_sigma': avalcd_gaussian_sigma(patch_size=patch_size),
        'padding_mode': padding_mode,
        'baseline_channels': AVALCD_BASELINE_CHANNELS,
        'patches': manifest_patches,
    }
    return manifest, patch_entries


def encode_patch_payload(stack: Any) -> bytes:
    payload = np.asarray(stack, dtype=np.float32)
    handle = io.BytesIO()
    np.savez_compressed(handle, stack=payload)
    return handle.getvalue()


def load_avalcd_scene_manifest(payload: bytes | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        parsed = payload
    elif isinstance(payload, bytes):
        parsed = json.loads(payload.decode('utf-8'))
    else:
        parsed = json.loads(str(payload))
    if not isinstance(parsed, dict):
        raise ValueError('AvalCD scene manifest must be a JSON object')
    if str(parsed.get('format') or '').strip() != AVALCD_SCENE_MANIFEST_FORMAT:
        raise ValueError(f'unsupported AvalCD scene manifest format "{parsed.get("format")}"')
    patches = parsed.get('patches')
    if not isinstance(patches, list) or not patches:
        raise ValueError('AvalCD scene manifest must include a non-empty patches[] list')
    full_shape = parsed.get('full_shape')
    if not isinstance(full_shape, list) or len(full_shape) != 2:
        raise ValueError('AvalCD scene manifest must include full_shape=[height,width]')
    bbox = parsed.get('bbox')
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError('AvalCD scene manifest must include bbox=[west,south,east,north]')
    normalized = dict(parsed)
    normalized['full_shape'] = [int(full_shape[0]), int(full_shape[1])]
    normalized['bbox'] = [float(value) for value in bbox]
    normalized['patch_size'] = int(parsed.get('patch_size') or AVALCD_PATCH_SIZE)
    normalized['stride'] = int(parsed.get('stride') or AVALCD_PATCH_STRIDE)
    normalized['gaussian_sigma'] = float(parsed.get('gaussian_sigma') or avalcd_gaussian_sigma(patch_size=normalized['patch_size']))
    normalized['patches'] = []
    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError('AvalCD scene manifest patches[] entries must be objects')
        asset_ref = str(patch.get('asset_ref') or '').strip()
        if not asset_ref:
            raise ValueError('AvalCD scene manifest patch is missing asset_ref')
        valid_window = patch.get('valid_window')
        if not isinstance(valid_window, list) or len(valid_window) != 4:
            raise ValueError('AvalCD scene manifest patch is missing valid_window=[row0,col0,row1,col1]')
        normalized['patches'].append({
            'asset_ref': asset_ref,
            'row': int(patch.get('row') or 0),
            'col': int(patch.get('col') or 0),
            'valid_window': [int(value) for value in valid_window],
        })
    return normalized


def resolve_manifest_relative_ref(manifest_ref: str, patch_ref: str) -> str:
    trimmed = str(patch_ref or '').strip()
    if not trimmed:
        raise ValueError('AvalCD scene manifest patch is missing asset_ref')
    parsed_patch = urlparse(trimmed)
    if parsed_patch.scheme in {'http', 'https'} or trimmed.startswith(('/', './', '../', '~')):
        return trimmed
    bucket, sep, object_path = trimmed.partition('/')
    if sep and bucket and object_path and not trimmed.startswith(AVALCD_PATCH_DIRECTORY + '/'):
        return trimmed

    base = str(manifest_ref).strip()
    parsed_base = urlparse(base)
    if parsed_base.scheme in {'http', 'https'}:
        base_dir = parsed_base._replace(path=str(PurePosixPath(parsed_base.path).parent) + '/').geturl()
        return urljoin(base_dir, trimmed)
    if '/' in base and not base.startswith(('/', './', '../', '~')):
        bucket, _, object_path = base.partition('/')
        base_dir = PurePosixPath(object_path).parent
        return f'{bucket}/{base_dir.joinpath(trimmed).as_posix()}'
    return str(Path(base).parent.joinpath(trimmed))
