"""Landslide U-Net model architecture.

Uses segmentation-models-pytorch for a U-Net with ResNet encoder,
configured for 14-channel Landslide4Sense input (12 S2 bands + slope + DEM).
"""

import segmentation_models_pytorch as smp


def get_model(
    encoder_name: str = "resnet34",
    in_channels: int = 14,
    encoder_weights: str | None = None,
) -> smp.Unet:
    """Create a U-Net segmentation model for landslide detection.

    Args:
        encoder_name: Encoder backbone (e.g., "resnet34", "resnet50").
        in_channels: Number of input channels (14 for Landslide4Sense).
        encoder_weights: Pretrained weights for encoder. None for random init,
            "imagenet" for ImageNet weights adapted to in_channels by SMP.

    Returns:
        U-Net model with raw logit output (no activation).
    """
    return smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=encoder_weights,
        in_channels=in_channels,
        classes=1,
        activation=None,
    )
