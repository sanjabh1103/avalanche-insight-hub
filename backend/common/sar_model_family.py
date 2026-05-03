from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    import segmentation_models_pytorch as smp
except Exception:  # pragma: no cover - optional dependency
    smp = None


SUPPORTED_SAR_MODEL_FAMILIES = {'resnet34_unet', 'swinunet_tiny_diff'}


def normalize_model_family(model_family: str | None) -> str:
    resolved = str(model_family or 'resnet34_unet').strip() or 'resnet34_unet'
    if resolved not in SUPPORTED_SAR_MODEL_FAMILIES:
        raise ValueError(
            f'unsupported SAR_UNET_MODEL_FAMILY "{resolved}"; '
            f'expected one of: {", ".join(sorted(SUPPORTED_SAR_MODEL_FAMILIES))}',
        )
    return resolved


def build_resnet34_unet_model() -> Any:
    if smp is None:
        raise RuntimeError('segmentation_models_pytorch is required for SAR model family resnet34_unet')
    return smp.Unet(
        encoder_name='resnet34',
        encoder_weights=None,
        in_channels=2,
        classes=1,
        activation=None,
    )


def build_swinunet_tiny_diff_model(*, image_size: int) -> Any:
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


def build_model_architecture(
    model_family: str | None,
    *,
    image_size: int | None = None,
) -> Any:
    resolved_family = normalize_model_family(model_family)
    if resolved_family == 'swinunet_tiny_diff':
        if image_size is None:
            raise ValueError('swinunet_tiny_diff requires image_size during model construction')
        return build_swinunet_tiny_diff_model(image_size=image_size)
    return build_resnet34_unet_model()
