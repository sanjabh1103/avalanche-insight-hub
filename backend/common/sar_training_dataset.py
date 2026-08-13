from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import numpy as np
import torch
from torch.utils.data import Dataset, Sampler

import requests

from backend.common.avalcd_manifest import (
    AVALCD_PADDING_MODE,
    AVALCD_PATCH_SIZE,
    AVALCD_PATCH_STRIDE,
    _normalize_patch_origins,
    load_avalcd_scene_manifest,
    resolve_manifest_relative_ref,
)
from backend.common.sar_release_refs import parse_storage_ref
from backend.common.storage_io import storage_download_bytes

try:  # pragma: no cover - optional dependency
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
except Exception:  # pragma: no cover - optional dependency
    MemoryFile = None
    from_origin = None


SAR_TRAINING_MANIFEST_VERSION = 'sar_training_manifest_v1'
SAR_TRAINING_ALLOWED_SPLITS = {'train', 'val', 'authoritative_test'}
DEFAULT_POSITIVE_NEGATIVE_RATIO = 1


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


def _ref_suffix(value: str) -> str:
    parsed = urlparse(value)
    candidate = parsed.path if parsed.scheme else value
    return Path(candidate).suffix.lower()


def _load_bytes_from_ref(value: str) -> bytes:
    if _looks_like_http_url(value):
        response = requests.get(value, timeout=300)
        response.raise_for_status()
        return response.content
    if _looks_like_storage_ref(value):
        bucket, object_path = parse_storage_ref(value)
        return storage_download_bytes(bucket=bucket, object_path=object_path)
    path = Path(value).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f'ref not found or unreadable: {value}. '
            'Expected local path, http(s) URL, or Supabase storage ref bucket/path.',
        )
    return path.read_bytes()


def _load_json_from_ref(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raw = str(value)
    payload = _load_bytes_from_ref(raw)
    parsed = json.loads(payload.decode('utf-8'))
    if not isinstance(parsed, dict):
        raise ValueError('SAR training manifest must decode to a JSON object')
    return parsed


def _load_stack_array_from_ref(value: str) -> np.ndarray:
    suffix = _ref_suffix(value)
    payload = _load_bytes_from_ref(value)
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
    raise ValueError(f'unsupported stack_ref format "{suffix}"')


def _load_truth_mask_from_ref(value: str) -> np.ndarray:
    suffix = _ref_suffix(value)
    payload = _load_bytes_from_ref(value)
    if suffix == '.npz':
        loaded = np.load(BytesIO(payload))
        candidate = loaded['mask'] if 'mask' in loaded else loaded[loaded.files[0]]
        return np.asarray(candidate, dtype=np.float32)
    if suffix == '.npy':
        return np.asarray(np.load(BytesIO(payload)), dtype=np.float32)
    if suffix in {'.tif', '.tiff'}:
        if MemoryFile is None:
            raise RuntimeError('rasterio is required to read GeoTIFF truth masks')
        with MemoryFile(payload) as memory_file:
            with memory_file.open() as dataset:
                band = np.asarray(dataset.read(1), dtype=np.float32)
                if band.size and float(np.nanmax(band)) > 1.0:
                    band = band / 255.0
                return band
    raise ValueError(f'unsupported truth_mask_ref format "{suffix}"')


def _normalize_four_channel_stack(stack: Any) -> np.ndarray:
    array = np.asarray(stack, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f'expected a 4-channel AvalCD scene stack, received shape {array.shape}')
    if array.shape[0] != 4 and array.shape[-1] == 4:
        array = np.moveaxis(array, -1, 0)
    if array.shape[0] != 4:
        raise ValueError(f'expected a 4-channel AvalCD scene stack, received shape {array.shape}')
    return np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def _pad_stack_and_mask(
    stack: np.ndarray,
    mask: np.ndarray,
    *,
    patch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    _, height, width = stack.shape
    pad_height = max(0, patch_size - height)
    pad_width = max(0, patch_size - width)
    if not pad_height and not pad_width:
        return stack, mask
    padded_stack = np.pad(
        stack,
        ((0, 0), (0, pad_height), (0, pad_width)),
        mode=AVALCD_PADDING_MODE,
    )
    padded_mask = np.pad(
        mask,
        ((0, pad_height), (0, pad_width)),
        mode='constant',
        constant_values=0,
    )
    return padded_stack, padded_mask


def _write_raster(path: Path, array: np.ndarray) -> None:
    if MemoryFile is None or from_origin is None:
        raise RuntimeError('rasterio is required to materialize SAR training patches')
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(array)
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    count, height, width = array.shape
    dtype = str(array.dtype)
    with path.open('wb') as handle:
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver='GTiff',
                width=width,
                height=height,
                count=count,
                dtype=dtype,
                transform=from_origin(0.0, 0.0, 1.0, 1.0),
            ) as dataset:
                dataset.write(array)
            handle.write(memory_file.read())


def _scene_slug(scene: dict[str, Any]) -> str:
    raw = str(scene.get('scene_id') or scene.get('event_id') or 'scene').strip().lower()
    return ''.join(ch if ch.isalnum() else '_' for ch in raw).strip('_') or 'scene'


def _event_slug(scene: dict[str, Any]) -> str:
    raw = str(scene.get('event_id') or scene.get('scene_id') or 'event').strip().lower()
    return ''.join(ch if ch.isalnum() else '_' for ch in raw).strip('_') or 'event'


def _normalize_scene(raw: dict[str, Any]) -> dict[str, Any]:
    source_dataset = str(raw.get('source_dataset') or '').strip()
    event_id = str(raw.get('event_id') or raw.get('scene_id') or '').strip()
    scene_id = str(raw.get('scene_id') or '').strip()
    region_key = str(raw.get('region_key') or '').strip()
    split = str(raw.get('split') or '').strip().lower()
    stack_ref = str(raw.get('stack_ref') or '').strip()
    truth_mask_ref = str(raw.get('truth_mask_ref') or raw.get('truth_mask') or '').strip()
    if not source_dataset:
        raise ValueError('scene is missing source_dataset')
    if not event_id:
        raise ValueError('scene is missing event_id')
    if not scene_id:
        raise ValueError('scene is missing scene_id')
    if not region_key:
        raise ValueError(f'scene "{scene_id}" is missing region_key')
    if split not in SAR_TRAINING_ALLOWED_SPLITS:
        raise ValueError(
            f'scene "{scene_id}" has unsupported split "{split}"; '
            f'expected one of: {", ".join(sorted(SAR_TRAINING_ALLOWED_SPLITS))}',
        )
    if not stack_ref:
        raise ValueError(f'scene "{scene_id}" is missing stack_ref')
    if not truth_mask_ref:
        raise ValueError(f'scene "{scene_id}" is missing truth_mask_ref')
    authoritative = bool(raw.get('authoritative', False))
    reference_set_key = str(raw.get('reference_set_key') or '').strip() or None
    if reference_set_key == 'snowslide-heldout-v1' and split != 'authoritative_test':
        raise ValueError(
            f'scene "{scene_id}" belongs to snowslide-heldout-v1 and must use split=authoritative_test',
        )
    if authoritative and split != 'authoritative_test':
        raise ValueError(f'authoritative scene "{scene_id}" must use split=authoritative_test')
    return {
        'source_dataset': source_dataset,
        'event_id': event_id,
        'scene_id': scene_id,
        'region_key': region_key,
        'split': split,
        'stack_ref': stack_ref,
        'truth_mask_ref': truth_mask_ref,
        'reference_set_key': reference_set_key,
        'authoritative': authoritative,
        'metadata': raw.get('metadata') if isinstance(raw.get('metadata'), dict) else {},
    }


def load_sar_training_manifest(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    manifest = _load_json_from_ref(value)
    version = str(manifest.get('version') or SAR_TRAINING_MANIFEST_VERSION).strip()
    if version != SAR_TRAINING_MANIFEST_VERSION:
        raise ValueError(
            f'unsupported SAR training manifest version "{version}"; expected {SAR_TRAINING_MANIFEST_VERSION}',
        )
    scenes = manifest.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('SAR training manifest must include a non-empty scenes[] list')
    normalized_scenes = [_normalize_scene(scene) for scene in scenes if isinstance(scene, dict)]
    if len(normalized_scenes) != len(scenes):
        raise ValueError('SAR training manifest scenes[] entries must be objects')
    return {
        'version': SAR_TRAINING_MANIFEST_VERSION,
        'dataset_version': str(manifest.get('dataset_version') or 'sar-training-v1').strip(),
        'scenes': normalized_scenes,
    }


@dataclass(frozen=True)
class SarPatchRecord:
    split: str
    event_id: str
    scene_id: str
    source_dataset: str
    region_key: str
    patch_id: str
    pre_path: str
    post_path: str
    mask_path: str
    positive_pixels: int
    total_pixels: int
    aux_path: str | None = None  # F3: optional 4-band aux raster (coherence, slope, PAR, mask)

    def as_dict(self) -> dict[str, Any]:
        result = {
            'split': self.split,
            'event_id': self.event_id,
            'scene_id': self.scene_id,
            'source_dataset': self.source_dataset,
            'region_key': self.region_key,
            'patch_id': self.patch_id,
            'pre_path': self.pre_path,
            'post_path': self.post_path,
            'mask_path': self.mask_path,
            'positive_pixels': self.positive_pixels,
            'total_pixels': self.total_pixels,
        }
        if self.aux_path is not None:
            result['aux_path'] = self.aux_path
        return result


def _iter_manifest_patches(
    scene: dict[str, Any],
    *,
    patch_size: int,
    stride: int,
) -> Iterator[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    manifest_ref = str(scene['stack_ref'])
    manifest = load_avalcd_scene_manifest(_load_json_from_ref(manifest_ref))
    manifest_patch_size = int(manifest.get('patch_size') or patch_size)
    manifest_stride = int(manifest.get('stride') or stride)
    if manifest_patch_size != patch_size or manifest_stride != stride:
        raise ValueError(
            f'scene "{scene["scene_id"]}" patch geometry mismatch: '
            f'manifest patch_size/stride={manifest_patch_size}/{manifest_stride}, '
            f'expected {patch_size}/{stride}',
        )
    truth_mask = _load_truth_mask_from_ref(str(scene['truth_mask_ref']))
    for patch in manifest['patches']:
        patch_ref = resolve_manifest_relative_ref(manifest_ref, str(patch['asset_ref']))
        stack = _normalize_four_channel_stack(_load_stack_array_from_ref(patch_ref))
        row = int(patch['row'])
        col = int(patch['col'])
        row0, col0, row1, col1 = [int(value) for value in patch['valid_window']]
        mask_patch = np.zeros((patch_size, patch_size), dtype=np.float32)
        truth_crop = truth_mask[row + row0:row + row1, col + col0:col + col1]
        if truth_crop.shape != (row1 - row0, col1 - col0):
            raise ValueError(
                f'scene "{scene["scene_id"]}" truth mask does not align with manifest patch '
                f'row={row} col={col} window={patch["valid_window"]}',
            )
        mask_patch[row0:row1, col0:col1] = truth_crop
        patch_id = f'{_scene_slug(scene)}__r{row:06d}_c{col:06d}'
        yield patch_id, stack[:2].astype(np.float32), stack[2:].astype(np.float32), mask_patch


def _iter_full_stack_patches(
    scene: dict[str, Any],
    *,
    patch_size: int,
    stride: int,
) -> Iterator[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    stack = _normalize_four_channel_stack(_load_stack_array_from_ref(str(scene['stack_ref'])))
    truth_mask = _load_truth_mask_from_ref(str(scene['truth_mask_ref']))
    if truth_mask.shape != tuple(stack.shape[1:]):
        raise ValueError(
            f'scene "{scene["scene_id"]}" truth mask shape {truth_mask.shape} '
            f'does not align with stack shape {stack.shape[1:]}',
        )
    padded_stack, padded_mask = _pad_stack_and_mask(stack, truth_mask, patch_size=patch_size)
    _, height, width = stack.shape
    row_origins = _normalize_patch_origins(height, patch_size=patch_size, stride=stride)
    col_origins = _normalize_patch_origins(width, patch_size=patch_size, stride=stride)
    for row in row_origins:
        for col in col_origins:
            valid_height = min(patch_size, height - row)
            valid_width = min(patch_size, width - col)
            patch_id = f'{_scene_slug(scene)}__r{row:06d}_c{col:06d}'
            yield (
                patch_id,
                padded_stack[:2, row:row + patch_size, col:col + patch_size].astype(np.float32),
                padded_stack[2:, row:row + patch_size, col:col + patch_size].astype(np.float32),
                padded_mask[row:row + patch_size, col:col + patch_size].astype(np.float32),
            )


def _iter_scene_patches(
    scene: dict[str, Any],
    *,
    patch_size: int,
    stride: int,
) -> Iterator[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    stack_ref = str(scene['stack_ref'])
    if stack_ref.lower().endswith('.json'):
        yield from _iter_manifest_patches(scene, patch_size=patch_size, stride=stride)
        return
    yield from _iter_full_stack_patches(scene, patch_size=patch_size, stride=stride)


def materialize_sar_training_dataset(
    *,
    manifest_source: str | Path | dict[str, Any],
    output_root: Path,
    patch_size: int = AVALCD_PATCH_SIZE,
    stride: int = AVALCD_PATCH_STRIDE,
) -> dict[str, Any]:
    manifest = load_sar_training_manifest(manifest_source)
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    patch_root = output_root / str(patch_size)
    patch_root.mkdir(parents=True, exist_ok=True)

    patch_records: list[SarPatchRecord] = []
    split_scene_counts = {split: 0 for split in SAR_TRAINING_ALLOWED_SPLITS}
    split_patch_counts = {split: 0 for split in SAR_TRAINING_ALLOWED_SPLITS}
    split_positive_pixels = {split: 0 for split in SAR_TRAINING_ALLOWED_SPLITS}
    split_total_pixels = {split: 0 for split in SAR_TRAINING_ALLOWED_SPLITS}
    source_counts: dict[str, int] = {}

    for scene in manifest['scenes']:
        split = str(scene['split'])
        split_scene_counts[split] += 1
        source_counts[scene['source_dataset']] = source_counts.get(scene['source_dataset'], 0) + 1
        if split == 'authoritative_test':
            continue
        event_dir = patch_root / split / _event_slug(scene)
        for patch_id, pre_patch, post_patch, mask_patch in _iter_scene_patches(
            scene,
            patch_size=patch_size,
            stride=stride,
        ):
            patch_dir = event_dir / patch_id
            _write_raster(patch_dir / 'pre.tif', pre_patch.astype(np.float32))
            _write_raster(patch_dir / 'post.tif', post_patch.astype(np.float32))
            _write_raster(patch_dir / 'mask.tif', (mask_patch >= 0.5).astype(np.uint8))
            positive_pixels = int(np.sum(mask_patch >= 0.5))
            total_pixels = int(mask_patch.size)
            patch_records.append(SarPatchRecord(
                split=split,
                event_id=str(scene['event_id']),
                scene_id=str(scene['scene_id']),
                source_dataset=str(scene['source_dataset']),
                region_key=str(scene['region_key']),
                patch_id=patch_id,
                pre_path=str((patch_dir / 'pre.tif').resolve()),
                post_path=str((patch_dir / 'post.tif').resolve()),
                mask_path=str((patch_dir / 'mask.tif').resolve()),
                positive_pixels=positive_pixels,
                total_pixels=total_pixels,
            ))
            split_patch_counts[split] += 1
            split_positive_pixels[split] += positive_pixels
            split_total_pixels[split] += total_pixels

    normalized_manifest_path = output_root / 'sar_training_manifest.json'
    patch_index_path = output_root / 'patch_index.json'
    audit_path = output_root / 'audit.json'
    normalized_manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    patch_index_payload = [record.as_dict() for record in patch_records]
    patch_index_path.write_text(json.dumps(patch_index_payload, indent=2, sort_keys=True), encoding='utf-8')

    audit = {
        'status': 'ok',
        'version': SAR_TRAINING_MANIFEST_VERSION,
        'dataset_version': manifest['dataset_version'],
        'patch_size': patch_size,
        'stride': stride,
        'patch_root': str(patch_root),
        'normalized_manifest_path': str(normalized_manifest_path),
        'patch_index_path': str(patch_index_path),
        'split_scene_counts': split_scene_counts,
        'split_patch_counts': split_patch_counts,
        'split_positive_pixel_rates': {
            split: (
                float(split_positive_pixels[split]) / float(split_total_pixels[split])
                if split_total_pixels[split] else 0.0
            )
            for split in SAR_TRAINING_ALLOWED_SPLITS
        },
        'train_events': sorted({record.event_id for record in patch_records if record.split == 'train'}),
        'val_events': sorted({record.event_id for record in patch_records if record.split == 'val'}),
        'authoritative_test_scene_ids': sorted({
            str(scene['scene_id'])
            for scene in manifest['scenes']
            if str(scene['split']) == 'authoritative_test'
        }),
        'source_dataset_scene_counts': source_counts,
    }
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding='utf-8')
    return audit


class SarPatchDataset(Dataset[dict[str, Any]]):
    def __init__(
        self,
        dataset_root: Path,
        *,
        split: str,
        normalization: dict[str, torch.Tensor] | None = None,
        augment: bool = False,
        six_channel: bool = False,
    ) -> None:
        self.dataset_root = dataset_root.expanduser().resolve()
        self.split = split
        self.augment = augment
        self.six_channel = six_channel
        patch_index = json.loads((self.dataset_root / 'patch_index.json').read_text(encoding='utf-8'))
        self.records = [record for record in patch_index if str(record.get('split')) == split]
        if not self.records:
            raise ValueError(f'no patch records found for split="{split}" under {self.dataset_root}')
        self.normalization = normalization

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        pre = torch.from_numpy(self._read_raster(record['pre_path'])).float()
        post = torch.from_numpy(self._read_raster(record['post_path'])).float()
        mask = torch.from_numpy(self._read_raster(record['mask_path'])[0]).float().unsqueeze(0)

        if self.six_channel:
            # F3: Compute 6-channel mSAFE tensor from pre/post + optional aux raster
            vv_diff = post[0] - pre[0]
            vh_diff = post[1] - pre[1]
            vv_vh_prod = (vv_diff ** 2) * (vh_diff ** 2)

            aux_path = record.get('aux_path')
            if aux_path and Path(aux_path).exists():
                aux = torch.from_numpy(self._read_raster(aux_path)).float()
                coherence = aux[0]
                slope = aux[1]
                par = aux[2]
            else:
                # Synthetic fallback when aux raster not available
                coherence = torch.zeros_like(vv_diff)
                slope = torch.zeros_like(vv_diff)
                par = torch.zeros_like(vv_diff)

            input_tensor = torch.stack([vv_diff, vh_diff, vv_vh_prod, coherence, slope, par], dim=0)

            if self.augment:
                if torch.rand(1).item() < 0.5:
                    input_tensor = torch.flip(input_tensor, dims=[2])
                    mask = torch.flip(mask, dims=[2])
                rotations = int(torch.randint(low=0, high=4, size=(1,)).item())
                if rotations:
                    input_tensor = torch.rot90(input_tensor, rotations, dims=(1, 2))
                    mask = torch.rot90(mask, rotations, dims=(1, 2))

            if self.normalization is not None:
                mean = self.normalization['img_mean'].view(-1, 1, 1)
                std = self.normalization['img_std'].view(-1, 1, 1)
                input_tensor = (input_tensor - mean) / std

            return {
                'input': input_tensor,
                'mask': mask,
                'event_id': str(record['event_id']),
                'scene_id': str(record['scene_id']),
                'region_key': str(record.get('region_key') or 'unknown'),
                'source_dataset': str(record.get('source_dataset') or 'unknown'),
                'patch_id': str(record['patch_id']),
                'positive_pixels': int(record.get('positive_pixels') or 0),
                'total_pixels': int(record.get('total_pixels') or mask.numel()),
            }

        # Original 2-channel bi-temporal path
        if self.augment:
            if torch.rand(1).item() < 0.5:
                pre = torch.flip(pre, dims=[2])
                post = torch.flip(post, dims=[2])
                mask = torch.flip(mask, dims=[2])
            rotations = int(torch.randint(low=0, high=4, size=(1,)).item())
            if rotations:
                pre = torch.rot90(pre, rotations, dims=(1, 2))
                post = torch.rot90(post, rotations, dims=(1, 2))
                mask = torch.rot90(mask, rotations, dims=(1, 2))
        if self.normalization is not None:
            mean = self.normalization['img_mean'].view(-1, 1, 1)
            std = self.normalization['img_std'].view(-1, 1, 1)
            pre = (pre - mean) / std
            post = (post - mean) / std
        return {
            'pre': pre,
            'post': post,
            'mask': mask,
            'event_id': str(record['event_id']),
            'scene_id': str(record['scene_id']),
            'region_key': str(record.get('region_key') or 'unknown'),
            'source_dataset': str(record.get('source_dataset') or 'unknown'),
            'patch_id': str(record['patch_id']),
            'positive_pixels': int(record.get('positive_pixels') or 0),
            'total_pixels': int(record.get('total_pixels') or mask.numel()),
        }

    @staticmethod
    def _read_raster(path: str) -> np.ndarray:
        payload = Path(path).read_bytes()
        if MemoryFile is None:
            raise RuntimeError('rasterio is required to read SAR patch rasters')
        with MemoryFile(payload) as memory_file:
            with memory_file.open() as dataset:
                return np.asarray(dataset.read(), dtype=np.float32)


def compute_sar_normalization(dataset: SarPatchDataset) -> dict[str, torch.Tensor]:
    # F3: Detect channel count from data to support both 2-channel and 6-channel modes
    first_pre = torch.from_numpy(dataset._read_raster(dataset.records[0]['pre_path'])).double()
    first_post = torch.from_numpy(dataset._read_raster(dataset.records[0]['post_path'])).double()
    base_channels = first_pre.shape[0]

    if dataset.six_channel:
        # 6-channel mode: compute normalization over all 6 channels of the constructed tensor
        num_channels = 6
        running_sum = torch.zeros(num_channels, dtype=torch.float64)
        running_sq = torch.zeros(num_channels, dtype=torch.float64)
        running_count = torch.zeros(num_channels, dtype=torch.float64)
        for record in dataset.records:
            pre = torch.from_numpy(dataset._read_raster(record['pre_path'])).double()
            post = torch.from_numpy(dataset._read_raster(record['post_path'])).double()
            vv_diff = post[0] - pre[0]
            vh_diff = post[1] - pre[1]
            vv_vh_prod = (vv_diff ** 2) * (vh_diff ** 2)

            aux_path = record.get('aux_path')
            if aux_path and Path(aux_path).exists():
                aux = torch.from_numpy(dataset._read_raster(aux_path)).double()
                coherence = aux[0]
                slope = aux[1]
                par = aux[2]
            else:
                coherence = torch.zeros_like(vv_diff)
                slope = torch.zeros_like(vv_diff)
                par = torch.zeros_like(vv_diff)

            channels = [vv_diff, vh_diff, vv_vh_prod, coherence, slope, par]
            for ch_idx, ch_data in enumerate(channels):
                finite = torch.isfinite(ch_data)
                values = ch_data[finite]
                if values.numel() == 0:
                    continue
                running_sum[ch_idx] += values.sum()
                running_sq[ch_idx] += torch.square(values).sum()
                running_count[ch_idx] += values.numel()
    else:
        # Original 2-channel normalization
        num_channels = base_channels
        running_sum = torch.zeros(num_channels, dtype=torch.float64)
        running_sq = torch.zeros(num_channels, dtype=torch.float64)
        running_count = torch.zeros(num_channels, dtype=torch.float64)
        for record in dataset.records:
            pre = torch.from_numpy(dataset._read_raster(record['pre_path'])).double()
            post = torch.from_numpy(dataset._read_raster(record['post_path'])).double()
            for channel in range(num_channels):
                stacked = torch.cat([pre[channel].flatten(), post[channel].flatten()])
                finite = torch.isfinite(stacked)
                values = stacked[finite]
                if values.numel() == 0:
                    continue
                running_sum[channel] += values.sum()
                running_sq[channel] += torch.square(values).sum()
                running_count[channel] += values.numel()
    img_mean = torch.where(running_count > 0, running_sum / running_count, torch.zeros_like(running_sum)).float()
    img_var = torch.where(
        running_count > 0,
        (running_sq / running_count) - torch.square(img_mean.double()),
        torch.ones_like(running_count),
    ).float()
    img_std = torch.sqrt(torch.clamp(img_var, min=1e-6))
    return {
        'img_mean': img_mean,
        'img_std': img_std,
    }


class BalancedPositivePatchSampler(Sampler[int]):
    def __init__(
        self,
        dataset: SarPatchDataset,
        *,
        negative_ratio: int = DEFAULT_POSITIVE_NEGATIVE_RATIO,
        seed: int = 42,
    ) -> None:
        self.dataset = dataset
        self.negative_ratio = max(1, int(negative_ratio))
        self.seed = int(seed)
        self.positive_indices = [
            index for index, record in enumerate(self.dataset.records)
            if int(record.get('positive_pixels') or 0) > 0
        ]
        self.negative_indices = [
            index for index, record in enumerate(self.dataset.records)
            if int(record.get('positive_pixels') or 0) <= 0
        ]
        if not self.positive_indices:
            raise ValueError('balanced SAR training sampler requires at least one positive patch')
        if not self.negative_indices:
            raise ValueError('balanced SAR training sampler requires at least one negative patch')
        self.samples_per_epoch = len(self.positive_indices) * (1 + self.negative_ratio)

    def __iter__(self) -> Iterator[int]:
        generator = torch.Generator()
        generator.manual_seed(self.seed)
        positive = torch.randint(
            low=0,
            high=len(self.positive_indices),
            size=(len(self.positive_indices),),
            generator=generator,
        )
        negatives = torch.randint(
            low=0,
            high=len(self.negative_indices),
            size=(len(self.positive_indices) * self.negative_ratio,),
            generator=generator,
        )
        indices = [self.positive_indices[idx] for idx in positive.tolist()]
        indices.extend(self.negative_indices[idx] for idx in negatives.tolist())
        permutation = torch.randperm(len(indices), generator=generator).tolist()
        for position in permutation:
            yield indices[position]

    def __len__(self) -> int:
        return self.samples_per_epoch
