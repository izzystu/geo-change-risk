"""Evaluation metrics and visualization for landslide detection.

Computes IoU, F1, precision, recall for binary segmentation predictions.
"""

import numpy as np


def compute_metrics(
    predictions: np.ndarray,
    targets: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Compute segmentation metrics for binary predictions.

    Args:
        predictions: Probability predictions, shape (N, 1, H, W).
        targets: Binary ground truth masks, shape (N, 1, H, W).
        threshold: Probability threshold for binarization.

    Returns:
        Dict with iou, f1, precision, recall.
    """
    pred_binary = (predictions > threshold).astype(np.float32)

    tp = (pred_binary * targets).sum()
    fp = (pred_binary * (1 - targets)).sum()
    fn = ((1 - pred_binary) * targets).sum()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0

    return {
        "iou": float(iou),
        "f1": float(f1),
        "precision": float(precision),
        "recall": float(recall),
    }


def save_prediction_visualization(
    image: np.ndarray,
    mask: np.ndarray,
    prediction: np.ndarray,
    output_path: str,
    threshold: float = 0.5,
) -> None:
    """Save a side-by-side visualization of input, ground truth, and prediction.

    Args:
        image: Input image, shape (14, 128, 128). Channels 3,2,1 (B04,B03,B02)
            are used for an RGB composite.
        mask: Ground truth mask, shape (1, 128, 128).
        prediction: Predicted probabilities, shape (1, 128, 128).
        output_path: Path to save the visualization.
        threshold: Probability threshold for binarization.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping visualization")
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # RGB composite from bands B04 (idx 3), B03 (idx 2), B02 (idx 1)
    rgb = np.stack([image[3], image[2], image[1]], axis=-1)
    rgb = np.clip(rgb / rgb.max() if rgb.max() > 0 else rgb, 0, 1)
    axes[0].imshow(rgb)
    axes[0].set_title("RGB (B04, B03, B02)")
    axes[0].axis("off")

    # Ground truth
    axes[1].imshow(mask[0], cmap="Reds", vmin=0, vmax=1)
    axes[1].set_title("Ground Truth")
    axes[1].axis("off")

    # Prediction
    pred_binary = (prediction[0] > threshold).astype(np.float32)
    axes[2].imshow(pred_binary, cmap="Reds", vmin=0, vmax=1)
    axes[2].set_title(f"Prediction (t={threshold})")
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close()
