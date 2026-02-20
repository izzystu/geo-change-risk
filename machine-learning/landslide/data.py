"""Landslide4Sense dataset class for training.

Wraps the HDF5 files from the Landslide4Sense dataset into a PyTorch Dataset.
Each sample returns a 14-channel image (12 Sentinel-2 bands + slope + DEM)
and a binary segmentation mask.
"""

from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset, WeightedRandomSampler

try:
    import albumentations as A
except ImportError:
    A = None


class Landslide4SenseDataset(Dataset):
    """PyTorch Dataset for Landslide4Sense HDF5 patches.

    Supports two directory layouts:

    HuggingFace layout (from `huggingface-cli download`):
        data_dir/
            images/train/       (3799 image_N.h5)
            images/validation/  (245 image_N.h5)
            annotations/train/       (3799 mask_N.h5)
            annotations/validation/  (245 mask_N.h5)

    Simple layout:
        data_dir/
            train/img/  (3799 .h5 files)
            train/mask/ (3799 .h5 files)
            val/img/    (245 .h5 files)
            val/mask/   (245 .h5 files)
    """

    def __init__(
        self,
        data_dir: str | Path,
        split: str = "train",
        transform: A.Compose | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.split = split
        self.transform = transform

        img_dir, mask_dir = self._find_directories()

        # Pair files by numeric ID to handle mismatched counts
        self.img_files, self.mask_files = self._pair_files(img_dir, mask_dir)

        if len(self.img_files) == 0:
            raise ValueError(f"No paired .h5 files found in {img_dir} and {mask_dir}")

    def _find_directories(self) -> tuple[Path, Path]:
        """Locate image and mask directories, supporting multiple layouts."""
        split = self.split
        # Map "val" -> "validation" for HuggingFace layout
        hf_split = "validation" if split == "val" else split

        # Try HuggingFace layout first: images/<split>/ + annotations/<split>/
        hf_img = self.data_dir / "images" / hf_split
        hf_mask = self.data_dir / "annotations" / hf_split
        if hf_img.exists() and hf_mask.exists():
            return hf_img, hf_mask

        # Try simple layout: <split>/img/ + <split>/mask/
        simple_img = self.data_dir / split / "img"
        simple_mask = self.data_dir / split / "mask"
        if simple_img.exists() and simple_mask.exists():
            return simple_img, simple_mask

        # Try simple layout with "validation" spelling
        simple_img_v = self.data_dir / hf_split / "img"
        simple_mask_v = self.data_dir / hf_split / "mask"
        if simple_img_v.exists() and simple_mask_v.exists():
            return simple_img_v, simple_mask_v

        raise FileNotFoundError(
            f"Could not find dataset for split '{split}'. "
            f"Tried:\n"
            f"  HuggingFace: {hf_img} + {hf_mask}\n"
            f"  Simple:      {simple_img} + {simple_mask}\n"
            f"Download with: huggingface-cli download ibm-nasa-geospatial/Landslide4sense --repo-type dataset --local-dir <dir>"
        )

    @staticmethod
    def _pair_files(img_dir: Path, mask_dir: Path) -> tuple[list[Path], list[Path]]:
        """Pair image and mask files by numeric ID.

        Handles cases where image and mask directories have different file
        counts by only keeping files that exist in both directories.
        """
        import re

        def extract_id(path: Path) -> str | None:
            m = re.search(r"(\d+)", path.stem)
            return m.group(1) if m else None

        img_by_id = {extract_id(p): p for p in img_dir.glob("*.h5") if extract_id(p)}
        mask_by_id = {extract_id(p): p for p in mask_dir.glob("*.h5") if extract_id(p)}

        common_ids = sorted(img_by_id.keys() & mask_by_id.keys(), key=int)

        img_files = [img_by_id[i] for i in common_ids]
        mask_files = [mask_by_id[i] for i in common_ids]

        skipped = len(img_by_id) + len(mask_by_id) - 2 * len(common_ids)
        if skipped > 0:
            print(f"  Paired {len(common_ids)} samples ({skipped} unpaired files skipped)")

        return img_files, mask_files

    def __len__(self) -> int:
        return len(self.img_files)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        # Load image (14, 128, 128) and mask (128, 128)
        with h5py.File(self.img_files[idx], "r") as f:
            image = f["img"][()].astype(np.float32)  # (128, 128, 14)

        with h5py.File(self.mask_files[idx], "r") as f:
            mask = f["mask"][()].astype(np.float32)  # (128, 128)

        # Apply augmentations (albumentations expects HWC for image)
        if self.transform is not None:
            # Separate spectral bands (0-11) from terrain bands (12-13) for noise aug
            transformed = self.transform(image=image, mask=mask)
            image = transformed["image"]
            mask = transformed["mask"]

        # Convert to CHW format
        image = np.transpose(image, (2, 0, 1))  # (14, 128, 128)
        mask = mask[np.newaxis, ...]  # (1, 128, 128)

        return torch.from_numpy(image), torch.from_numpy(mask)


def compute_normalization_stats(
    dataset: Landslide4SenseDataset,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute per-channel mean and std from the training split.

    Returns:
        Tuple of (means, stds), each of shape (14,).
    """
    print(f"Computing normalization stats from {len(dataset)} samples...")
    channel_sum = np.zeros(14, dtype=np.float64)
    channel_sq_sum = np.zeros(14, dtype=np.float64)
    pixel_count = 0

    for idx in range(len(dataset)):
        with h5py.File(dataset.img_files[idx], "r") as f:
            image = f["img"][()].astype(np.float64)  # (128, 128, 14)

        # Sum per channel
        for c in range(14):
            channel_sum[c] += image[:, :, c].sum()
            channel_sq_sum[c] += (image[:, :, c] ** 2).sum()

        pixel_count += image.shape[0] * image.shape[1]

        if (idx + 1) % 500 == 0:
            print(f"  Processed {idx + 1}/{len(dataset)}")

    means = channel_sum / pixel_count
    stds = np.sqrt(channel_sq_sum / pixel_count - means**2)

    # Avoid zero std
    stds = np.maximum(stds, 1e-6)

    print(f"  Means: {means}")
    print(f"  Stds:  {stds}")
    return means.astype(np.float32), stds.astype(np.float32)


def compute_positive_weight(dataset: Landslide4SenseDataset) -> float:
    """Compute pos_weight for BCE loss from training mask class ratio.

    Returns:
        Ratio of negative to positive pixels (typically ~4.0 for Landslide4Sense).
    """
    positive_pixels = 0
    total_pixels = 0

    for idx in range(len(dataset)):
        with h5py.File(dataset.mask_files[idx], "r") as f:
            mask = f["mask"][()]

        positive_pixels += mask.sum()
        total_pixels += mask.size

    negative_pixels = total_pixels - positive_pixels
    pos_weight = negative_pixels / max(positive_pixels, 1)
    print(f"Class ratio: {positive_pixels}/{total_pixels} positive pixels, pos_weight={pos_weight:.2f}")
    return float(pos_weight)


def get_positive_sampler(dataset: Landslide4SenseDataset) -> WeightedRandomSampler:
    """Create a WeightedRandomSampler that oversamples positive patches at 2x.

    A positive patch is one containing any landslide pixel.
    """
    weights = []
    for idx in range(len(dataset)):
        with h5py.File(dataset.mask_files[idx], "r") as f:
            mask = f["mask"][()]

        has_landslide = mask.sum() > 0
        weights.append(2.0 if has_landslide else 1.0)

    return WeightedRandomSampler(
        weights=weights,
        num_samples=len(weights),
        replacement=True,
    )


def get_train_transform() -> "A.Compose":
    """Augmentation pipeline for training.

    Geometric transforms apply to all 14 channels + mask.
    Noise augmentation targets spectral bands (0-11) only.
    """
    if A is None:
        raise ImportError("albumentations is required for training augmentations")

    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.5),
        A.RandomRotate90(p=0.5),
        A.Affine(
            translate_percent={"x": (-0.1, 0.1), "y": (-0.1, 0.1)},
            scale=(0.85, 1.15),
            rotate=(-45, 45),
            p=0.5,
        ),
        A.ElasticTransform(alpha=50, sigma=2.5, p=0.2),
        A.GaussNoise(std_range=(0.01, 0.05), p=0.3),
    ])
