"""Training loop for landslide U-Net model.

Entry point for training on Landslide4Sense dataset.
Usage:
    python train.py --data-dir /path/to/landslide4sense --output model.pth
"""

import argparse
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

import segmentation_models_pytorch as smp

from data import (
    Landslide4SenseDataset,
    compute_normalization_stats,
    compute_positive_weight,
    get_positive_sampler,
    get_train_transform,
)
from evaluate import compute_metrics
from model import get_model


def train(args: argparse.Namespace) -> None:
    """Run the full training loop."""
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    # Create datasets
    print("Loading datasets...")
    train_dataset = Landslide4SenseDataset(
        args.data_dir, split="train", transform=get_train_transform(),
    )
    val_dataset = Landslide4SenseDataset(args.data_dir, split="val")

    print(f"  Train: {len(train_dataset)} samples")
    print(f"  Val:   {len(val_dataset)} samples")

    # Compute normalization stats from raw training data (no augmentation)
    raw_train = Landslide4SenseDataset(args.data_dir, split="train")
    means, stds = compute_normalization_stats(raw_train)

    # Compute pos_weight for BCE loss, capped to avoid over-predicting
    pos_weight_val = min(compute_positive_weight(raw_train), args.max_pos_weight)

    # Create data loaders with positive oversampling
    sampler = get_positive_sampler(raw_train)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        sampler=sampler,
        num_workers=4,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=True,
    )

    # Create model
    print(f"Creating U-Net with {args.backbone} encoder...")
    model = get_model(
        encoder_name=args.backbone,
        encoder_weights=args.encoder_weights or None,
    )
    model = model.to(device)

    # Loss function
    dice_loss = smp.losses.DiceLoss(mode="binary", from_logits=True)
    if args.loss == "dice-focal":
        pixel_loss = smp.losses.FocalLoss(mode="binary", gamma=2.0)
        loss_name = "Dice + Focal (gamma=2.0)"
    else:
        pixel_loss = smp.losses.SoftBCEWithLogitsLoss(
            pos_weight=torch.tensor([pos_weight_val]).to(device),
        )
        loss_name = f"Dice + BCE (pos_weight={pos_weight_val:.2f})"

    def combined_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return dice_loss(pred, target) + pixel_loss(pred, target)

    # Optimizer and scheduler
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay,
    )
    if args.scheduler == "plateau":
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="max", factor=0.5, patience=5, min_lr=1e-6,
        )
        scheduler_name = "ReduceLROnPlateau (factor=0.5, patience=5)"
    else:
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=20, T_mult=2,
        )
        scheduler_name = "CosineAnnealingWarmRestarts (T_0=20, T_mult=2)"

    # Mixed precision
    use_amp = device == "cuda"
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    # TensorBoard
    writer = SummaryWriter()

    # Training loop
    best_iou = 0.0
    best_f1 = 0.0
    patience_counter = 0

    print(f"\nStarting training for {args.epochs} epochs...")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Learning rate: {args.lr}")
    print(f"  Scheduler: {scheduler_name}")
    print(f"  Loss: {loss_name}")
    print(f"  Encoder weights: {args.encoder_weights or 'None (random init)'}")
    print(f"  Mixed precision: {use_amp}")
    print()

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()

        # Train
        model.train()
        train_loss = 0.0
        train_batches = 0

        for images, masks in train_loader:
            images = _normalize_batch(images, means, stds).to(device)
            masks = masks.to(device)

            optimizer.zero_grad()

            if use_amp:
                with torch.amp.autocast("cuda"):
                    preds = model(images)
                    loss = combined_loss(preds, masks)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                preds = model(images)
                loss = combined_loss(preds, masks)
                loss.backward()
                optimizer.step()

            train_loss += loss.item()
            train_batches += 1

        if args.scheduler == "cosine":
            scheduler.step()
        avg_train_loss = train_loss / max(train_batches, 1)

        # Validate
        model.eval()
        val_loss = 0.0
        val_batches = 0
        all_preds = []
        all_masks = []

        with torch.no_grad():
            for images, masks in val_loader:
                images = _normalize_batch(images, means, stds).to(device)
                masks = masks.to(device)

                if use_amp:
                    with torch.amp.autocast("cuda"):
                        preds = model(images)
                        loss = combined_loss(preds, masks)
                else:
                    preds = model(images)
                    loss = combined_loss(preds, masks)

                val_loss += loss.item()
                val_batches += 1

                probs = torch.sigmoid(preds)
                all_preds.append(probs.cpu().numpy())
                all_masks.append(masks.cpu().numpy())

        avg_val_loss = val_loss / max(val_batches, 1)

        # Compute metrics
        all_preds_np = np.concatenate(all_preds)
        all_masks_np = np.concatenate(all_masks)
        metrics = compute_metrics(all_preds_np, all_masks_np, threshold=0.5)

        elapsed = time.time() - epoch_start
        print(
            f"Epoch {epoch:3d}/{args.epochs} | "
            f"Train Loss: {avg_train_loss:.4f} | "
            f"Val Loss: {avg_val_loss:.4f} | "
            f"IoU: {metrics['iou']:.4f} | "
            f"F1: {metrics['f1']:.4f} | "
            f"Prec: {metrics['precision']:.4f} | "
            f"Rec: {metrics['recall']:.4f} | "
            f"{elapsed:.1f}s"
        )

        # Step plateau scheduler after computing metrics
        if args.scheduler == "plateau":
            scheduler.step(metrics["iou"])

        # TensorBoard logging
        writer.add_scalar("Loss/train", avg_train_loss, epoch)
        writer.add_scalar("Loss/val", avg_val_loss, epoch)
        writer.add_scalar("Metrics/IoU", metrics["iou"], epoch)
        writer.add_scalar("Metrics/F1", metrics["f1"], epoch)
        writer.add_scalar("Metrics/Precision", metrics["precision"], epoch)
        writer.add_scalar("Metrics/Recall", metrics["recall"], epoch)
        writer.add_scalar("LR", optimizer.param_groups[0]["lr"], epoch)

        # Early stopping on val IoU
        if metrics["iou"] > best_iou:
            best_iou = metrics["iou"]
            best_f1 = metrics["f1"]
            patience_counter = 0

            # Save best checkpoint
            checkpoint = {
                "model_state_dict": model.state_dict(),
                "encoder_name": args.backbone,
                "in_channels": 14,
                "model_version": f"landslide-unet-{args.backbone}-ls4s-v1",
                "patch_size": 128,
                "normalization": {
                    "means": means.tolist(),
                    "stds": stds.tolist(),
                },
                "metrics": {
                    "val_iou": best_iou,
                    "val_f1": best_f1,
                    "val_precision": metrics["precision"],
                    "val_recall": metrics["recall"],
                },
                "dataset": "landslide4sense",
                "training_epochs": epoch,
            }
            torch.save(checkpoint, args.output)
            print(f"  -> Saved best model (IoU={best_iou:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                print(f"\nEarly stopping at epoch {epoch} (patience={args.patience})")
                break

    writer.close()
    print(f"\nTraining complete. Best val IoU: {best_iou:.4f}")
    print(f"Model saved to: {args.output}")


def _normalize_batch(
    images: torch.Tensor,
    means: np.ndarray,
    stds: np.ndarray,
) -> torch.Tensor:
    """Normalize a batch of images using per-channel statistics.

    Args:
        images: Tensor of shape (B, 14, H, W).
        means: Per-channel means, shape (14,).
        stds: Per-channel stds, shape (14,).

    Returns:
        Normalized tensor.
    """
    means_t = torch.tensor(means, dtype=torch.float32).view(1, -1, 1, 1)
    stds_t = torch.tensor(stds, dtype=torch.float32).view(1, -1, 1, 1)
    return (images - means_t) / stds_t


def main():
    parser = argparse.ArgumentParser(
        description="Train landslide U-Net on Landslide4Sense dataset"
    )
    parser.add_argument(
        "--data-dir", type=str, required=True,
        help="Path to Landslide4Sense dataset directory",
    )
    parser.add_argument(
        "--output", type=str, default="landslide_model.pth",
        help="Output path for model checkpoint (default: landslide_model.pth)",
    )
    parser.add_argument(
        "--epochs", type=int, default=100,
        help="Maximum training epochs (default: 100)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=16,
        help="Batch size (default: 16)",
    )
    parser.add_argument(
        "--lr", type=float, default=1e-4,
        help="Learning rate (default: 1e-4)",
    )
    parser.add_argument(
        "--weight-decay", type=float, default=1e-4,
        help="Weight decay (default: 1e-4)",
    )
    parser.add_argument(
        "--patience", type=int, default=15,
        help="Early stopping patience (default: 15)",
    )
    parser.add_argument(
        "--device", type=str, default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Device (default: auto)",
    )
    parser.add_argument(
        "--backbone", type=str, default="resnet34",
        help="Encoder backbone (default: resnet34)",
    )
    parser.add_argument(
        "--encoder-weights", type=str, default="",
        help="Pretrained encoder weights, e.g. 'imagenet' (default: none)",
    )
    parser.add_argument(
        "--max-pos-weight", type=float, default=10.0,
        help="Cap for BCE positive class weight (default: 10.0)",
    )
    parser.add_argument(
        "--loss", type=str, default="dice-bce",
        choices=["dice-bce", "dice-focal"],
        help="Loss function: dice-bce (default) or dice-focal",
    )
    parser.add_argument(
        "--scheduler", type=str, default="cosine",
        choices=["cosine", "plateau"],
        help="LR scheduler: cosine (warm restarts) or plateau (reduce on plateau, default: cosine)",
    )

    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
