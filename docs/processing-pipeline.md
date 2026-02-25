# Processing Pipeline

The Python raster pipeline (`src/pipeline/`) executes change detection and risk scoring via the `georisk process` CLI command. It communicates with the .NET API throughout to update processing run status and persist results.

## Pipeline Steps

### Step 0 — Setup

- Fetches AOI details (bounding box, name) from the .NET API
- Creates a new `ProcessingRun` record (or reuses an existing `--run-id`)
- The run's status is updated at the API after each step so the web UI can show progress

### Step 1 — Find Imagery

- Searches the STAC catalog (Microsoft Planetary Computer) for a before/after Sentinel-2 scene pair matching the target dates within a configurable search window, using `pystac-client` for catalog queries and the `planetary-computer` library to sign asset URLs for download access
- Updates the processing run with the resolved scene IDs

### Step 1b — RGB Composites

- Creates true-color RGB GeoTIFF and PNG from each scene for the web UI's before/after comparison (Sentinel-2 raw data is delivered as individual spectral bands with scientific reflectance values, not display-ready images, so an RGB composite must be assembled and brightness-adjusted)
- Uploads both to object storage (MinIO locally, S3 in AWS) with georeferencing bounds sidecar files

### Step 2 — Calculate NDVI

- Downloads the Red (B04) and NIR (B08) bands for each scene
- Computes NDVI = (NIR - Red) / (NIR + Red) for both before and after scenes

### Step 3 — Detect Changes

- Diffs the two NDVI rasters to find areas where vegetation dropped significantly
- Vectorizes the change raster into polygons using `rasterio.features.shapes` to trace contiguous pixel regions, `shapely` to create polygon objects, and `pyproj` to reproject from the raster's native CRS to WGS84
- Output: a list of `ChangePolygon` objects with geometry, NDVI drop statistics, and area

### Step 3b — Terrain Analysis (optional)

Disabled with `--skip-terrain` or `--dem-source none`.

- Downloads a DEM from USGS 3DEP for the AOI bounding box
- Calculates slope and aspect from the DEM
- Enriches each change polygon with: mean slope, max slope, aspect, and elevation

### Step 3c — Land Cover Classification (optional)

Disabled with `--skip-landcover`. Requires ML dependencies (`pip install -e ".[ml]"`).

- Loads all 13 Sentinel-2 bands from the *before* scene
- Loads the pretrained EuroSAT model via TorchGeo
- For each change polygon: classifies land cover (Forest, Residential, etc.) with confidence score
- Re-classifies change types using land cover context (e.g., vegetation loss on cropland becomes AgriculturalChange)

See [Land Cover Classification (EuroSAT)](#land-cover-classification-eurosat) below for details.

### Step 3d — Landslide Detection (optional)

Disabled with `--skip-landslide`. Requires ML dependencies and terrain data from step 3b (skipped automatically if no DEM is available).

- Loads 12 Sentinel-2 bands from the *before* scene (excludes B8A, which is spectrally redundant with B08 at lower resolution — the Landslide4Sense training dataset omits it)
- Loads the custom-trained U-Net landslide model from local cache or object storage
- For each polygon with mean slope >= 10 degrees: runs landslide inference
- If positive: overrides `change_type` to `LandslideDebris` and stores ML confidence

See [Landslide Detection (U-Net)](#landslide-detection-u-net) below for details.

### Save Change Polygons

- POSTs all change polygons (with terrain, land cover, and landslide enrichments) to the .NET API
- Captures the created polygon IDs for linking to risk events in the next step

### Step 4 — Risk Scoring

- Fetches all registered assets (power lines, substations, hospitals, schools, etc.) for the AOI from the API
- For each change polygon, finds assets within proximity distance (default 1000m)
- For each change-asset pair, calculates a 0-100 risk score from additive factors:
  - Distance to asset (up to 28 points)
  - NDVI drop magnitude (up to 25 points)
  - Change area (up to 15 points)
  - Slope + direction (up to 20 points)
  - Aspect (up to 5 points)
- Applies three multipliers:
  - Land cover context (0.25x-1.0x) — suppresses scores for changes on low-risk land types
  - Landslide boost (1.8x-2.5x) — amplifies confirmed landslide events
  - Asset criticality (0.5x-2.0x) — weights by asset importance
- POSTs all risk events to the .NET API

### Step 5 — Complete

- Marks the processing run as `Completed` with summary metadata (polygon count, risk event count, detection stats, which ML models were used)
- Prints a summary highlighting high/critical risk events
- If any step fails, the run is marked `Failed` with the error message and the process exits with code 1

---

## ML Models

Both ML steps are optional. If the ML dependencies (`torch`, `torchgeo`, `segmentation-models-pytorch`) are not installed, the pipeline skips classification gracefully and continues with rule-based change detection and scoring.

### Land Cover Classification (EuroSAT)

**File:** `src/pipeline/georisk/raster/landcover.py`

Classifies the *before* Sentinel-2 scene into 10 land cover classes to provide context for risk scoring. A vegetation change in a forest is scored differently than one on a highway.

**How it works:**

1. `load_eurosat_model()` loads a pretrained ResNet (default ResNet18) from TorchGeo with `SENTINEL2_ALL_MOCO` weights. These weights were pretrained on unlabeled Sentinel-2 imagery using MoCo v2 (self-supervised contrastive learning), then fine-tuned on the EuroSAT dataset (27,000 labeled patches across 10 classes). The model is cached at module level after first load.
2. `load_scene_bands()` loads and aligns all 13 Sentinel-2 bands into a single multi-band DataArray, resampling lower-resolution bands (20m, 60m) to the 10m reference grid.
3. For each change polygon, `classify_polygon_landcover()`:
   - Extracts a 64x64 pixel patch centered on the polygon
   - Normalizes by dividing by 10,000 (standard Sentinel-2 reflectance scaling)
   - Resizes to 224x224 (model input size)
   - Runs inference with `torch.no_grad()`, applies softmax
   - Returns the dominant class, confidence, and a risk multiplier

**EuroSAT classes and risk multipliers:**

| Class | Risk Multiplier |
|---|---|
| Forest | 1.0 (baseline) |
| Residential | 0.9 |
| HerbaceousVegetation | 0.85 |
| River | 0.8 |
| PermanentCrop | 0.75 |
| Pasture | 0.7 |
| Industrial | 0.5 |
| SeaLake | 0.4 |
| AnnualCrop | 0.3 |
| Highway | 0.25 |

**Model source:** Downloaded automatically by TorchGeo/PyTorch on first use. No custom training required.

### Landslide Detection (U-Net)

**File:** `src/pipeline/georisk/raster/landslide.py`

Detects landslide debris on steep terrain by running per-pixel segmentation on change polygons.

**How it works:**

1. `load_landslide_model()` loads a custom-trained U-Net checkpoint (ResNet34 encoder). The model file is resolved from multiple locations in priority order:
   - Explicit path or `~/.cache/georisk/models/landslide_model.pth` (default)
   - `src/pipeline/models/landslide_model.pth` (dev convenience)
   - Auto-download from S3/MinIO `ml-models` bucket
   - The checkpoint is self-describing: it contains the architecture parameters (`encoder_name`, `in_channels`), normalization statistics (per-channel means and stds from the training set), and validation metrics.
2. `assemble_landslide_input()` builds a 14-channel input patch (128x128 pixels):
   - Channels 0-11: 12 Sentinel-2 bands (B01-B12, excludes B8A)
   - Channel 12: Slope in degrees (from DEM)
   - Channel 13: Elevation in meters (from DEM)
3. For each steep-terrain polygon (slope >= 10 degrees), `classify_polygon_landslide()`:
   - Normalizes the patch using per-channel z-score: `(value - mean) / std`
   - Runs U-Net inference with `torch.no_grad()`, applies sigmoid
   - Produces a 128x128 probability map (landslide probability per pixel)
   - Applies dual classification criteria to reduce false positives:
     - Mean probability > 35% (70% of the 0.5 threshold)
     - At least 15% of pixels exceed the 0.5 threshold
   - Both criteria must be met to classify as a landslide

**Model source:** Trained in-house on the Landslide4Sense dataset (3,799 training patches). Training code is at `machine-learning/landslide/`. The deployed model (ResNet34 encoder, Dice + BCE loss with pos_weight=10.0) achieved IoU 0.47, Precision 0.42, Recall 0.78.

### EuroSAT vs Landslide Model Comparison

| | EuroSAT (Land Cover) | Landslide (U-Net) |
|---|---|---|
| **Task** | Classification (whole-patch label) | Segmentation (per-pixel map) |
| **Architecture** | ResNet18 | U-Net + ResNet34 encoder |
| **Library** | TorchGeo | segmentation-models-pytorch |
| **Source** | Pretrained by researchers, hosted by TorchGeo | Trained in-house on Landslide4Sense |
| **Input** | 13 bands, 64x64 resized to 224x224 | 14 channels (12 bands + slope + DEM), 128x128 |
| **Output** | 10-class softmax probabilities | 128x128 pixel probability map |
| **Normalization** | Divide by 10,000 | Per-channel z-score from checkpoint |
| **Final activation** | Softmax | Sigmoid |
| **Decision logic** | argmax over 10 classes | Dual threshold (mean + pixel fraction) |
| **Model storage** | TorchGeo auto-downloads | S3/MinIO to local cache |
| **Effect on risk score** | 0.25x-1.0x multiplier | 1.8x-2.5x multiplier |

### ML Configuration

All ML settings are controlled via the `MlConfig` dataclass in `georisk/config.py` and can be set through environment variables:

| Setting | Default | Env Var |
|---|---|---|
| ML enabled | `True` | `ML_ENABLED` |
| Land cover enabled | `True` | `LANDCOVER_ENABLED` |
| Land cover backbone | `resnet18` | `LANDCOVER_BACKBONE` |
| Landslide enabled | `True` | `LANDSLIDE_ENABLED` |
| Landslide model path | (auto) | `LANDSLIDE_MODEL_PATH` |
| Landslide confidence threshold | `0.5` | `LANDSLIDE_CONFIDENCE_THRESHOLD` |
| Landslide slope threshold | `10.0` degrees | `LANDSLIDE_SLOPE_THRESHOLD_DEG` |
| Torch device | `auto` | `ML_DEVICE` |

### ML Model Management CLI

```bash
# Upload a trained model to object storage
georisk model upload landslide_model.pth --name landslide --version v1

# Download a model from object storage to local cache
georisk model download --name landslide --version v1

# List available models in object storage
georisk model list --name landslide
```
