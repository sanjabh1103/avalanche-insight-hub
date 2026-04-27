from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import requests

from backend.common.artifacts import create_artifact_dir, dump_json, latest_artifact_dir, load_joblib, load_json
from backend.common.config import load_settings
from backend.common.label_governance import materialize_label_governance
from backend.common.sar_release_refs import load_reference_bundle, parse_storage_ref, reference_item_to_scene
from backend.common.sar_artifacts import persist_sar_artifacts
from backend.common.storage_io import storage_download_bytes, storage_upload_bytes
from backend.common.supabase_io import has_supabase_credentials, rest_insert, rest_upsert

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


def load_scene_stack(scene: dict[str, Any]) -> np.ndarray:
    if scene.get('channels') is not None:
        return _normalize_stack(scene['channels'])
    if scene.get('vv') is not None and scene.get('vh') is not None:
        return _normalize_stack(np.stack([scene['vv'], scene['vh']], axis=0))

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
    state_dict = _extract_state_dict(torch.load(model_path, map_location=device))
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


def predict_scene_probability_mask(loaded_model: LoadedUnetModel, scene: dict[str, Any], *, device: str) -> np.ndarray:
    if loaded_model.model_family == 'swinunet_tiny_diff':
        pre_stack, post_stack = load_bitemporal_scene_inputs(scene)
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
                return np.asarray(dataset.read(1), dtype=np.float32)
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
        predictions.append(_load_mask_array(scene['prediction_mask']) >= SAR_UNET_SEGMENTATION_THRESHOLD)
        truths.append(_load_mask_array(scene['truth_mask']) >= SAR_UNET_SEGMENTATION_THRESHOLD)
        if scene.get('baseline_mask') is not None:
            baselines.append(_load_mask_array(scene['baseline_mask']) >= SAR_UNET_SEGMENTATION_THRESHOLD)

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
    for scene in scenes:
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
            continue
        detections.append(detection)
        records.append(build_shadow_event_record(detection, hazard_type=hazard_type, promoted=promoted))

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
    return {path.name for path in root.iterdir() if path.is_dir()}


def _discover_new_artifact_dir(root: Path, before: set[str]) -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(path for path in root.iterdir() if path.is_dir() and path.name not in before)
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
        'HAZARD_TYPE': str(request.get('hazard_type') or env.get('HAZARD_TYPE') or 'avalanche'),
        'MTS_RUNTIME_PROVIDER': 'modal',
        'TRAIN_MTS_LSTM_HEAD': 'true',
        'USE_MTS_LSTM_HEAD': 'true',
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
    if artifact_dir is None:
        try:
            artifact_dir = latest_artifact_dir(artifact_root)
        except Exception:
            artifact_dir = None
    metrics, lstm_head_meta = _load_training_summary(artifact_dir)
    report = {
        'status': 'ok' if completed.returncode == 0 else ('completed_with_gate_failure' if metrics else 'failed'),
        'request_type': str(request.get('request_type') or 'train_mtslstm'),
        'runtime_provider': 'modal',
        'shadow_mode': _flag_from_payload(request.get('shadow_mode'), True),
        'promotion_rule': str(request.get('promotion_rule') or 'strict_pss_gt_rf_and_brier_lte_rf'),
        'model_artifact_ref': str((artifact_dir / 'model.joblib')) if artifact_dir and (artifact_dir / 'model.joblib').exists() else None,
        'artifact_dir': str(artifact_dir) if artifact_dir else None,
        'dataset_snapshot_id': (
            lstm_head_meta.get('dataset_snapshot_id')
            or metrics.get('dataset_snapshot_id')
            or request.get('dataset_snapshot_id')
        ),
        'lstm_pss': lstm_head_meta.get('pss_holdout'),
        'rf_pss': lstm_head_meta.get('rf_pss_holdout'),
        'lstm_brier': lstm_head_meta.get('brier_score'),
        'rf_brier': lstm_head_meta.get('rf_brier_score'),
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
    env = os.environ.copy()
    env.update({
        'ARTIFACT_ROOT': str(artifact_root),
        'HAZARD_TYPE': str(request.get('hazard_type') or env.get('HAZARD_TYPE') or 'avalanche'),
        'FORECAST_HOURS': str(int(request.get('forecast_hours') or env.get('FORECAST_HOURS') or '72')),
        'GRID_SIZE': str(int(request.get('grid_size') or env.get('GRID_SIZE') or '20')),
    })
    completed = _run_python_module('backend.daily_inference', env=env)
    try:
        artifact_dir = latest_artifact_dir(artifact_root)
    except Exception:
        artifact_dir = None
    inference_manifest = {}
    lstm_head_meta = {}
    if artifact_dir is not None:
        manifest_path = artifact_dir / 'inference_manifest.json'
        if manifest_path.exists():
            inference_manifest = load_json(manifest_path)
        metrics_path = artifact_dir / 'training_metrics.json'
        if metrics_path.exists():
            training_metrics = load_json(metrics_path)
            candidate = training_metrics.get('lstm_head_meta') if isinstance(training_metrics, dict) else {}
            lstm_head_meta = candidate if isinstance(candidate, dict) else {}
    report = {
        'status': 'ok' if completed.returncode == 0 else 'failed',
        'request_type': str(request.get('request_type') or 'infer_mtslstm'),
        'artifact_dir': str(artifact_dir) if artifact_dir else None,
        'forecast_hours': int(request.get('forecast_hours') or env.get('FORECAST_HOURS') or '72'),
        'regions_written': inference_manifest.get('regions_written'),
        'completed_at': inference_manifest.get('completed_at'),
        'promotion_gate_passed': bool(lstm_head_meta.get('promotion_gate_passed')),
        'shadow_mode_active': not bool(lstm_head_meta.get('promotion_gate_passed')),
        'dataset_snapshot_id': lstm_head_meta.get('dataset_snapshot_id'),
        'stdout_tail': _tail_lines(completed.stdout),
        'stderr_tail': _tail_lines(completed.stderr),
        'subprocess_returncode': completed.returncode,
    }
    if artifact_dir is not None:
        dump_json(artifact_dir / 'infer_mtslstm_manifest.json', report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = load_settings()
    model_path_env = os.environ.get('SAR_UNET_MODEL_PATH')
    parser = argparse.ArgumentParser(description='Shadow-mode SAR U-Net segmentation worker')
    parser.add_argument('--mode', choices=['sar-segment', 'evaluate-release', 'train-mtslstm', 'infer-mtslstm'], default=os.environ.get('SAR_WORKER_MODE', 'sar-segment'))
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

    persist_events = not dry_run
    if isinstance(reference_set_key, str) and reference_set_key.strip():
        persist_events = _flag_from_payload(manifest.get('persist_events'), False) and not dry_run

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
