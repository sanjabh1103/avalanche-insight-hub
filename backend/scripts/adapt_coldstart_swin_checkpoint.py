from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import timm
import torch
import torch.nn.functional as F

from backend.common.regions import repo_root
from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet, DEFAULT_TIMM_MODEL
from backend.sar_unet_worker import build_unet_model
from backend.scripts.fetch_sota_sar_weights import update_env_file


DEFAULT_OUTPUT = Path('backend/data/models/swin_transformer_v2_tiny_coldstart_v1.pt')
DEFAULT_ENV_FILE = Path('.env')
DEFAULT_ENV_MODEL_PATH = '/artifacts/models/swin_transformer_v2_tiny_coldstart_v1.pt'
DEFAULT_MODEL_FAMILY = 'swinunet_tiny_diff'
DEFAULT_MODEL_VERSION = 'swin_transformer_v2_tiny_coldstart_v1'
DEFAULT_IMAGE_SIZE = 128
DEFAULT_SOURCE_PATCH_SIZE = 4
DEFAULT_TARGET_PATCH_SIZE = 2
DEFAULT_OUT_INDICES = (0, 1, 2)


def _resolve_output_path(output: Path) -> Path:
    expanded = output.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (repo_root() / expanded).resolve()


def adapt_patch_embed_weight(
    weight: torch.Tensor,
    *,
    target_in_channels: int = 2,
    target_patch_size: int = DEFAULT_TARGET_PATCH_SIZE,
) -> torch.Tensor:
    if weight.ndim != 4:
        raise ValueError('patch embedding weight must be 4D [out_channels, in_channels, height, width]')
    reduced = weight.detach().to(dtype=torch.float32).mean(dim=1, keepdim=True)
    resized = F.interpolate(
        reduced,
        size=(target_patch_size, target_patch_size),
        mode='bilinear',
        align_corners=False,
    )
    expanded = resized.repeat(1, target_in_channels, 1, 1) / float(target_in_channels)
    return expanded.to(dtype=weight.dtype)


def build_coldstart_state_dict(
    *,
    source_state_dict: dict[str, torch.Tensor],
    target_state_dict: dict[str, torch.Tensor],
) -> dict[str, Any]:
    adapted_state_dict: dict[str, torch.Tensor] = {}
    matched_source_keys: list[str] = []
    dropped_source_keys: list[str] = []

    for source_key, source_value in source_state_dict.items():
        if source_key.startswith('head.'):
            dropped_source_keys.append(source_key)
            continue

        candidate_key = f'sar_encoder.model.{source_key}'
        if candidate_key not in target_state_dict:
            dropped_source_keys.append(source_key)
            continue

        adapted_value = (
            adapt_patch_embed_weight(source_value)
            if source_key == 'patch_embed.proj.weight'
            else source_value.detach().clone()
        )
        target_value = target_state_dict[candidate_key]
        if tuple(adapted_value.shape) != tuple(target_value.shape):
            dropped_source_keys.append(source_key)
            continue

        adapted_state_dict[candidate_key] = adapted_value.detach().cpu().clone()
        matched_source_keys.append(source_key)

    missing_target_keys = [
        key
        for key in target_state_dict
        if key.startswith('sar_encoder.model.') and key not in adapted_state_dict
    ]
    return {
        'state_dict': adapted_state_dict,
        'matched_source_keys': matched_source_keys,
        'dropped_source_keys': dropped_source_keys,
        'missing_target_keys': missing_target_keys,
    }


def adapt_coldstart_swin_checkpoint(
    *,
    output: Path = DEFAULT_OUTPUT,
    env_file: Path = DEFAULT_ENV_FILE,
    env_model_path: str = DEFAULT_ENV_MODEL_PATH,
    model_family: str = DEFAULT_MODEL_FAMILY,
    model_version: str = DEFAULT_MODEL_VERSION,
    image_size: int = DEFAULT_IMAGE_SIZE,
    source_model_name: str = DEFAULT_TIMM_MODEL,
) -> dict[str, Any]:
    resolved_output = _resolve_output_path(output)
    resolved_env_file = env_file.expanduser().resolve()

    source_model = timm.create_model(
        source_model_name,
        pretrained=True,
        features_only=True,
        out_indices=DEFAULT_OUT_INDICES,
        in_chans=3,
        img_size=image_size,
        patch_size=DEFAULT_SOURCE_PATCH_SIZE,
    )
    target_model = ChangeDetectionSwinUNet(
        img_size=image_size,
        sar_in_channels=2,
        aux_in_channels=4,
        num_classes=1,
        use_aux=False,
        model_size='tiny',
        fusion_type='diff',
        encoder_patch_size=DEFAULT_TARGET_PATCH_SIZE,
    )

    adaptation = build_coldstart_state_dict(
        source_state_dict=source_model.state_dict(),
        target_state_dict=target_model.state_dict(),
    )
    adapted_state_dict = adaptation['state_dict']
    if not adapted_state_dict:
        raise RuntimeError('cold-start checkpoint adaptation produced an empty state_dict')

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_payload = {
        'state_dict': adapted_state_dict,
        'metadata': {
            'source_model_name': source_model_name,
            'model_family': model_family,
            'model_version': model_version,
            'image_size': image_size,
            'matched_source_keys_count': len(adaptation['matched_source_keys']),
            'dropped_source_keys_count': len(adaptation['dropped_source_keys']),
            'missing_target_keys_count': len(adaptation['missing_target_keys']),
        },
    }
    torch.save(checkpoint_payload, resolved_output)

    shadow_loaded = build_unet_model(
        resolved_output,
        device='cpu',
        model_family=model_family,
        image_size=image_size,
        promoted=False,
    )

    update_env_file(
        resolved_env_file,
        {
            'SAR_UNET_MODEL_FAMILY': model_family,
            'SAR_UNET_MODEL_VERSION': model_version,
            'SAR_UNET_MODEL_PATH': env_model_path,
        },
    )

    checkpoint_mismatch = dict(shadow_loaded.checkpoint_key_mismatch)
    return {
        'status': 'ok',
        'output_path': str(resolved_output),
        'env_file': str(resolved_env_file),
        'env_updates': {
            'SAR_UNET_MODEL_FAMILY': model_family,
            'SAR_UNET_MODEL_VERSION': model_version,
            'SAR_UNET_MODEL_PATH': env_model_path,
        },
        'source_model_name': source_model_name,
        'matched_source_keys_count': len(adaptation['matched_source_keys']),
        'dropped_source_keys_count': len(adaptation['dropped_source_keys']),
        'missing_target_keys_count': len(adaptation['missing_target_keys']),
        'matched_source_keys_sample': adaptation['matched_source_keys'][:20],
        'dropped_source_keys_sample': adaptation['dropped_source_keys'][:20],
        'shadow_verification': {
            'model_family': shadow_loaded.model_family,
            'checkpoint_key_mismatch': checkpoint_mismatch,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Adapt a timm Swin V2 Tiny backbone into a shadow-only SAR cold-start checkpoint',
    )
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--env-file', type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument('--env-model-path', default=DEFAULT_ENV_MODEL_PATH)
    parser.add_argument('--model-family', default=DEFAULT_MODEL_FAMILY)
    parser.add_argument('--model-version', default=DEFAULT_MODEL_VERSION)
    parser.add_argument('--image-size', type=int, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument('--source-model-name', default=DEFAULT_TIMM_MODEL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = adapt_coldstart_swin_checkpoint(
        output=args.output,
        env_file=args.env_file,
        env_model_path=args.env_model_path,
        model_family=args.model_family,
        model_version=args.model_version,
        image_size=args.image_size,
        source_model_name=args.source_model_name,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
