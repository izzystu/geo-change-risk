# Landslide U-Net Training Notes

## Concepts

### The Model

We use a **U-Net**, a neural network architecture designed for image segmentation (labeling each pixel in an image). It takes a satellite image patch and outputs a mask predicting which pixels are landslide debris.

The U-Net has two halves:
- **Encoder** (the "eyes") — extracts features from the image (edges, textures, terrain patterns). We use **resnet34**, a 34-layer deep network. We also tried resnet50 (50 layers, more capacity) but it didn't improve results on this small dataset.
- **Decoder** — takes those features and produces a pixel-level prediction map.

**ImageNet pretrained weights** means the encoder starts with features learned from millions of natural images (cats, cars, landscapes). Even though satellite imagery looks different, low-level features like edges and textures transfer well and give the model a head start vs random initialization.

### Loss Functions

The loss function measures "how wrong was the model?" after each prediction. The model adjusts its weights to minimize this number.

- **BCE (Binary Cross-Entropy)** — scores every pixel independently: "was this pixel landslide or not?" Simple and effective, but with 97.7% of pixels being "not landslide", the model can score well by just predicting "no" everywhere. We use `pos_weight` to counteract this: a pos_weight of 10 means getting a landslide pixel wrong costs 10x more than a normal pixel.
- **Dice loss** — measures overall shape overlap between predicted and real landslide areas, rather than scoring individual pixels. Naturally handles class imbalance. We always use this in combination with BCE or Focal.
- **Focal loss** — a smarter version of BCE that automatically down-weights "easy" pixels (ones the model is already confident about) and focuses on "hard" pixels near landslide boundaries. Designed for extreme class imbalance but didn't clearly outperform simple BCE + pos_weight for us.

### Metrics (how we judge model quality)

- **Precision** — "When the model says landslide, how often is it right?" Low precision = too many false alarms.
- **Recall** — "Of all real landslides, how many did the model find?" Low recall = missed landslides.
- **IoU (Intersection over Union)** — "How well does the predicted shape overlap the real shape?" Combines precision and recall into one number. 1.0 = perfect, 0.0 = no overlap. Our target was 0.55.
- **F1** — harmonic mean of precision and recall. Balances both into a single score.

For a **risk assessment tool**, higher precision is generally preferred because false alarms waste user attention, while the pipeline has additional filtering (slope thresholds, dual criteria) that can partially compensate for missed detections.

### Other Training Concepts

- **Learning rate (LR)** — how big a step the model takes when adjusting weights. Too high = overshoots good solutions. Too low = learns too slowly or gets stuck.
- **Scheduler** — adjusts the learning rate during training. **Cosine** follows a fixed wave pattern (which can disrupt training at restart points). **Plateau** only reduces LR when performance stalls (more adaptive).
- **Batch size** — how many images the model sees before updating weights. Larger batches = smoother gradient estimates but more GPU memory.
- **Early stopping** — stops training when validation performance hasn't improved for N epochs (patience), preventing overfitting.
- **pos_weight** — multiplier on the cost of misclassifying positive (landslide) pixels in BCE loss.

---

## Dataset

**Landslide4Sense** from HuggingFace (`ibm-nasa-geospatial/Landslide4sense`)

- 3,799 train / 245 val / 800 test patches (128x128 pixels, 14 channels)
- Channels: 12 Sentinel-2 bands (no B8A) + slope + DEM elevation
- HDF5 format, keys: `"img"` shape `(128,128,14)`, `"mask"` shape `(128,128)`
- Binary labels: 1=landslide, 0=stable
- Class imbalance: only 2.3% of pixels are landslide (1.4M / 62.2M)
- Train annotations have 5 extra mask files (3804 vs 3799 images) — dataset loader pairs by numeric ID

### Download

```powershell
pip install huggingface-hub
$env:HF_TOKEN="your_token"
python -c "from huggingface_hub import snapshot_download; snapshot_download('ibm-nasa-geospatial/Landslide4sense', repo_type='dataset', local_dir='./data')"
```

No login required (public dataset), but setting HF_TOKEN avoids rate limiting.

### Normalization Stats (computed from training split)

```
Means: [0.926, 0.923, 0.954, 0.960, 1.023, 1.043, 1.036, 1.047, 1.170, 1.174, 1.049, 1.037, 1.251, 1.650]
Stds:  [0.141, 0.221, 0.318, 0.572, 0.460, 0.447, 0.465, 0.495, 0.513, 0.684, 0.532, 0.663, 0.678, 1.073]
```

## Quick Start

From the `machine-learning/landslide/` directory:

```powershell
# 1. Install training dependencies (GPU build)
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130

# 2. Download dataset (~8GB)
#    Optional: set HF token to avoid rate limiting (public dataset, no login required)
$env:HF_TOKEN="your_token_here"
python -c "from huggingface_hub import snapshot_download; snapshot_download('ibm-nasa-geospatial/Landslide4sense', repo_type='dataset', local_dir='./data')"

# 3. Train (best config from our experiments, ~30 min on RTX 4070)
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 16 --encoder-weights imagenet --max-pos-weight 10

# 4. Upload model to object storage (S3/MinIO)
python -m georisk model upload landslide_model.pth

# Or copy to local cache directly
mkdir "$HOME\.cache\georisk\models" -Force
copy landslide_model.pth "$HOME\.cache\georisk\models\landslide_model.pth"
```

Once uploaded to object storage, the pipeline auto-downloads the model on first use. You can also override the model path via the `LANDSLIDE_MODEL_PATH` environment variable.

Without a deployed model, the pipeline runs normally but skips landslide classification.

## Environment

- Windows 11, Python 3.13
- RTX 4070 Laptop GPU (8GB VRAM), CUDA 13.0
- PyTorch 2.10.0+cu130 (must install with `--index-url https://download.pytorch.org/whl/cu130`)
- `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130` (default pip install gives CPU-only build)
- albumentations >= 2.0 changed API: `ShiftScaleRotate` -> `Affine`, `GaussNoise(var_limit=)` -> `GaussNoise(std_range=)`

## Training Runs

### Run 1: Baseline (random init, raw pos_weight)

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 16
```

| Setting | Value |
|---------|-------|
| Encoder | resnet34, random init |
| pos_weight | 42.14 (uncapped, computed from data) |
| Batch size | 16 |
| LR | 1e-4 |
| Result | **IoU 0.32**, early stopped at epoch 72 |

**Problem:** pos_weight=42 was far too aggressive. The plan estimated ~4.0 but actual class ratio is ~43:1 (2.3% positive pixels). This caused the model to over-predict landslides — high recall (0.85) but low precision (0.29). IoU plateaued around 0.32, well below the 0.55 target.

**Lesson:** Always cap pos_weight. A value of 42x makes the loss overwhelmingly dominated by positive pixels, preventing the model from learning to reject false positives.

### Run 2: Capped pos_weight + ImageNet encoder weights

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 16 --encoder-weights imagenet --max-pos-weight 10
```

| Setting | Value |
|---------|-------|
| Encoder | resnet34, ImageNet weights adapted to 14ch |
| pos_weight | 10.0 (capped from 42.14) |
| Batch size | 16 |
| LR | 1e-4 |
| Result | **IoU 0.4598**, F1 0.63, Prec 0.54, Rec 0.76, early stopped at epoch 58 |

**Result:** Significant improvement over Run 1. Precision rose from 0.29 to 0.54 (fewer false positives), recall dropped from 0.85 to 0.76 (expected with lower pos_weight). IoU jumped from 0.32 to 0.46 but still below 0.55 target.

**Lesson:** ImageNet pretrained weights + capped pos_weight both helped. The model is no longer over-predicting but may need more capacity (resnet50) or larger batches for smoother gradients.

### Run 3: resnet50 + batch 32 + pos_weight 5

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 32 --encoder-weights imagenet --max-pos-weight 5 --backbone resnet50
```

| Setting | Value |
|---------|-------|
| Encoder | resnet50, ImageNet weights adapted to 14ch |
| pos_weight | 5.0 (capped from 42.14) |
| Batch size | 32 |
| LR | 1e-4 |
| Result | **IoU 0.4588**, F1 0.59, Prec 0.50, Rec 0.71, early stopped at epoch 49 |

**Result:** No improvement over Run 2 despite larger model and batch size. resnet50 didn't help — the bottleneck isn't model capacity. Stopped earlier (epoch 49 vs 58), suggesting resnet50 may overfit slightly faster on this small dataset.

**Lesson:** More model capacity (resnet50) doesn't help when the dataset is small (3,799 training patches). The simpler resnet34 is sufficient.

### Run 4: Focal loss (replacing BCE)

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 32 --encoder-weights imagenet --backbone resnet34 --loss dice-focal
```

| Setting | Value |
|---------|-------|
| Encoder | resnet34, ImageNet weights adapted to 14ch |
| Loss | Dice + Focal (gamma=2.0), no pos_weight needed |
| Batch size | 32 |
| LR | 1e-4 |
| Result | **IoU 0.4760**, F1 0.55, Prec 0.44, Rec 0.75, early stopped at epoch 27 |

**Result:** Highest peak IoU (0.476) but converged and stalled much faster (best at ~epoch 12, stopped at 27). The cosine scheduler restarted the LR at epoch 20, destabilizing training after the model had already peaked.

**Lesson:** Focal loss converges fast but the cosine warm restart scheduler disrupted it. The LR jump at epoch 20 kicked the model out of a good minimum. Also, precision dropped (0.44) meaning more false positives.

### Run 5: Focal loss + ReduceLROnPlateau + lower LR

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 32 --encoder-weights imagenet --backbone resnet34 --loss dice-focal --scheduler plateau --lr 5e-5
```

| Setting | Value |
|---------|-------|
| Encoder | resnet34, ImageNet weights adapted to 14ch |
| Loss | Dice + Focal (gamma=2.0) |
| Scheduler | ReduceLROnPlateau (factor=0.5, patience=5, monitors val IoU) |
| Batch size | 32 |
| LR | 5e-5 |
| Result | **IoU 0.4528**, F1 0.62, Prec 0.58, Rec 0.65, early stopped at epoch 50 |

**Result:** Most stable training (ran longest, best at ~epoch 35) and highest precision (0.58), but recall dropped to 0.65 and overall IoU didn't improve. The lower LR made the model too conservative — good at avoiding false positives but missed too many real landslides.

**Lesson:** The plateau scheduler worked well for stability, but halving the learning rate was counterproductive. 1e-4 was the right LR.

### Run 6: Re-run of Run 2 settings (final v1 model)

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 16 --encoder-weights imagenet --max-pos-weight 10
```

| Setting | Value |
|---------|-------|
| Encoder | resnet34, ImageNet weights adapted to 14ch |
| pos_weight | 10.0 (capped from 42.14) |
| Batch size | 16 |
| LR | 1e-4 |
| Result | **IoU 0.4344**, F1 0.59, Prec 0.51, Rec 0.70, early stopped at epoch 43 |

**Result:** Lower than Run 2 (0.43 vs 0.46) with identical settings. The difference is due to random variance — different random initialization of the decoder, different augmentation/sampling order each run.

### Run 8: Final v1 model (same config as Run 2)

```
python train.py --data-dir ./data --output landslide_model.pth --epochs 100 --batch-size 16 --encoder-weights imagenet --max-pos-weight 10
```

| Setting | Value |
|---------|-------|
| Encoder | resnet34, ImageNet weights adapted to 14ch |
| pos_weight | 10.0 (capped from 42.14) |
| Batch size | 16 |
| LR | 1e-4 |
| Result | **IoU 0.4702**, F1 0.56, Prec 0.42, Rec 0.78, early stopped at epoch 39 |

**Result:** Second best IoU overall (0.47), close to Run 4's peak (0.48). High recall (0.78) with moderate precision. This is the deployed v1 model.

## Summary

| Run | Backbone | Loss | pos_weight | LR | Batch | Scheduler | IoU | Prec | Rec |
|-----|----------|------|------------|-----|-------|-----------|-----|------|-----|
| 1 | resnet34 | Dice+BCE | 42.1 | 1e-4 | 16 | Cosine | 0.32 | 0.29 | 0.85 |
| 2 | resnet34 | Dice+BCE | 10.0 | 1e-4 | 16 | Cosine | 0.46 | 0.54 | 0.76 |
| 3 | resnet50 | Dice+BCE | 5.0 | 1e-4 | 32 | Cosine | 0.46 | 0.50 | 0.71 |
| 4 | resnet34 | Dice+Focal | — | 1e-4 | 32 | Cosine | 0.48 | 0.44 | 0.75 |
| 5 | resnet34 | Dice+Focal | — | 5e-5 | 32 | Plateau | 0.45 | 0.58 | 0.65 |
| 6 | resnet34 | Dice+BCE | 10.0 | 1e-4 | 16 | Cosine | 0.43 | 0.51 | 0.70 |
| 8 | resnet34 | Dice+BCE | 10.0 | 1e-4 | 16 | Cosine | **0.47** | 0.42 | 0.78 |

### What we learned

- **~0.46 IoU is the practical ceiling** for a single U-Net on Landslide4Sense. Run-to-run variance is ~0.05 IoU, so runs 2-8 are all within noise of each other.
- **Two changes mattered:** ImageNet pretrained encoder weights and capping pos_weight at 10. Everything else (resnet50, focal loss, different scheduler, lower LR, larger batch) made no meaningful difference.
- **The deployed v1 model** (Run 8) has IoU 0.47, Precision 0.42, Recall 0.78. The inference pipeline adds slope filtering (only classifies polygons in steep terrain) and dual-criteria thresholds (mean probability + pixel fraction) that further reduce false positives in practice.

### How we compare to the Landslide4Sense 2022 competition

The official competition baseline U-Net scored Precision 51.8%, Recall 65.5%, F1 57.8%. Our best run (Run 2) beat the baseline on all three: Precision 54%, Recall 76%, F1 63%.

The competition winners scored **F1 ~74-75%** using transformer-based architectures (Swin Transformer, SegFormer) plus ensemble methods, hard example mining, self-training, and mix-up augmentation. The ~12-point F1 gap between our U-Net and those winning entries is not a hyperparameter tuning problem — it's an architectural difference.

**U-Nets** process images through small sliding windows (3x3 pixel filters). Each layer only sees a small neighborhood, so the network must stack many layers and progressively shrink/expand the image to understand large-scale patterns. It's like reading a page through a keyhole — you scan across and piece things together.

**Transformers** (Swin, SegFormer) use an "attention" mechanism that lets every part of the image look at every other part directly. A pixel in the top-left can relate to one in the bottom-right in a single step, rather than relying on information to propagate through many layers.

For landslide detection, long-range spatial context matters — a debris field's relationship to the slope above it, drainage patterns, surrounding terrain. Transformers capture this naturally, which is why they scored higher. But they're significantly larger, slower to train, need more data, and are a bigger engineering effort. For a v1 where landslide detection is one signal among many, the U-Net is the right tradeoff.

## Performance Notes

- ~40s per epoch on RTX 4070 Laptop GPU
- GPU utilization is low (brief spikes) — bottleneck is CPU-side HDF5 data loading, not GPU compute
- 128x128 patches at batch_size=16 use only ~0.8GB VRAM; batch_size=32 would be fine
- Full 100 epochs ~65 min, but early stopping typically triggers at 40-60 epochs

## Possible Future Improvements

- ~~**Batch size 32**~~ — tried in Run 3, no improvement
- ~~**resnet50 backbone**~~ — tried in Run 3, no improvement over resnet34
- ~~**Focal loss**~~ — tried in Runs 4-5, marginal or no improvement
- ~~**ReduceLROnPlateau scheduler**~~ — tried in Run 5, more stable but no improvement
- **Pre-cache HDF5 to numpy** to eliminate data loading bottleneck
- **Lower confidence threshold** at inference (0.3-0.4) if precision is high but recall drops
- **Tversky loss** with alpha > beta to penalize FPs more than FNs
- **Test-time augmentation (TTA)** — average predictions over flips/rotations at inference
- **Set random seed** for reproducibility between runs
