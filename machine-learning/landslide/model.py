"""Landslide segmentation model architecture.

Uses segmentation-models-pytorch for multi-architecture support,
configured for 14-channel Landslide4Sense input (12 S2 bands + slope + DEM).

Supported architectures:
- unet: U-Net with CNN or transformer encoder (default)
- segformer: SegFormer with native MLP decoder
- upernet: UPerNet with pyramid pooling decoder
"""

import segmentation_models_pytorch as smp


SUPPORTED_ARCHITECTURES = ("unet", "segformer", "upernet")


def get_model(
    arch: str = "unet",
    encoder_name: str = "resnet34",
    in_channels: int = 14,
    encoder_weights: str | None = None,
) -> smp.Unet | smp.Segformer | smp.UPerNet:
    """Create a segmentation model for landslide detection.

    Args:
        arch: Architecture - "unet", "segformer", or "upernet".
        encoder_name: Encoder backbone (e.g., "resnet34", "mit_b2").
        in_channels: Number of input channels (14 for Landslide4Sense).
        encoder_weights: Pretrained weights for encoder. None for random init,
            "imagenet" for ImageNet weights adapted to in_channels by SMP.

    Returns:
        Segmentation model with raw logit output (no activation).
    """
    if arch not in SUPPORTED_ARCHITECTURES:
        raise ValueError(
            f"Unknown architecture '{arch}'. "
            f"Supported: {SUPPORTED_ARCHITECTURES}"
        )

    kwargs = dict(
        encoder_name=encoder_name,
        encoder_weights=encoder_weights,
        in_channels=in_channels,
        classes=1,
    )

    if arch == "segformer":
        return smp.Segformer(**kwargs)
    elif arch == "upernet":
        return smp.UPerNet(**kwargs)
    else:
        return smp.Unet(**kwargs, activation=None)
