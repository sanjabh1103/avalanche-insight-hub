from __future__ import annotations

import os
from typing import Any

try:  # pragma: no cover - optional dependency
    import segmentation_models_pytorch as smp
except Exception:  # pragma: no cover - optional dependency
    smp = None


SUPPORTED_SAR_MODEL_FAMILIES = {'resnet34_unet', 'swinunet_tiny_diff'}

# F3: mSAFE 6-channel FCNN support. Default 2 for backward compatibility.
SAR_DEFAULT_INPUT_CHANNELS = int(os.getenv('SAR_INPUT_CHANNELS', '2'))
SAR_SUPPORTED_CHANNEL_COUNTS = {2, 6}


def normalize_model_family(model_family: str | None) -> str:
    resolved = str(model_family or 'resnet34_unet').strip() or 'resnet34_unet'
    if resolved not in SUPPORTED_SAR_MODEL_FAMILIES:
        raise ValueError(
            f'unsupported SAR_UNET_MODEL_FAMILY "{resolved}"; '
            f'expected one of: {", ".join(sorted(SUPPORTED_SAR_MODEL_FAMILIES))}',
        )
    return resolved


def build_resnet34_unet_model(*, in_channels: int = SAR_DEFAULT_INPUT_CHANNELS) -> Any:
    if in_channels not in SAR_SUPPORTED_CHANNEL_COUNTS:
        raise ValueError(f'Unsupported in_channels={in_channels}; expected one of {SAR_SUPPORTED_CHANNEL_COUNTS}')
    if smp is None:
        raise RuntimeError('segmentation_models_pytorch is required for SAR model family resnet34_unet')
    return smp.Unet(
        encoder_name='resnet34',
        encoder_weights=None,
        in_channels=in_channels,
        classes=1,
        activation=None,
    )


def build_swinunet_tiny_diff_model(
    *,
    image_size: int,
    sar_in_channels: int = SAR_DEFAULT_INPUT_CHANNELS,
    six_channel: bool | None = None,
) -> Any:
    from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet, require_swin_runtime

    require_swin_runtime()
    if sar_in_channels not in SAR_SUPPORTED_CHANNEL_COUNTS:
        raise ValueError(f'Unsupported sar_in_channels={sar_in_channels}; expected one of {SAR_SUPPORTED_CHANNEL_COUNTS}')
    # Auto-detect six_channel mode when sar_in_channels == 6 and not explicitly set
    if six_channel is None:
        six_channel = sar_in_channels == 6
    return ChangeDetectionSwinUNet(
        img_size=image_size,
        sar_in_channels=sar_in_channels,
        aux_in_channels=4,
        num_classes=1,
        use_aux=False,
        model_size='tiny',
        fusion_type='diff',
        six_channel=six_channel,
    )


def build_model_architecture(
    model_family: str | None,
    *,
    image_size: int | None = None,
    in_channels: int | None = None,
) -> Any:
    resolved_family = normalize_model_family(model_family)
    resolved_channels = in_channels if in_channels is not None else SAR_DEFAULT_INPUT_CHANNELS
    if resolved_family == 'swinunet_tiny_diff':
        if image_size is None:
            raise ValueError('swinunet_tiny_diff requires image_size during model construction')
        return build_swinunet_tiny_diff_model(image_size=image_size, sar_in_channels=resolved_channels)
    return build_resnet34_unet_model(in_channels=resolved_channels)
