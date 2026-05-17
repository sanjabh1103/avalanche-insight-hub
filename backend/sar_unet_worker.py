from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import requests

from backend.common.artifacts import create_artifact_dir, dump_json, is_artifact_run_dir, latest_artifact_dir, load_joblib, load_json, resolve_artifact_dir
from backend.common.avalcd_manifest import (
    AVALCD_SCENE_MANIFEST_FORMAT,
    avalcd_gaussian_sigma,
    is_avalcd_manifest_name,
    load_avalcd_scene_manifest,
    resolve_manifest_relative_ref,
)
from backend.common.config import load_settings
from backend.common.label_governance import materialize_label_governance
from backend.common.run_linkage import merge_compute_job_result_linkage, merge_compute_job_terminal_result
from backend.common.sar_release_refs import load_reference_bundle, parse_storage_ref, reference_item_to_scene
from backend.common.sar_artifacts import persist_sar_artifacts
from backend.common.storage_io import storage_download_bytes, storage_upload_bytes
from backend.common.supabase_io import has_supabase_credentials, rest_insert, rest_upsert
from backend.sar_unet_training import _postprocess_binary_mask, train_sar_unet

try:  # pragma: no cover - optional dependency
    import torch
except Exception:  # pragma: no cover - optional dependency
    torch = None

try:  # pragma: no cover - optional dependency
    import segmentation_models_pytorch as smp
except Exception:  # pragma: no cover - optional dependency
    smp = None

try:  # pragma: no cover - optional dependency
    from rasterio.features import shapes as raster_shapes
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds
except Exception:  # pragma: no cover - optional dependency
    raster_shapes = None
    MemoryFile = None
    from_bounds = None


SAR_MASK_BUCKET = os.environ.get('SAR_MASK_BUCKET', 'sar-masks')
SAR_UNET_MODEL_FAMILY = str(os.environ.get('SAR_UNET_MODEL_FAMILY') or 'resnet34_unet').strip() or 'resnet34_unet'
SAR_UNET_MODEL_VERSION = os.environ.get('SAR_UNET_MODEL_VERSION', 'sar_unet_resnet34_shadow_v1')
SAR_UNET_SEGMENTATION_THRESHOLD = float(os.environ.get('SAR_UNET_SEGMENTATION_THRESHOLD', '0.5'))
SAR_UNET_PROMOTED = os.environ.get('SAR_UNET_PROMOTED', '').strip().lower() in {'1', 'true', 'yes', 'on'}
SAR_UNET_SHADOW_REASON = 'sar_unet_shadow_mode'
DEFAULT_LSTM_EPOCHS = int(os.environ.get('MTS_LSTM_EPOCHS', '50'))
DEFAULT_LSTM_MIN_EPOCHS = int(os.environ.get('MTS_LSTM_MIN_EPOCHS_BEFORE_EARLY_STOPPING', '10'))
DEFAULT_LSTM_PATIENCE = int(os.environ.get('MTS_LSTM_EARLY_STOPPING_PATIENCE', '7'))


@dataclass(frozen=True)
class SegmentationDetection:
    scene_id: str
    region_key: str
    scene_time: str
    bbox: tuple[float, float, float, float]
    probability: float
    centroid: dict[str, float]
    geometry: dict[str, Any]
    mask_asset_ref: str | None
    model_version: str
    source_scene_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            'scene_id': self.scene_id,
            'region_key': self.region_key,
            'scene_time': self.scene_time,
            'bbox': list(self.bbox),
            'confidence': self.probability,
            'centroid': self.centroid,
            'geometry': self.geometry,
            'mask_asset_ref': self.mask_asset_ref,
            'model_version': self.model_version,
            'source_scene_ids': self.source_scene_ids,
        }


@dataclass(frozen=True)
class LoadedUnetModel:
    model: Any
    checkpoint_key_mismatch: dict[str, Any]
    model_family: str
    normalization: dict[str, np.ndarray] | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flag_from_payload(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _coerce_bbox(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError('scene bbox must be a 4-item list: [west, south, east, north]')
    west, south, east, north = [float(item) for item in value]
    if east <= west or north <= south:
        raise ValueError(f'invalid scene bbox: {value}')
    return west, south, east, north


def _scene_id(scene: dict[str, Any]) -> str:
    return str(
        scene.get('scene_id')
        or scene.get('sceneName')
        or scene.get('fileID')
        or scene.get('id')
        or 'unknown-scene'
    )


def _scene_time(scene: dict[str, Any]) -> str:
    for key in ('scene_time', 'timestamp', 'sensing_time', 'event_time'):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _utc_now_iso()


def _scene_region_key(scene: dict[str, Any]) -> str:
    return str(scene.get('region_key') or scene.get('region') or 'unknown')


def _scene_ids(scene: dict[str, Any]) -> list[str]:
    raw = scene.get('source_scene_ids') or scene.get('scene_ids')
    if isinstance(raw, list) and raw:
        return [str(item) for item in raw if item]
    return [_scene_id(scene)]


def _normalize_stack(stack: Any) -> np.ndarray:
    array = np.asarray(stack, dtype=np.float32)
    if array.ndim == 2:
        raise ValueError(
            f'Expected 2-channel VV+VH stack but received a single 2D array of shape {array.shape}. '
            'Pass channels as stack of shape (2, H, W) or (H, W, 2), or use vv/vh keys.',
        )
    if array.ndim != 3:
        raise ValueError(f'expected a 2-channel stack, received shape {array.shape}')
    if array.shape[0] != 2 and array.shape[-1] == 2:
        array = np.moveaxis(array, -1, 0)
    if array.shape[0] != 2:
        raise ValueError(f'expected a 2-channel stack, received shape {array.shape}')
    return np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def _normalize_release_stack(stack: Any) -> np.ndarray:
    array = np.asarray(stack, dtype=np.float32)
    if array.ndim == 2:
        raise ValueError(f'expected a 2-channel or 4-channel stack, received shape {array.shape}')
    if array.ndim != 3:
        raise ValueError(f'expected a 2-channel or 4-channel stack, received shape {array.shape}')
    if array.shape[0] not in {2, 4} and array.shape[-1] in {2, 4}:
        array = np.moveaxis(array, -1, 0)
    if array.shape[0] not in {2, 4}:
        raise ValueError(f'expected a 2-channel or 4-channel stack, received shape {array.shape}')
    return np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def _load_json_from_bytes(payload: bytes) -> dict[str, Any]:
    parsed = json.loads(payload.decode('utf-8'))
    if not isinstance(parsed, dict):
        raise ValueError('JSON scene payload must decode to an object')
    return parsed


def _load_json_from_string_ref(value: str) -> dict[str, Any]:
    suffix = _ref_suffix(value)
    if suffix != '.json':
        raise ValueError(f'unsupported JSON scene reference "{value}"')
    if _looks_like_http_url(value):
        response = requests.get(value, timeout=120)
        response.raise_for_status()
        return _load_json_from_bytes(response.content)
    if _looks_like_storage_ref(value):
        bucket, _, object_path = value.partition('/')
        return _load_json_from_bytes(storage_download_bytes(bucket=bucket, object_path=object_path))
    path = Path(value)
    if path.exists():
        return _load_json_from_bytes(path.read_bytes())
    raise FileNotFoundError(
        f'JSON scene ref not found or unreadable: {value}. '
        'Expected an absolute/relative local path, http(s) URL, or Supabase storage ref bucket/path.',
    )


def _scene_manifest_ref(scene: dict[str, Any]) -> str | None:
    for key in ('stack_ref', 'stack_path', 'stack_url'):
        value = scene.get(key)
        if isinstance(value, str) and value.strip() and is_avalcd_manifest_name(value.strip()):
            return value.strip()
    return None


def _load_avalcd_manifest_from_string_ref(value: str) -> dict[str, Any]:
    manifest = load_avalcd_scene_manifest(_load_json_from_string_ref(value))
    if manifest.get('format') != AVALCD_SCENE_MANIFEST_FORMAT:
        raise ValueError(f'unsupported AvalCD scene manifest format "{manifest.get("format")}"')
    return manifest


def _resolve_manifest_patch_ref(manifest_ref: str, patch_ref: str) -> str:
    return resolve_manifest_relative_ref(manifest_ref, patch_ref)


def _reconstruct_avalcd_stack_from_manifest(
    manifest_ref: str,
    *,
    channel_slice: slice | tuple[int, ...] | None = None,
) -> np.ndarray:
    manifest = _load_avalcd_manifest_from_string_ref(manifest_ref)
    height, width = [int(value) for value in manifest['full_shape']]
    channels = 4 if channel_slice is None else len(range(*channel_slice.indices(4))) if isinstance(channel_slice, slice) else len(channel_slice)
    accum = np.zeros((channels, height, width), dtype=np.float32)
    counts = np.zeros((height, width), dtype=np.float32)

    def _load_manifest_patch(patch: dict[str, Any]) -> tuple[dict[str, Any], np.ndarray, str]:
        patch_ref = _resolve_manifest_patch_ref(manifest_ref, str(patch['asset_ref']))
        patch_stack = _normalize_release_stack(_load_stack_array_from_string_ref(patch_ref))
        if patch_stack.shape[0] != 4:
            raise ValueError(
                f'manifest patch "{patch_ref}" must contain a 4-channel AvalCD stack, received {patch_stack.shape}',
            )
        selected = patch_stack[channel_slice] if channel_slice is not None else patch_stack
        return patch, selected, patch_ref

    max_workers = max(1, int(os.environ.get('SAR_UNET_PATCH_DOWNLOAD_WORKERS', '16')))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        patch_iter = executor.map(_load_manifest_patch, manifest['patches'])
        for patch, selected, patch_ref in patch_iter:
            row = int(patch['row'])
            col = int(patch['col'])
            row0, col0, row1, col1 = [int(value) for value in patch['valid_window']]
            if row0 < 0 or col0 < 0 or row1 <= row0 or col1 <= col0:
                raise ValueError(f'manifest patch "{patch_ref}" has invalid valid_window {patch["valid_window"]}')
            dest_row1 = row + row1
            dest_col1 = col + col1
            if dest_row1 > height or dest_col1 > width:
                raise ValueError(f'manifest patch "{patch_ref}" extends beyond full_shape {manifest["full_shape"]}')
            accum[:, row + row0:dest_row1, col + col0:dest_col1] += selected[:, row0:row1, col0:col1]
            counts[row + row0:dest_row1, col + col0:dest_col1] += 1.0
    if not np.all(counts > 0):
        raise ValueError(f'AvalCD manifest "{manifest_ref}" does not fully cover its declared full_shape')
    return accum / counts[np.newaxis, ...]


def load_scene_stack(scene: dict[str, Any]) -> np.ndarray:
    if scene.get('channels') is not None:
        return _normalize_stack(scene['channels'])
    if scene.get('vv') is not None and scene.get('vh') is not None:
        return _normalize_stack(np.stack([scene['vv'], scene['vh']], axis=0))

    manifest_ref = _scene_manifest_ref(scene)
    if manifest_ref:
        return _normalize_stack(_reconstruct_avalcd_stack_from_manifest(manifest_ref, channel_slice=slice(2, 4)))

    stack_ref = scene.get('stack_ref')
    if isinstance(stack_ref, str) and stack_ref.strip():
        return _normalize_stack(_load_stack_array_from_string_ref(stack_ref.strip()))

    stack_path = scene.get('stack_path')
    if isinstance(stack_path, str) and stack_path.strip():
        return _normalize_stack(_load_stack_array_from_string_ref(stack_path.strip()))

    stack_url = scene.get('stack_url')
    if isinstance(stack_url, str) and stack_url.strip():
        return _normalize_stack(_load_stack_array_from_string_ref(stack_url.strip()))

    raise ValueError(
        f"scene {_scene_id(scene)} is missing SAR patch data; provide channels, vv/vh, stack_ref, stack_path, or stack_url",
    )


def _normalize_bitemporal_stack(stack: Any) -> tuple[np.ndarray, np.ndarray]:
    array = np.asarray(stack, dtype=np.float32)
    if array.ndim == 2:
        raise ValueError(
            f'Expected a 4-channel bi-temporal stack but received a single 2D array of shape {array.shape}. '
            'Provide pre/post channels separately or pass a stack of shape (4, H, W) or (H, W, 4).',
        )
    if array.ndim != 3:
        raise ValueError(f'expected a 4-channel bi-temporal stack, received shape {array.shape}')
    if array.shape[0] != 4 and array.shape[-1] == 4 and array.shape[0] not in {2, 4}:
        array = np.moveaxis(array, -1, 0)
    if array.shape[0] != 4:
        raise ValueError(
            f'expected a 4-channel bi-temporal stack, received shape {array.shape}; '
            'the Swin shadow path requires [pre_vv, pre_vh, post_vv, post_vh]',
        )
    array = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    return array[:2], array[2:]


def load_bitemporal_scene_inputs(scene: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    if scene.get('pre_channels') is not None and scene.get('post_channels') is not None:
        return _normalize_stack(scene['pre_channels']), _normalize_stack(scene['post_channels'])
    if all(scene.get(key) is not None for key in ('pre_vv', 'pre_vh', 'post_vv', 'post_vh')):
        return (
            _normalize_stack(np.stack([scene['pre_vv'], scene['pre_vh']], axis=0)),
            _normalize_stack(np.stack([scene['post_vv'], scene['post_vh']], axis=0)),
        )

    for pre_key, post_key in (
        ('pre_stack_ref', 'post_stack_ref'),
        ('pre_stack_path', 'post_stack_path'),
        ('pre_stack_url', 'post_stack_url'),
    ):
        pre_value = scene.get(pre_key)
        post_value = scene.get(post_key)
        if isinstance(pre_value, str) and pre_value.strip() and isinstance(post_value, str) and post_value.strip():
            return (
                _normalize_stack(_load_stack_array_from_string_ref(pre_value.strip())),
                _normalize_stack(_load_stack_array_from_string_ref(post_value.strip())),
            )

    four_channel_candidates = (
        scene.get('temporal_channels'),
        scene.get('channels'),
    )
    for candidate in four_channel_candidates:
        if candidate is not None:
            return _normalize_bitemporal_stack(candidate)
    manifest_ref = _scene_manifest_ref(scene)
    if manifest_ref:
        stack = _reconstruct_avalcd_stack_from_manifest(manifest_ref)
        return _normalize_bitemporal_stack(stack)
    for key in ('stack_ref', 'stack_path', 'stack_url'):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_bitemporal_stack(_load_stack_array_from_string_ref(value.strip()))

    raise ValueError(
        f"scene {_scene_id(scene)} is missing bi-temporal SAR patch data; "
        'swinunet_tiny_diff requires pre/post stacks or a 4-channel temporal stack',
    )


def _checkpoint_key_mismatch_summary(load_result: Any) -> dict[str, Any]:
    missing_keys = [str(item) for item in (getattr(load_result, 'missing_keys', None) or [])]
    unexpected_keys = [str(item) for item in (getattr(load_result, 'unexpected_keys', None) or [])]
    return {
        'missing_keys': missing_keys,
        'unexpected_keys': unexpected_keys,
        'missing_count': len(missing_keys),
        'unexpected_count': len(unexpected_keys),
        'has_mismatch': bool(missing_keys or unexpected_keys),
    }


def _normalize_model_family(model_family: str | None) -> str:
    resolved = str(model_family or SAR_UNET_MODEL_FAMILY).strip() or 'resnet34_unet'
    if resolved not in {'resnet34_unet', 'swinunet_tiny_diff'}:
        raise ValueError(
            f'unsupported SAR_UNET_MODEL_FAMILY "{resolved}"; '
            'expected one of: resnet34_unet, swinunet_tiny_diff',
        )
    return resolved


def _extract_state_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ('state_dict', 'model_state_dict', 'model'):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        return payload
    raise RuntimeError('checkpoint payload must be a dict or contain a nested state_dict')


def _checkpoint_normalization(payload: Any) -> dict[str, np.ndarray] | None:
    if not isinstance(payload, dict):
        return None
    metadata = payload.get('metadata')
    if not isinstance(metadata, dict):
        return None
    normalization = metadata.get('normalization')
    if not isinstance(normalization, dict):
        return None
    mean = normalization.get('img_mean')
    std = normalization.get('img_std')
    if mean is None or std is None:
        return None
    mean_array = np.asarray(mean, dtype=np.float32)
    std_array = np.maximum(np.asarray(std, dtype=np.float32), np.float32(1e-6))
    if mean_array.shape != (2,) or std_array.shape != (2,):
        raise ValueError(
            'SAR checkpoint normalization must contain img_mean/img_std arrays with exactly two channels',
        )
    return {'img_mean': mean_array, 'img_std': std_array}


def _apply_loaded_normalization(
    pre_stack: np.ndarray,
    post_stack: np.ndarray,
    normalization: dict[str, np.ndarray] | None,
) -> tuple[np.ndarray, np.ndarray]:
    if normalization is None:
        return pre_stack, post_stack
    mean = np.asarray(normalization['img_mean'], dtype=np.float32)
    std = np.maximum(np.asarray(normalization['img_std'], dtype=np.float32), np.float32(1e-6))
    if pre_stack.ndim == 4:
        shape = (1, mean.shape[0], 1, 1)
    elif pre_stack.ndim == 3:
        shape = (mean.shape[0], 1, 1)
    else:
        raise ValueError(f'expected SAR pre_stack with 3 or 4 dimensions, received {pre_stack.shape}')
    mean = mean.reshape(shape)
    std = std.reshape(shape)
    return (
        (np.asarray(pre_stack, dtype=np.float32) - mean) / std,
        (np.asarray(post_stack, dtype=np.float32) - mean) / std,
    )


def _build_resnet34_unet_model() -> Any:
    if smp is None:
        raise RuntimeError('segmentation_models_pytorch is required for SAR model family resnet34_unet')
    return smp.Unet(
        encoder_name='resnet34',
        encoder_weights=None,
        in_channels=2,
        classes=1,
        activation=None,
    )


def _build_swinunet_tiny_diff_model(*, image_size: int) -> Any:
    from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet, require_swin_runtime

    require_swin_runtime()
    return ChangeDetectionSwinUNet(
        img_size=image_size,
        sar_in_channels=2,
        aux_in_channels=4,
        num_classes=1,
        use_aux=False,
        model_size='tiny',
        fusion_type='diff',
    )


def _obvious_checkpoint_family_mismatch(
    *,
    model_family: str,
    state_dict: dict[str, Any],
    checkpoint_key_mismatch: dict[str, Any],
) -> str | None:
    state_keys = [str(key) for key in state_dict]
    provided_key_count = len(state_keys)
    unexpected_count = int(checkpoint_key_mismatch.get('unexpected_count') or 0)
    matched_provided_key_count = max(0, provided_key_count - unexpected_count)
    checkpoint_key_mismatch['provided_key_count'] = provided_key_count
    checkpoint_key_mismatch['matched_provided_key_count'] = matched_provided_key_count
    checkpoint_key_mismatch['provided_match_ratio'] = (
        float(matched_provided_key_count) / float(provided_key_count)
        if provided_key_count
        else 1.0
    )
    if provided_key_count < 10:
        return None
    if matched_provided_key_count == 0:
        return (
            f'checkpoint is incompatible with selected SAR_UNET_MODEL_FAMILY={model_family}; '
            'no checkpoint keys matched the target model graph'
        )

    lower_keys = [key.lower() for key in state_keys]
    resnet_hits = sum(
        1
        for key in lower_keys
        if key.startswith('encoder.') or key.startswith('decoder.') or key.startswith('segmentation_head.')
    )
    swin_hits = sum(
        1
        for key in lower_keys
        if key.startswith('sar_encoder.')
        or key.startswith('fusion_stages.')
        or key.startswith('decoder.layers_up.')
        or key.startswith('aux_encoder.')
        or 'swin' in key
    )
    if model_family == 'resnet34_unet' and swin_hits >= 10 and checkpoint_key_mismatch['provided_match_ratio'] < 0.25:
        return 'checkpoint appears to target the Swin bi-temporal family, not resnet34_unet'
    if model_family == 'swinunet_tiny_diff' and resnet_hits >= 10 and checkpoint_key_mismatch['provided_match_ratio'] < 0.25:
        return 'checkpoint appears to target the ResNet34 U-Net family, not swinunet_tiny_diff'
    return None


def build_unet_model(
    model_path: Path,
    *,
    device: str,
    model_family: str | None = None,
    image_size: int | None = None,
    promoted: bool | None = None,
) -> LoadedUnetModel:
    if torch is None:
        raise RuntimeError('torch is required for sar_unet_worker')
    if not model_path.exists():
        raise FileNotFoundError(f'SAR U-Net weights not found: {model_path}')
    resolved_family = _normalize_model_family(model_family)
    promoted_mode = SAR_UNET_PROMOTED if promoted is None else bool(promoted)
    if resolved_family == 'swinunet_tiny_diff':
        if image_size is None:
            raise ValueError('swinunet_tiny_diff requires image_size during model construction')
        model = _build_swinunet_tiny_diff_model(image_size=image_size)
    else:
        model = _build_resnet34_unet_model()
    payload = torch.load(model_path, map_location=device)
    state_dict = _extract_state_dict(payload)
    normalization = _checkpoint_normalization(payload)
    load_result = model.load_state_dict(state_dict, strict=False)
    checkpoint_key_mismatch = _checkpoint_key_mismatch_summary(load_result)
    mismatch_reason = _obvious_checkpoint_family_mismatch(
        model_family=resolved_family,
        state_dict=state_dict,
        checkpoint_key_mismatch=checkpoint_key_mismatch,
    )
    if mismatch_reason:
        raise RuntimeError(mismatch_reason)
    if checkpoint_key_mismatch['has_mismatch']:
        print(
            '[sar_unet_worker] load_state_dict key mismatch: '
            f"{checkpoint_key_mismatch['missing_count']} missing, "
            f"{checkpoint_key_mismatch['unexpected_count']} unexpected",
            file=sys.stderr,
        )
        if promoted_mode:
            raise RuntimeError(
                'Promoted SAR U-Net checkpoints must load cleanly; '
                f"received {checkpoint_key_mismatch['missing_count']} missing and "
                f"{checkpoint_key_mismatch['unexpected_count']} unexpected keys.",
            )
    model.to(device)
    model.eval()
    return LoadedUnetModel(
        model=model,
        checkpoint_key_mismatch=checkpoint_key_mismatch,
        model_family=resolved_family,
        normalization=normalization,
    )


def predict_probability_mask(model: Any, stack: np.ndarray, *, device: str) -> np.ndarray:
    if torch is None:
        raise RuntimeError('torch is required for sar_unet_worker inference')
    tensor = torch.from_numpy(stack[np.newaxis, ...]).float().to(device)
    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.sigmoid(logits).detach().cpu().numpy()
    return np.asarray(probabilities[0, 0], dtype=np.float32)


def predict_bitemporal_probability_mask(model: Any, pre_stack: np.ndarray, post_stack: np.ndarray, *, device: str) -> np.ndarray:
    if torch is None:
        raise RuntimeError('torch is required for sar_unet_worker inference')
    pre_tensor = torch.from_numpy(pre_stack[np.newaxis, ...]).float().to(device)
    post_tensor = torch.from_numpy(post_stack[np.newaxis, ...]).float().to(device)
    with torch.no_grad():
        logits = model(pre_tensor, post_tensor)
        probabilities = torch.sigmoid(logits).detach().cpu().numpy()
    return np.asarray(probabilities[0, 0], dtype=np.float32)


def predict_bitemporal_probability_mask_batch(
    model: Any,
    pre_stacks: np.ndarray,
    post_stacks: np.ndarray,
    *,
    device: str,
) -> np.ndarray:
    if torch is None:
        raise RuntimeError('torch is required for sar_unet_worker inference')
    pre_tensor = torch.from_numpy(pre_stacks).float().to(device)
    post_tensor = torch.from_numpy(post_stacks).float().to(device)
    with torch.no_grad():
        logits = model(pre_tensor, post_tensor)
        probabilities = torch.sigmoid(logits).detach().cpu().numpy()
    return np.asarray(probabilities[:, 0], dtype=np.float32)


def _gaussian_patch_weights(*, patch_size: int, sigma: float) -> np.ndarray:
    axis = np.arange(patch_size, dtype=np.float32) - ((patch_size - 1) / 2.0)
    gaussian = np.exp(-(axis ** 2) / max(2.0 * (sigma ** 2), 1e-6))
    weights = np.outer(gaussian, gaussian).astype(np.float32)
    max_weight = float(np.max(weights))
    if max_weight <= 0.0:
        return np.ones((patch_size, patch_size), dtype=np.float32)
    return weights / max_weight


def _predict_manifest_probability_mask(
    loaded_model: LoadedUnetModel,
    *,
    manifest_ref: str,
    device: str,
) -> np.ndarray:
    manifest = _load_avalcd_manifest_from_string_ref(manifest_ref)
    height, width = [int(value) for value in manifest['full_shape']]
    patch_size = int(manifest.get('patch_size') or 128)
    sigma = float(manifest.get('gaussian_sigma') or avalcd_gaussian_sigma(patch_size=patch_size))
    numerator = np.zeros((height, width), dtype=np.float32)
    weights = np.zeros((height, width), dtype=np.float32)
    patch_weights = _gaussian_patch_weights(patch_size=patch_size, sigma=sigma)

    def _load_manifest_patch_stack(patch: dict[str, Any]) -> tuple[dict[str, Any], str, np.ndarray]:
        patch_ref = _resolve_manifest_patch_ref(manifest_ref, str(patch['asset_ref']))
        stack = _normalize_release_stack(_load_stack_array_from_string_ref(patch_ref))
        if stack.shape[0] != 4:
            raise ValueError(
                f'manifest patch "{patch_ref}" must contain a 4-channel AvalCD stack, received {stack.shape}',
            )
        if stack.shape[1] != patch_size or stack.shape[2] != patch_size:
            raise ValueError(
                f'manifest patch "{patch_ref}" must match patch_size={patch_size}, received {stack.shape}',
            )
        return patch, patch_ref, stack

    max_workers = max(1, int(os.environ.get('SAR_UNET_PATCH_DOWNLOAD_WORKERS', '16')))
    batch_size = max(1, int(os.environ.get('SAR_UNET_PATCH_BATCH_SIZE', '64')))
    patches = list(manifest['patches'])
    total_batches = max(1, (len(patches) + batch_size - 1) // batch_size)
    for start in range(0, len(patches), batch_size):
        batch = patches[start:start + batch_size]
        batch_number = (start // batch_size) + 1
        print(
            f'[sar_unet_worker] manifest inference {manifest_ref}: batch {batch_number}/{total_batches} '
            f'({len(batch)} patches, workers={min(max_workers, len(batch))})',
            file=sys.stderr,
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=min(max_workers, len(batch))) as executor:
            loaded_batch = list(executor.map(_load_manifest_patch_stack, batch))
        pre_batch = np.stack([stack[:2] for _, _, stack in loaded_batch], axis=0)
        post_batch = np.stack([stack[2:] for _, _, stack in loaded_batch], axis=0)
        pre_batch, post_batch = _apply_loaded_normalization(pre_batch, post_batch, loaded_model.normalization)
        probability_batch = predict_bitemporal_probability_mask_batch(
            loaded_model.model,
            pre_batch,
            post_batch,
            device=device,
        )
        for (patch, patch_ref, _stack), probability_patch in zip(loaded_batch, probability_batch):
            row = int(patch['row'])
            col = int(patch['col'])
            row0, col0, row1, col1 = [int(value) for value in patch['valid_window']]
            dest_row1 = row + row1
            dest_col1 = col + col1
            cropped_probabilities = probability_patch[row0:row1, col0:col1]
            cropped_weights = patch_weights[row0:row1, col0:col1]
            numerator[row + row0:dest_row1, col + col0:dest_col1] += cropped_probabilities * cropped_weights
            weights[row + row0:dest_row1, col + col0:dest_col1] += cropped_weights
    if not np.all(weights > 0):
        raise ValueError(f'AvalCD manifest "{manifest_ref}" does not fully cover its declared full_shape')
    return numerator / np.maximum(weights, 1e-6)


def predict_scene_probability_mask(loaded_model: LoadedUnetModel, scene: dict[str, Any], *, device: str) -> np.ndarray:
    manifest_ref = _scene_manifest_ref(scene)
    if manifest_ref and loaded_model.model_family == 'swinunet_tiny_diff':
        return _predict_manifest_probability_mask(loaded_model, manifest_ref=manifest_ref, device=device)
    if loaded_model.model_family == 'swinunet_tiny_diff':
        pre_stack, post_stack = load_bitemporal_scene_inputs(scene)
        pre_stack, post_stack = _apply_loaded_normalization(pre_stack, post_stack, loaded_model.normalization)
        return predict_bitemporal_probability_mask(loaded_model.model, pre_stack, post_stack, device=device)
    stack = load_scene_stack(scene)
    return predict_probability_mask(loaded_model.model, stack, device=device)


def _pixel_to_lng(col: float, west: float, east: float, width: int) -> float:
    return west + (col / max(width, 1)) * (east - west)


def _pixel_to_lat(row: float, south: float, north: float, height: int) -> float:
    return north - (row / max(height, 1)) * (north - south)


def _ring_area(ring: list[list[float]]) -> float:
    if len(ring) < 4:
        return 0.0
    area = 0.0
    for idx in range(len(ring) - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / 2.0


def _fallback_polygon(mask: np.ndarray, bbox: tuple[float, float, float, float]) -> dict[str, Any] | None:
    if not np.any(mask):
        return None
    rows, cols = np.where(mask)
    min_row, max_row = int(rows.min()), int(rows.max())
    min_col, max_col = int(cols.min()), int(cols.max())
    west, south, east, north = bbox
    height, width = mask.shape
    left = _pixel_to_lng(min_col, west, east, width)
    right = _pixel_to_lng(max_col + 1, west, east, width)
    top = _pixel_to_lat(min_row, south, north, height)
    bottom = _pixel_to_lat(max_row + 1, south, north, height)
    return {
        'type': 'Polygon',
        'coordinates': [[
            [left, bottom],
            [left, top],
            [right, top],
            [right, bottom],
            [left, bottom],
        ]],
    }


def polygonize_probability_mask(
    probability_mask: np.ndarray,
    *,
    bbox: tuple[float, float, float, float],
    threshold: float = SAR_UNET_SEGMENTATION_THRESHOLD,
) -> dict[str, Any] | None:
    mask = np.asarray(probability_mask >= threshold, dtype=np.uint8)
    if not np.any(mask):
        return None
    if raster_shapes is None or from_bounds is None:
        return _fallback_polygon(mask.astype(bool), bbox)

    west, south, east, north = bbox
    height, width = mask.shape
    transform = from_bounds(west, south, east, north, width, height)
    best_geometry: dict[str, Any] | None = None
    best_area = 0.0
    for geometry, value in raster_shapes(mask, mask=mask.astype(bool), transform=transform):
        if not value or geometry.get('type') != 'Polygon':
            continue
        coordinates = geometry.get('coordinates') or []
        if not coordinates or not isinstance(coordinates[0], list):
            continue
        area = _ring_area(coordinates[0])
        if area > best_area:
            best_area = area
            best_geometry = geometry
    return best_geometry or _fallback_polygon(mask.astype(bool), bbox)


def mask_centroid(
    probability_mask: np.ndarray,
    *,
    bbox: tuple[float, float, float, float],
    threshold: float = SAR_UNET_SEGMENTATION_THRESHOLD,
) -> dict[str, float]:
    mask = probability_mask >= threshold
    west, south, east, north = bbox
    height, width = probability_mask.shape
    if not np.any(mask):
        return {'lat': (south + north) / 2.0, 'lng': (west + east) / 2.0}
    rows, cols = np.where(mask)
    row_center = float(rows.mean() + 0.5)
    col_center = float(cols.mean() + 0.5)
    return {
        'lat': _pixel_to_lat(row_center, south, north, height),
        'lng': _pixel_to_lng(col_center, west, east, width),
    }


def encode_mask_geotiff(probability_mask: np.ndarray, *, bbox: tuple[float, float, float, float]) -> bytes:
    if MemoryFile is None or from_bounds is None:
        raise RuntimeError('rasterio is required to encode GeoTIFF mask artifacts')
    height, width = probability_mask.shape
    west, south, east, north = bbox
    transform = from_bounds(west, south, east, north, width, height)
    band = np.clip(probability_mask * 255.0, 0, 255).astype(np.uint8)
    with MemoryFile() as memory_file:
        with memory_file.open(
            driver='GTiff',
            width=width,
            height=height,
            count=1,
            dtype='uint8',
            crs='EPSG:4326',
            transform=transform,
            compress='deflate',
        ) as dataset:
            dataset.write(band, 1)
        return memory_file.read()


def build_mask_object_path(
    *,
    region_key: str,
    scene_id: str,
    scene_time: str,
    model_version: str,
) -> str:
    time_slug = scene_time.replace(':', '').replace('+', '_')
    return f'{scene_time[:10]}/{region_key}/{scene_id}-{model_version}-{time_slug}.tif'


def build_shadow_event_record(
    detection: SegmentationDetection,
    *,
    hazard_type: str = 'avalanche',
    promoted: bool = SAR_UNET_PROMOTED,
) -> dict[str, Any]:
    record = {
        'source': 'sar_unet',
        'fusion_source': 'sar_unet',
        'hazard_type': hazard_type,
        'description': f'SAR U-Net avalanche candidate over {detection.region_key}',
        'severity': 3,
        'confidence': float(detection.probability),
        'label_confidence': float(detection.probability),
        'training_eligible': bool(promoted),
        'training_eligible_reason': None if promoted else SAR_UNET_SHADOW_REASON,
        'timestamp': detection.scene_time,
        'location': f"SRID=4326;POINT({detection.centroid['lng']} {detection.centroid['lat']})",
        'source_model': detection.model_version,
        'source_scene_ids': detection.source_scene_ids,
        'geometry_type': 'polygon',
        'mask_asset_ref': detection.mask_asset_ref,
        'features': {
            'region_key': detection.region_key,
            'sar_scene_time': detection.scene_time,
            'sar_scene_ids': detection.source_scene_ids,
            'sar_geometry': detection.geometry,
            'sar_centroid': detection.centroid,
            'sar_coverage_state': 'model_segmented',
            'shadow_mask_applied': True,
            'fusion_method': detection.model_version,
            'hazard_type': hazard_type,
        },
    }
    record.update(materialize_label_governance(record))
    return record


def build_detection_from_scene(
    scene: dict[str, Any],
    *,
    probability_mask: np.ndarray,
    mask_asset_ref: str | None,
    model_version: str,
    threshold: float = SAR_UNET_SEGMENTATION_THRESHOLD,
) -> SegmentationDetection | None:
    bbox = _coerce_bbox(scene.get('bbox'))
    geometry = polygonize_probability_mask(probability_mask, bbox=bbox, threshold=threshold)
    if not geometry:
        return None
    centroid = mask_centroid(probability_mask, bbox=bbox, threshold=threshold)
    mask = probability_mask >= threshold
    probability = float(np.mean(probability_mask[mask])) if np.any(mask) else float(np.max(probability_mask))
    probability = float(max(0.0, min(0.99, probability)))
    return SegmentationDetection(
        scene_id=_scene_id(scene),
        region_key=_scene_region_key(scene),
        scene_time=_scene_time(scene),
        bbox=bbox,
        probability=probability,
        centroid=centroid,
        geometry=geometry,
        mask_asset_ref=mask_asset_ref,
        model_version=model_version,
        source_scene_ids=_scene_ids(scene),
    )


def persist_shadow_detections(records: list[dict[str, Any]]) -> dict[str, int]:
    if not records or not has_supabase_credentials():
        return {'persisted_events': 0, 'artifact_rows_persisted': 0}
    inserted = rest_insert('avalanche_events', records)
    matched_count = min(len(inserted), len(records))
    if len(inserted) != len(records):
        print(
            f'[sar_unet_worker] WARNING: inserted {len(inserted)} rows for {len(records)} records; '
            f'artifact persistence truncated to {matched_count} matched rows.',
            file=sys.stderr,
        )
    artifact_rows_persisted = persist_sar_artifacts(inserted[:matched_count], records[:matched_count])
    return {
        'persisted_events': len(inserted),
        'artifact_rows_persisted': artifact_rows_persisted,
    }


def compute_mask_metrics(prediction_masks: list[np.ndarray], truth_masks: list[np.ndarray]) -> dict[str, Any]:
    if not prediction_masks or not truth_masks or len(prediction_masks) != len(truth_masks):
        return {'status': 'skipped_no_ground_truth'}
    prediction = np.concatenate([mask.astype(bool).ravel() for mask in prediction_masks])
    truth = np.concatenate([mask.astype(bool).ravel() for mask in truth_masks])
    tp = int(np.sum(prediction & truth))
    fp = int(np.sum(prediction & ~truth))
    fn = int(np.sum(~prediction & truth))
    tn = int(np.sum(~prediction & ~truth))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-9)
    iou = tp / max(tp + fp + fn, 1)
    false_positive_rate = fp / max(fp + tn, 1)
    return {
        'status': 'ok',
        'scene_count': len(prediction_masks),
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'iou': iou,
        'false_positive_rate': false_positive_rate,
    }


def _load_mask_array(value: Any) -> np.ndarray:
    if isinstance(value, str) and value:
        return _load_mask_array_from_string_ref(value)
    return np.asarray(value, dtype=np.float32)


def _ref_suffix(value: str) -> str:
    parsed = urlparse(value)
    candidate = parsed.path if parsed.scheme else value
    return Path(candidate).suffix.lower()


def _looks_like_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _looks_like_storage_ref(value: str) -> bool:
    if not value or value.startswith(('/', './', '../', '~')):
        return False
    if _looks_like_http_url(value):
        return False
    bucket, _, object_path = value.partition('/')
    return bool(bucket and object_path)


def _load_mask_array_from_bytes(payload: bytes, *, suffix: str) -> np.ndarray:
    suffix = suffix.lower()
    if suffix == '.npz':
        loaded = np.load(BytesIO(payload))
        candidate = loaded['mask'] if 'mask' in loaded else loaded[loaded.files[0]]
        return np.asarray(candidate, dtype=np.float32)
    if suffix == '.npy':
        return np.asarray(np.load(BytesIO(payload)), dtype=np.float32)
    if suffix in {'.tif', '.tiff'}:
        if MemoryFile is None:
            raise RuntimeError('rasterio is required to read GeoTIFF evaluation masks')
        with MemoryFile(payload) as memory_file:
            with memory_file.open() as dataset:
                band = np.asarray(dataset.read(1), dtype=np.float32)
                if band.size and float(np.nanmax(band)) > 1.0:
                    band = band / 255.0
                return band
    raise ValueError(
        f'unsupported evaluation mask format "{suffix}". Supported: .npy, .npz, .tif, .tiff',
    )


def _load_mask_array_from_string_ref(value: str) -> np.ndarray:
    suffix = _ref_suffix(value)
    if suffix not in {'.npy', '.npz', '.tif', '.tiff'}:
        raise ValueError(
            f'unsupported evaluation mask reference "{value}". '
            'Use .npy, .npz, .tif, or .tiff data sources.',
        )

    if _looks_like_http_url(value):
        response = requests.get(value, timeout=120)
        response.raise_for_status()
        return _load_mask_array_from_bytes(response.content, suffix=suffix)

    # Check Supabase Storage ref BEFORE local path so that bucket-path refs
    # (e.g. 'sar-masks/heldout/mask.tif') always route to storage even when an
    # artifact volume or test directory with the same name exists locally.
    if _looks_like_storage_ref(value):
        bucket, _, object_path = value.partition('/')
        payload = storage_download_bytes(bucket=bucket, object_path=object_path)
        return _load_mask_array_from_bytes(payload, suffix=suffix)

    # Absolute paths and ./-relative paths reach here.
    path = Path(value)
    if path.exists():
        return _load_mask_array_from_bytes(path.read_bytes(), suffix=suffix)

    raise FileNotFoundError(
        f'evaluation mask ref not found or unreadable: {value}. '
        'Expected an absolute/relative local path, http(s) URL, or Supabase storage ref bucket/path.',
    )


def _load_stack_array_from_bytes(payload: bytes, *, suffix: str) -> np.ndarray:
    suffix = suffix.lower()
    if suffix == '.npz':
        loaded = np.load(BytesIO(payload))
        candidate = loaded['stack'] if 'stack' in loaded else loaded[loaded.files[0]]
        return np.asarray(candidate, dtype=np.float32)
    if suffix == '.npy':
        return np.asarray(np.load(BytesIO(payload)), dtype=np.float32)
    if suffix in {'.tif', '.tiff'}:
        if MemoryFile is None:
            raise RuntimeError('rasterio is required to read GeoTIFF scene stacks')
        with MemoryFile(payload) as memory_file:
            with memory_file.open() as dataset:
                return np.asarray(dataset.read(), dtype=np.float32)
    raise ValueError(
        f'unsupported scene stack format "{suffix}". Supported: .npy, .npz, .tif, .tiff',
    )


def _load_stack_array_from_string_ref(value: str) -> np.ndarray:
    suffix = _ref_suffix(value)
    if suffix not in {'.npy', '.npz', '.tif', '.tiff'}:
        raise ValueError(
            f'unsupported scene stack reference "{value}". '
            'Use .npy, .npz, .tif, or .tiff data sources.',
        )
    if _looks_like_http_url(value):
        response = requests.get(value, timeout=120)
        response.raise_for_status()
        return _load_stack_array_from_bytes(response.content, suffix=suffix)
    if _looks_like_storage_ref(value):
        bucket, _, object_path = value.partition('/')
        payload = storage_download_bytes(bucket=bucket, object_path=object_path)
        return _load_stack_array_from_bytes(payload, suffix=suffix)
    path = Path(value)
    if path.exists():
        return _load_stack_array_from_bytes(path.read_bytes(), suffix=suffix)
    raise FileNotFoundError(
        f'scene stack ref not found or unreadable: {value}. '
        'Expected an absolute/relative local path, http(s) URL, or Supabase storage ref bucket/path.',
    )


def load_reference_set_scenes(
    reference_set_key: str,
    *,
    prediction_model_version: str,
    authoritative_only: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    set_row, items = load_reference_bundle(
        reference_set_key,
        authoritative_only=authoritative_only,
        status='active' if authoritative_only else None,
    )
    scenes = [
        reference_item_to_scene(
            set_row,
            item,
            model_version=prediction_model_version,
        )
        for item in items
    ]
    return set_row, scenes


def evaluate_scene_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    # If the caller supplies reference_set_key without pre-built scenes[], resolve
    # the authoritative manifest from Supabase. This allows trigger-job and other
    # callers to pass only the key when they don't have manifest-building capability.
    reference_set_key = str(manifest.get('reference_set_key') or '').strip()
    if reference_set_key and (not isinstance(manifest.get('scenes'), list) or not manifest.get('scenes')):
        try:
            from backend.sar_release_manifest import ReleaseManifestOptions, build_release_manifest_from_reference_set
            prediction_model_version = str(
                manifest.get('prediction_model_version') or 'sar_unet_resnet34_shadow_v1'
            ).strip()
            manifest = build_release_manifest_from_reference_set(
                reference_set_key=reference_set_key,
                options=ReleaseManifestOptions(
                    prediction_model_version=prediction_model_version,
                    validate_refs=False,  # storage refs are not locally resolvable in the worker
                    authoritative_only=True,
                ),
            )
        except Exception as exc:
            return {
                'status': 'invalid_manifest',
                'reason': f'could not resolve reference_set_key "{reference_set_key}": {exc}',
                'scene_count': 0,
                'region_coverage': [],
                'beats_baseline': False,
                'baseline_f1_floor_used': None,
            }

    scenes = manifest.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        return {
            'status': 'invalid_manifest',
            'reason': 'evaluation manifest must include a non-empty scenes[] list',
            'scene_count': 0,
            'region_coverage': [],
            'beats_baseline': False,
            'baseline_f1_floor_used': None,
        }
    prediction_threshold = float(
        manifest.get('prediction_threshold')
        or manifest.get('threshold')
        or SAR_UNET_SEGMENTATION_THRESHOLD
    )
    truth_threshold = float(manifest.get('truth_threshold') or 0.5)
    postprocess_min_component_area_px = int(manifest.get('postprocess_min_component_area_px') or 0)
    postprocess_opening_size_px = int(manifest.get('postprocess_opening_size_px') or 0)
    predictions: list[np.ndarray] = []
    truths: list[np.ndarray] = []
    baselines: list[np.ndarray] = []
    region_coverage = sorted({
        str(scene.get('region_key') or scene.get('region') or 'unknown')
        for scene in scenes
        if isinstance(scene, dict)
    })
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        if scene.get('prediction_mask') is None or scene.get('truth_mask') is None:
            continue
        prediction = _load_mask_array(scene['prediction_mask']) >= prediction_threshold
        if postprocess_min_component_area_px > 0 or postprocess_opening_size_px > 0:
            prediction = _postprocess_binary_mask(
                prediction,
                min_component_area_px=postprocess_min_component_area_px,
                opening_size_px=postprocess_opening_size_px,
            )
        predictions.append(prediction)
        truths.append(_load_mask_array(scene['truth_mask']) >= truth_threshold)
        if scene.get('baseline_mask') is not None:
            baselines.append(_load_mask_array(scene['baseline_mask']) >= truth_threshold)

    if not predictions or len(predictions) != len(truths):
        return {
            'status': 'invalid_manifest',
            'reason': 'evaluation scenes must include prediction_mask and truth_mask for held-out comparison',
            'scene_count': 0,
            'region_coverage': region_coverage,
            'beats_baseline': False,
            'baseline_f1_floor_used': None,
        }

    metrics = compute_mask_metrics(predictions, truths)
    baseline_margin = float(manifest.get('baseline_margin', 0.05))
    baseline_f1_floor_raw = float(manifest.get('baseline_f1_floor') or 0.0)
    baseline_metrics = manifest.get('baseline_metrics') if isinstance(manifest.get('baseline_metrics'), dict) else None
    derived_baseline_metrics: dict[str, Any] | None = None
    baseline_f1_floor_used: float | None = None
    if baseline_f1_floor_raw > 0.0:
        baseline_f1_floor_used = baseline_f1_floor_raw
    elif baseline_metrics and float(baseline_metrics.get('f1') or 0.0) > 0.0:
        baseline_f1_floor_used = float(baseline_metrics['f1']) + baseline_margin
        derived_baseline_metrics = {'source': 'manifest.baseline_metrics', **baseline_metrics}
    elif baselines and len(baselines) == len(truths):
        derived_baseline_metrics = compute_mask_metrics(baselines, truths)
        baseline_f1_floor_used = float(derived_baseline_metrics.get('f1', 0.0)) + baseline_margin
    if baseline_f1_floor_used is None or baseline_f1_floor_used <= 0.0:
        return {
            'status': 'invalid_manifest',
            'reason': (
                'evaluation manifest must provide a positive baseline_f1_floor, '
                'baseline_metrics.f1, or per-scene baseline_mask values aligned to truth_mask'
            ),
            'scene_count': len(predictions),
            'region_coverage': region_coverage,
            'beats_baseline': False,
            'baseline_f1_floor_used': None,
        }
    metrics['status'] = 'ok'
    metrics['prediction_threshold'] = prediction_threshold
    metrics['truth_threshold'] = truth_threshold
    metrics['postprocess_min_component_area_px'] = postprocess_min_component_area_px
    metrics['postprocess_opening_size_px'] = postprocess_opening_size_px
    metrics['baseline_f1_floor_used'] = baseline_f1_floor_used
    metrics['baseline_margin'] = baseline_margin
    if derived_baseline_metrics is not None:
        metrics['baseline_metrics'] = derived_baseline_metrics
    metrics['beats_baseline'] = bool(metrics.get('f1', 0.0) > baseline_f1_floor_used)
    metrics['region_coverage'] = region_coverage
    return metrics


def run_segmentation(
    *,
    scenes: list[dict[str, Any]],
    model_path: Path,
    artifact_root: Path,
    threshold: float = SAR_UNET_SEGMENTATION_THRESHOLD,
    device: str = 'cpu',
    hazard_type: str = 'avalanche',
    persist_events: bool = True,
    promoted: bool = SAR_UNET_PROMOTED,
    model_version: str = SAR_UNET_MODEL_VERSION,
    model_family: str = SAR_UNET_MODEL_FAMILY,
) -> dict[str, Any]:
    artifact_dir = create_artifact_dir(artifact_root)
    if not scenes:
        manifest = {'status': 'skipped_no_scenes', 'detections': [], 'persisted_events': 0}
        dump_json(artifact_dir / 'sar_segment_manifest.json', manifest)
        return manifest

    resolved_family = _normalize_model_family(model_family)
    image_size = None
    if resolved_family == 'swinunet_tiny_diff':
        first_manifest_ref = _scene_manifest_ref(scenes[0])
        if first_manifest_ref:
            manifest = _load_avalcd_manifest_from_string_ref(first_manifest_ref)
            image_size = int(manifest.get('patch_size') or 128)
        else:
            first_pre_stack, first_post_stack = load_bitemporal_scene_inputs(scenes[0])
            if first_pre_stack.shape != first_post_stack.shape:
                raise ValueError('swinunet_tiny_diff requires pre/post stacks with identical shapes')
            if first_pre_stack.shape[1] != first_pre_stack.shape[2]:
                raise ValueError('swinunet_tiny_diff currently requires square scene patches')
            image_size = int(first_pre_stack.shape[1])
    loaded_model = build_unet_model(
        model_path,
        device=device,
        model_family=resolved_family,
        image_size=image_size,
        promoted=promoted,
    )
    detections: list[SegmentationDetection] = []
    records: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        print(
            f'[sar_unet_worker] segmenting scene {index}/{len(scenes)}: {_scene_id(scene)}',
            file=sys.stderr,
            flush=True,
        )
        probability_mask = predict_scene_probability_mask(loaded_model, scene, device=device)
        bbox = _coerce_bbox(scene.get('bbox'))
        mask_asset_ref = None
        desired_prediction_ref = scene.get('prediction_mask')
        if has_supabase_credentials() and (persist_events or (isinstance(desired_prediction_ref, str) and desired_prediction_ref.strip())):
            geotiff_bytes = encode_mask_geotiff(probability_mask, bbox=bbox)
            if isinstance(desired_prediction_ref, str) and desired_prediction_ref.strip():
                upload_bucket, mask_object_path = parse_storage_ref(desired_prediction_ref.strip())
            else:
                upload_bucket = SAR_MASK_BUCKET
                mask_object_path = build_mask_object_path(
                    region_key=_scene_region_key(scene),
                    scene_id=_scene_id(scene),
                    scene_time=_scene_time(scene),
                    model_version=model_version,
                )
            mask_asset_ref = storage_upload_bytes(
                bucket=upload_bucket,
                object_path=mask_object_path,
                payload=geotiff_bytes,
                content_type='image/tiff',
            )
        detection = build_detection_from_scene(
            scene,
            probability_mask=probability_mask,
            mask_asset_ref=mask_asset_ref,
            model_version=model_version,
            threshold=threshold,
        )
        if detection is None:
            print(
                f'[sar_unet_worker] completed scene {index}/{len(scenes)}: {_scene_id(scene)} '
                '(no detection above threshold)',
                file=sys.stderr,
                flush=True,
            )
            continue
        detections.append(detection)
        records.append(build_shadow_event_record(detection, hazard_type=hazard_type, promoted=promoted))
        print(
            f'[sar_unet_worker] completed scene {index}/{len(scenes)}: {_scene_id(scene)} '
            f'-> mask_asset_ref={mask_asset_ref}',
            file=sys.stderr,
            flush=True,
        )

    persistence_summary = {'persisted_events': 0, 'artifact_rows_persisted': 0}
    if persist_events and detections and model_path.exists():
        persistence_summary = persist_shadow_detections(records)

    manifest = {
        'status': 'ok',
        'shadow_mode': not promoted,
        'model_family': loaded_model.model_family,
        'model_version': model_version,
        'scene_count': len(scenes),
        'detections_count': len(detections),
        'persisted_events': persistence_summary['persisted_events'],
        'artifact_rows_persisted': persistence_summary['artifact_rows_persisted'],
        'mask_asset_refs': [detection.mask_asset_ref for detection in detections if detection.mask_asset_ref],
        'detections': [detection.as_dict() for detection in detections],
    }
    if loaded_model.checkpoint_key_mismatch.get('has_mismatch'):
        manifest['checkpoint_key_mismatch'] = loaded_model.checkpoint_key_mismatch
    dump_json(artifact_dir / 'sar_segment_manifest.json', manifest)
    return manifest


def flip_to_training_eligible(event_ids: list[str]) -> int:
    """Post-SAR-promotion: flip shadow sar_unet events to training_eligible=True.

    Called ONLY after ``evaluate-release`` returns ``beats_baseline=True`` and the
    operator has set ``SAR_UNET_PROMOTED=True``. Clears ``governance_version`` so
    the next training run re-materialises governance stamps on the promoted rows.

    Returns the number of rows successfully flipped.
    """
    if not event_ids:
        return 0
    if not has_supabase_credentials():
        print(
            f'[sar_unet_worker] flip_to_training_eligible: Supabase credentials absent; '
            f'would flip {len(event_ids)} events',
            file=sys.stderr,
        )
        return 0
    flipped = 0
    for event_id in event_ids:
        try:
            rows = rest_upsert(
                'avalanche_events',
                [{
                    'id': event_id,
                    'training_eligible': True,
                    'training_eligible_reason': None,
                    'governance_version': None,  # force re-governance on next train
                }],
                on_conflict='id',
            )
            flipped += len(rows)
        except Exception as exc:
            print(
                f'[sar_unet_worker] flip_to_training_eligible failed for {event_id}: {exc}',
                file=sys.stderr,
            )
    return flipped


def _artifact_snapshot(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {path.name for path in root.iterdir() if is_artifact_run_dir(path)}


def _discover_new_artifact_dir(root: Path, before: set[str]) -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(path for path in root.iterdir() if is_artifact_run_dir(path) and path.name not in before)
    return candidates[-1] if candidates else None


def _tail_lines(text: str, *, limit: int = 20) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def _run_python_module(module: str, *, env: dict[str, str], args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, '-m', module, *(args or [])]
    return subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_training_summary(artifact_dir: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if artifact_dir is None:
        return {}, {}
    metrics_path = artifact_dir / 'training_metrics.json'
    if not metrics_path.exists():
        return {}, {}
    metrics = load_json(metrics_path)
    lstm_head_meta = metrics.get('lstm_head_meta') if isinstance(metrics, dict) else {}
    return metrics if isinstance(metrics, dict) else {}, lstm_head_meta if isinstance(lstm_head_meta, dict) else {}


def _load_inference_summary(artifact_dir: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if artifact_dir is None:
        return {}, {}
    manifest_path = artifact_dir / 'inference_manifest.json'
    forecast_path = artifact_dir / 'forecast_grids.json'
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    forecast_payload = load_json(forecast_path) if forecast_path.exists() else []
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(forecast_payload, list):
        forecast_payload = []

    total_cells_written = 0
    cells_with_shap = 0
    sample_dominant_driver = None
    surrogate_model_version = None
    dynamic_model_type = None
    dynamic_model_version = None
    partial_regions = 0
    ready_cells = 0
    unavailable_terrain_cells = 0
    unavailable_weather_cells = 0
    for region_payload in forecast_payload:
        if not isinstance(region_payload, dict):
            continue
        if region_payload.get('status') == 'partial':
            partial_regions += 1
        metadata = region_payload.get('model_metadata') if isinstance(region_payload.get('model_metadata'), dict) else {}
        surrogate_model_version = surrogate_model_version or metadata.get('surrogate_model_version')
        dynamic_model_type = dynamic_model_type or metadata.get('dynamic_model_type')
        dynamic_model_version = dynamic_model_version or metadata.get('dynamic_model_version')
        grid_geojson = region_payload.get('grid_geojson') if isinstance(region_payload.get('grid_geojson'), list) else []
        total_cells_written += len(grid_geojson)
        for cell in grid_geojson:
            if not isinstance(cell, dict):
                continue
            cell_status = str(cell.get('status') or 'ready')
            if cell_status == 'ready':
                ready_cells += 1
            elif cell_status == 'unavailable_terrain':
                unavailable_terrain_cells += 1
            elif cell_status == 'unavailable_weather':
                unavailable_weather_cells += 1
            shap_context = cell.get('shap_context') if isinstance(cell.get('shap_context'), dict) else {}
            top_features = shap_context.get('top_features') if isinstance(shap_context.get('top_features'), list) else []
            has_shap = bool(cell.get('shap_values')) or bool(top_features)
            if has_shap:
                cells_with_shap += 1
            if sample_dominant_driver is None:
                dominant_driver = cell.get('dominant_driver_feature')
                if isinstance(dominant_driver, str) and dominant_driver.strip():
                    sample_dominant_driver = dominant_driver

    return manifest, {
        'regions_written': manifest.get('regions_written', len(forecast_payload)),
        'total_cells_written': manifest.get('total_cells_written', total_cells_written),
        'cells_with_shap': cells_with_shap,
        'partial_regions': manifest.get('partial_regions', partial_regions),
        'ready_cells': manifest.get('ready_cells', ready_cells),
        'unavailable_terrain_cells': manifest.get('unavailable_terrain_cells', unavailable_terrain_cells),
        'unavailable_weather_cells': manifest.get('unavailable_weather_cells', unavailable_weather_cells),
        'sample_dominant_driver': sample_dominant_driver,
        'surrogate_model_version': surrogate_model_version,
        'dynamic_model_type': dynamic_model_type,
        'dynamic_model_version': dynamic_model_version,
        'completed_at': manifest.get('completed_at'),
        'dry_run': bool(manifest.get('dry_run', False)),
    }


def _build_inference_linkage(
    *,
    request: dict[str, Any],
    artifact_dir: Path | None,
    inference_manifest: dict[str, Any],
) -> dict[str, Any]:
    compute_job_id = str(
        request.get('compute_job_id')
        or request.get('job_id')
        or inference_manifest.get('compute_job_id')
        or ''
    ).strip() or None
    forecast_run_id = inference_manifest.get('forecast_run_id')
    forecast_run_ids = inference_manifest.get('forecast_run_ids')
    forecast_run_ids_by_region = inference_manifest.get('forecast_run_ids_by_region')
    modal_call_id = str(
        request.get('modal_call_id')
        or os.environ.get('MODAL_CALL_ID')
        or ''
    ).strip() or None
    return {
        'compute_job_id': compute_job_id,
        'modal_call_id': modal_call_id,
        'artifact_dir': str(artifact_dir) if artifact_dir is not None else None,
        'forecast_run_id': forecast_run_id,
        'forecast_run_ids': forecast_run_ids if isinstance(forecast_run_ids, list) else [],
        'forecast_run_ids_by_region': (
            forecast_run_ids_by_region
            if isinstance(forecast_run_ids_by_region, dict)
            else {}
        ),
    }


def _sync_compute_job_inference_linkage_best_effort(
    *,
    linkage: dict[str, Any],
) -> None:
    compute_job_id = linkage.get('compute_job_id')
    if not isinstance(compute_job_id, str) or not compute_job_id.strip():
        return
    if not has_supabase_credentials():
        return
    try:
        merge_compute_job_result_linkage(
            compute_job_id=compute_job_id,
            linkage=linkage,
        )
    except Exception:
        pass


def _sync_compute_job_inference_terminal_result_best_effort(
    *,
    linkage: dict[str, Any],
    worker_result: dict[str, Any],
) -> None:
    compute_job_id = linkage.get('compute_job_id')
    if not isinstance(compute_job_id, str) or not compute_job_id.strip():
        return
    if not has_supabase_credentials():
        return
    try:
        merge_compute_job_terminal_result(
            compute_job_id=compute_job_id,
            linkage=linkage,
            worker_result=worker_result,
        )
    except Exception:
        pass


def _resolve_requested_infer_artifact_dir(
    request: dict[str, Any],
    *,
    artifact_root: Path,
) -> tuple[Path | None, str | None]:
    raw_artifact_dir = request.get('artifact_dir')
    if raw_artifact_dir is None or not str(raw_artifact_dir).strip():
        return None, None
    resolved = resolve_artifact_dir(artifact_root, str(raw_artifact_dir), require_model=True)
    return resolved, str(resolved)


def run_train_mtslstm(
    request: dict[str, Any],
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    before = _artifact_snapshot(artifact_root)
    env = os.environ.copy()
    env.update({
        'ARTIFACT_ROOT': str(artifact_root),
        'DEM_ROOT': str(Path(env.get('DEM_ROOT') or artifact_root / 'dem')),
        'DEM_DIR': str(Path(env.get('DEM_DIR') or env.get('DEM_ROOT') or artifact_root / 'dem')),
        'HAZARD_TYPE': str(request.get('hazard_type') or env.get('HAZARD_TYPE') or 'avalanche'),
        'MTS_RUNTIME_PROVIDER': 'modal',
        'TRAIN_MTS_LSTM_HEAD': 'true',
        'USE_MTS_LSTM_HEAD': 'true',
        'ALLOW_MODEL_STATUS_PUBLISH': 'true' if _flag_from_payload(request.get('allow_publish'), False) else 'false',
        'MTS_LSTM_EPOCHS': str(int(request.get('epochs') or DEFAULT_LSTM_EPOCHS)),
        'MTS_LSTM_EARLY_STOPPING': 'true' if _flag_from_payload(request.get('early_stopping'), True) else 'false',
        'MTS_LSTM_MIN_EPOCHS_BEFORE_EARLY_STOPPING': str(int(request.get('minimum_epochs_before_early_stopping') or DEFAULT_LSTM_MIN_EPOCHS)),
        'MTS_LSTM_EARLY_STOPPING_PATIENCE': str(int(request.get('patience_early_stopping') or DEFAULT_LSTM_PATIENCE)),
        'SAR_RELEASE_GATE_PASSED': 'true' if _flag_from_payload(request.get('sar_release_gate_passed'), False) else 'false',
        'REQUESTED_DATASET_SNAPSHOT_ID': str(request.get('dataset_snapshot_id') or 'latest'),
        'ML_SEED': str(int(request.get('seed') or env.get('ML_SEED') or '42')),
        'SAMPLES_PER_REGION': str(int(request.get('samples_per_region') or env.get('SAMPLES_PER_REGION') or '500')),
        'PSS_FLOOR': str(request.get('pss_floor') or env.get('PSS_FLOOR') or '0.45'),
    })
    completed = _run_python_module('backend.train_model', env=env)
    artifact_dir = _discover_new_artifact_dir(artifact_root, before)
    new_artifact_created = artifact_dir is not None
    artifact_stale_fallback_used = False
    if artifact_dir is None:
        try:
            artifact_dir = latest_artifact_dir(artifact_root)
            artifact_stale_fallback_used = artifact_dir is not None
        except Exception:
            artifact_dir = None
    metrics, lstm_head_meta = _load_training_summary(artifact_dir)
    phase2_summary = metrics.get('phase2_evaluation') if isinstance(metrics.get('phase2_evaluation'), dict) else {}
    shadow_mode = _flag_from_payload(request.get('shadow_mode'), True)
    allow_publish = _flag_from_payload(request.get('allow_publish'), False)
    if not new_artifact_created:
        status = 'failed_no_new_artifact'
    elif completed.returncode == 0:
        status = 'ok'
    elif metrics:
        status = 'completed_with_gate_failure'
    else:
        status = 'failed'
    report = {
        'status': status,
        'request_type': str(request.get('request_type') or 'train_mtslstm'),
        'runtime_provider': 'modal',
        'shadow_mode': shadow_mode,
        'allow_publish': allow_publish,
        'promotion_rule': str(request.get('promotion_rule') or 'strict_pss_gt_rf_and_brier_lte_rf'),
        'new_artifact_created': new_artifact_created,
        'artifact_stale_fallback_used': artifact_stale_fallback_used,
        'model_artifact_ref': str((artifact_dir / 'model.joblib')) if artifact_dir and (artifact_dir / 'model.joblib').exists() else None,
        'artifact_dir': str(artifact_dir) if artifact_dir else None,
        'dataset_snapshot_id': (
            lstm_head_meta.get('dataset_snapshot_id')
            or metrics.get('dataset_snapshot_id')
            or request.get('dataset_snapshot_id')
        ),
        'lstm_pss': lstm_head_meta.get('pss_holdout'),
        'lstm_pss_uncalibrated': lstm_head_meta.get('pss_holdout_uncalibrated'),
        'lstm_pss_calibrated': lstm_head_meta.get('pss_holdout_calibrated', lstm_head_meta.get('pss_holdout')),
        'rf_pss': lstm_head_meta.get('rf_pss_holdout'),
        'lstm_brier': lstm_head_meta.get('brier_score'),
        'lstm_brier_uncalibrated': lstm_head_meta.get('brier_score_uncalibrated'),
        'lstm_brier_calibrated': lstm_head_meta.get('brier_score_calibrated', lstm_head_meta.get('brier_score')),
        'rf_brier': lstm_head_meta.get('rf_brier_score'),
        'calibration_method': lstm_head_meta.get('calibration_method'),
        'calibration_applied': bool(lstm_head_meta.get('calibration_applied')),
        'calibration_reason': lstm_head_meta.get('calibration_reason'),
        'calibration_improved': bool(lstm_head_meta.get('calibration_improved')),
        'label_snapshot_id': metrics.get('label_snapshot_id'),
        'hindcast_run_id': metrics.get('hindcast_run_id'),
        'calibration_report_ref': metrics.get('calibration_report_ref') or phase2_summary.get('calibration_report_ref'),
        'calibration_report_ids': metrics.get('calibration_report_ids') or phase2_summary.get('calibration_report_ids') or [],
        'shadow_quality_gate_passed': bool(lstm_head_meta.get('shadow_quality_gate_passed')),
        'sar_release_gate_passed': bool(lstm_head_meta.get('sar_release_gate_passed')),
        'production_eligibility_gate_passed': bool(lstm_head_meta.get('production_eligibility_gate_passed')),
        'promotion_gate_passed': bool(lstm_head_meta.get('promotion_gate_passed')),
        'epochs_requested': lstm_head_meta.get('epochs_requested'),
        'epochs_completed': lstm_head_meta.get('epochs_completed'),
        'early_stopped': bool(lstm_head_meta.get('early_stopped')),
        'stdout_tail': _tail_lines(completed.stdout),
        'stderr_tail': _tail_lines(completed.stderr),
        'subprocess_returncode': completed.returncode,
    }
    if artifact_dir is not None:
        dump_json(artifact_dir / 'train_mtslstm_manifest.json', report)
    return report


def run_infer_mtslstm(
    request: dict[str, Any],
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    dry_run = _flag_from_payload(request.get('dry_run'), False)
    shadow_mode = _flag_from_payload(request.get('shadow_mode'), True)
    lifeboat_mode = _flag_from_payload(request.get('lifeboat_mode'), False)
    lifeboat_profile = str(request.get('lifeboat_profile') or 'proof72').strip() or 'proof72'
    default_forecast_hours = 24 if lifeboat_mode and lifeboat_profile == 'smoke24' else 72
    default_grid_size = 5 if lifeboat_mode else 20
    forecast_hours = int(request.get('forecast_hours') or os.environ.get('FORECAST_HOURS') or str(default_forecast_hours))
    grid_size = int(request.get('grid_size') or os.environ.get('GRID_SIZE') or str(default_grid_size))
    skip_tree_shap = _flag_from_payload(request.get('skip_tree_shap'), lifeboat_mode)
    skip_shap_cache = _flag_from_payload(request.get('skip_shap_cache'), lifeboat_mode)
    skip_runout_generation = _flag_from_payload(request.get('skip_runout_generation'), lifeboat_mode)
    skip_compatibility_write = _flag_from_payload(request.get('skip_compatibility_write'), lifeboat_mode)
    emit_stage_metrics = _flag_from_payload(request.get('emit_stage_metrics'), lifeboat_mode)
    requested_artifact_dir = request.get('artifact_dir')
    try:
        resolved_artifact_dir, resolved_artifact_dir_text = _resolve_requested_infer_artifact_dir(
            request,
            artifact_root=artifact_root,
        )
    except (FileNotFoundError, ValueError) as exc:
        return {
            'status': 'failed',
            'request_type': str(request.get('request_type') or 'infer_mtslstm'),
            'runtime_provider': 'modal',
            'compute_job_id': str(request.get('compute_job_id') or request.get('job_id') or '').strip() or None,
            'artifact_dir': str(requested_artifact_dir).strip() if requested_artifact_dir is not None else None,
            'forecast_hours': forecast_hours,
            'grid_size': grid_size,
            'regions_written': None,
            'total_cells_written': None,
            'cells_with_shap': None,
            'sample_dominant_driver': None,
            'surrogate_model_version': None,
            'dynamic_model_type': None,
            'dynamic_model_version': None,
            'completed_at': None,
            'promotion_gate_passed': False,
            'shadow_mode': shadow_mode,
            'shadow_mode_active': shadow_mode,
            'dry_run': dry_run,
            'lifeboat_mode': lifeboat_mode,
            'lifeboat_profile': lifeboat_profile if lifeboat_mode else None,
            'dataset_snapshot_id': None,
            'forecast_run_id': None,
            'forecast_run_ids': [],
            'forecast_run_ids_by_region': {},
            'stdout_tail': [],
            'stderr_tail': [str(exc)],
            'subprocess_returncode': None,
        }
    env = os.environ.copy()
    env.update({
        'ARTIFACT_ROOT': str(artifact_root),
        'HAZARD_TYPE': str(request.get('hazard_type') or env.get('HAZARD_TYPE') or 'avalanche'),
        'FORECAST_HOURS': str(forecast_hours),
        'GRID_SIZE': str(grid_size),
        'COMPUTE_JOB_ID': str(request.get('compute_job_id') or request.get('job_id') or env.get('COMPUTE_JOB_ID') or '').strip(),
        'MODAL_CALL_ID': str(request.get('modal_call_id') or env.get('MODAL_CALL_ID') or '').strip(),
    })
    requested_region_keys: list[str] = []
    singular_region_key = request.get('region_key')
    if isinstance(singular_region_key, str) and singular_region_key.strip():
        requested_region_keys.append(singular_region_key.strip())
    raw_region_keys = request.get('region_keys')
    if isinstance(raw_region_keys, (list, tuple)):
        requested_region_keys.extend(
            str(region_key).strip()
            for region_key in raw_region_keys
            if str(region_key).strip()
        )
    args: list[str] = []
    if dry_run:
        args.append('--dry-run')
    if resolved_artifact_dir_text:
        args.extend(['--artifact-dir', resolved_artifact_dir_text])
    if lifeboat_mode:
        args.extend(['--lifeboat-mode', '--lifeboat-profile', lifeboat_profile])
    if skip_tree_shap:
        args.append('--skip-tree-shap')
    if skip_shap_cache:
        args.append('--skip-shap-cache')
    if skip_runout_generation:
        args.append('--skip-runout-generation')
    if skip_compatibility_write:
        args.append('--skip-compatibility-write')
    if emit_stage_metrics:
        args.append('--emit-stage-metrics')
    for region_key in requested_region_keys:
        args.extend(['--region-key', region_key])
    completed = _run_python_module('backend.daily_inference', env=env, args=args)
    artifact_dir = resolved_artifact_dir
    if artifact_dir is None:
        try:
            artifact_dir = latest_artifact_dir(artifact_root)
        except Exception:
            artifact_dir = None
    inference_manifest = {}
    lstm_head_meta = {}
    if artifact_dir is not None:
        inference_manifest, summary = _load_inference_summary(artifact_dir)
        metrics_path = artifact_dir / 'training_metrics.json'
        if metrics_path.exists():
            training_metrics = load_json(metrics_path)
            candidate = training_metrics.get('lstm_head_meta') if isinstance(training_metrics, dict) else {}
            lstm_head_meta = candidate if isinstance(candidate, dict) else {}
    else:
        summary = {}
    inference_linkage = _build_inference_linkage(
        request=request,
        artifact_dir=artifact_dir,
        inference_manifest=inference_manifest,
    )
    report = {
        'status': 'ok' if completed.returncode == 0 else 'failed',
        'request_type': str(request.get('request_type') or 'infer_mtslstm'),
        'runtime_provider': 'modal',
        'artifact_dir': str(artifact_dir) if artifact_dir else None,
        'forecast_hours': forecast_hours,
        'grid_size': grid_size,
        'regions_written': summary.get('regions_written'),
        'total_cells_written': summary.get('total_cells_written'),
        'cells_with_shap': summary.get('cells_with_shap'),
        'partial_regions': summary.get('partial_regions'),
        'ready_cells': summary.get('ready_cells'),
        'unavailable_terrain_cells': summary.get('unavailable_terrain_cells'),
        'unavailable_weather_cells': summary.get('unavailable_weather_cells'),
        'sample_dominant_driver': summary.get('sample_dominant_driver'),
        'surrogate_model_version': summary.get('surrogate_model_version'),
        'dynamic_model_type': summary.get('dynamic_model_type'),
        'dynamic_model_version': summary.get('dynamic_model_version'),
        'completed_at': summary.get('completed_at') or inference_manifest.get('completed_at'),
        'promotion_gate_passed': bool(lstm_head_meta.get('promotion_gate_passed')),
        'shadow_mode': shadow_mode,
        'shadow_mode_active': shadow_mode,
        'dry_run': dry_run,
        'lifeboat_mode': lifeboat_mode,
        'lifeboat_profile': lifeboat_profile if lifeboat_mode else None,
        'skip_tree_shap': skip_tree_shap,
        'skip_shap_cache': skip_shap_cache,
        'skip_runout_generation': skip_runout_generation,
        'skip_compatibility_write': skip_compatibility_write,
        'emit_stage_metrics': emit_stage_metrics,
        'stage_metrics_summary': inference_manifest.get('stage_metrics_summary'),
        'dataset_snapshot_id': lstm_head_meta.get('dataset_snapshot_id'),
        'stdout_tail': _tail_lines(completed.stdout),
        'stderr_tail': _tail_lines(completed.stderr),
        'subprocess_returncode': completed.returncode,
        **inference_linkage,
    }
    if artifact_dir is not None:
        dump_json(artifact_dir / 'infer_mtslstm_manifest.json', report)
    _sync_compute_job_inference_linkage_best_effort(linkage=inference_linkage)
    _sync_compute_job_inference_terminal_result_best_effort(
        linkage=inference_linkage,
        worker_result=report,
    )
    return report


def run_train_sar_unet(
    request: dict[str, Any],
    *,
    artifact_root: Path,
    device: str = 'cpu',
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    return train_sar_unet(
        request,
        artifact_root=artifact_root,
        device=device,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = load_settings()
    model_path_env = os.environ.get('SAR_UNET_MODEL_PATH')
    parser = argparse.ArgumentParser(description='Shadow-mode SAR U-Net segmentation worker')
    parser.add_argument(
        '--mode',
        choices=['sar-segment', 'evaluate-release', 'train-sar-unet', 'train-mtslstm', 'infer-mtslstm'],
        default=os.environ.get('SAR_WORKER_MODE', 'sar-segment'),
    )
    parser.add_argument('--manifest', type=Path, help='JSON manifest describing scenes or evaluation inputs')
    parser.add_argument('--artifact-root', type=Path, default=settings.artifact_root)
    parser.add_argument('--model-path', type=Path, default=Path(model_path_env) if model_path_env else None)
    parser.add_argument('--device', default=os.environ.get('SAR_UNET_DEVICE', 'cpu'))
    parser.add_argument('--threshold', type=float, default=SAR_UNET_SEGMENTATION_THRESHOLD)
    parser.add_argument('--hazard-type', default=settings.hazard_type)
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args(argv)


def _load_manifest(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def run_worker_request(
    mode: str,
    manifest: dict[str, Any],
    *,
    artifact_root: Path,
    model_path: Path | None = None,
    device: str = 'cpu',
    threshold: float = SAR_UNET_SEGMENTATION_THRESHOLD,
    hazard_type: str = 'avalanche',
    dry_run: bool = False,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    prediction_model_family = str(manifest.get('model_family') or SAR_UNET_MODEL_FAMILY)
    prediction_model_version = str(manifest.get('prediction_model_version') or SAR_UNET_MODEL_VERSION)

    if mode == 'evaluate-release':
        evaluation_manifest = manifest
        if (not isinstance(manifest.get('scenes'), list) or not manifest.get('scenes')) and isinstance(manifest.get('reference_set_key'), str):
            from backend.sar_release_manifest import ReleaseManifestOptions, build_release_manifest_from_reference_set

            evaluation_manifest = build_release_manifest_from_reference_set(
                reference_set_key=manifest['reference_set_key'].strip(),
                options=ReleaseManifestOptions(
                    baseline_margin=float(manifest.get('baseline_margin', 0.05)),
                    validate_refs=not _flag_from_payload(manifest.get('skip_validate_refs'), False),
                    prediction_model_version=prediction_model_version,
                    reference_set_key=manifest['reference_set_key'].strip(),
                    authoritative_only=_flag_from_payload(manifest.get('authoritative_only'), True),
                ),
            )
            if manifest.get('threshold') is not None:
                evaluation_manifest['threshold'] = manifest.get('threshold')
            if manifest.get('prediction_threshold') is not None:
                evaluation_manifest['prediction_threshold'] = manifest.get('prediction_threshold')
            if manifest.get('truth_threshold') is not None:
                evaluation_manifest['truth_threshold'] = manifest.get('truth_threshold')
            if manifest.get('postprocess_min_component_area_px') is not None:
                evaluation_manifest['postprocess_min_component_area_px'] = manifest.get('postprocess_min_component_area_px')
            if manifest.get('postprocess_opening_size_px') is not None:
                evaluation_manifest['postprocess_opening_size_px'] = manifest.get('postprocess_opening_size_px')
        artifact_dir = create_artifact_dir(artifact_root)
        report = evaluate_scene_manifest(evaluation_manifest)
        report.update({
            'model_version': prediction_model_version,
            'evaluated_at': _utc_now_iso(),
        })
        dump_json(artifact_dir / 'sar_evaluation_report.json', report)
        return report

    if mode == 'train-mtslstm':
        return run_train_mtslstm(manifest, artifact_root=artifact_root)

    if mode == 'infer-mtslstm':
        return run_infer_mtslstm(manifest, artifact_root=artifact_root)

    if mode == 'train-sar-unet':
        return run_train_sar_unet(
            manifest,
            artifact_root=artifact_root,
            device=device,
        )

    scenes = manifest.get('scenes')
    reference_set_key = manifest.get('reference_set_key')
    if not isinstance(scenes, list):
        if isinstance(reference_set_key, str) and reference_set_key.strip():
            try:
                set_row, scenes = load_reference_set_scenes(
                    reference_set_key.strip(),
                    prediction_model_version=prediction_model_version,
                    authoritative_only=_flag_from_payload(manifest.get('authoritative_only'), True),
                )
            except Exception as exc:
                return {
                    'status': 'invalid_reference_set',
                    'reason': str(exc),
                    'reference_set_key': reference_set_key,
                }
            manifest = {**manifest, 'scenes': scenes}
            manifest['reference_set_source_version'] = set_row.get('source_version')
        else:
            return {'status': 'skipped_no_scenes', 'reason': 'manifest missing scenes[]'}

    if not model_path or not str(model_path):
        return {'status': 'skipped_missing_weights', 'reason': 'SAR_UNET_MODEL_PATH not provided'}

    explicit_persist_events = manifest.get('persist_events')
    if explicit_persist_events is not None:
        persist_events = _flag_from_payload(explicit_persist_events, not dry_run) and not dry_run
    elif isinstance(reference_set_key, str) and reference_set_key.strip():
        persist_events = False
    else:
        persist_events = not dry_run

    return run_segmentation(
        scenes=scenes,
        model_path=model_path,
        artifact_root=artifact_root,
        threshold=threshold,
        device=device,
        hazard_type=hazard_type,
        persist_events=persist_events,
        promoted=not _flag_from_payload(manifest.get('shadow_mode'), not SAR_UNET_PROMOTED),
        model_family=prediction_model_family,
        model_version=prediction_model_version,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = _load_manifest(args.manifest)
    artifact_root = args.artifact_root
    artifact_root.mkdir(parents=True, exist_ok=True)

    try:
        result = run_worker_request(
            args.mode,
            manifest,
            artifact_root=artifact_root,
            model_path=args.model_path,
            device=args.device,
            threshold=args.threshold,
            hazard_type=args.hazard_type,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
