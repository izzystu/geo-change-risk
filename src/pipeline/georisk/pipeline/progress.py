"""Progress callbacks for pipeline execution."""

import click


# Step name → display label mapping
_STEP_LABELS = {
    "search_imagery": "1. Searching for imagery",
    "create_rgb": "2. Creating RGB imagery for visualization",
    "calculate_ndvi": "3. Calculating NDVI",
    "detect_changes": "4. Detecting changes",
    "analyze_terrain": "5. Analyzing terrain",
    "classify_landcover": "6. Classifying land cover",
    "detect_landslide": "7. Running landslide detection",
    "save_polygons": "8. Saving change polygons",
    "score_risk": "9. Scoring risk events",
    "generate_lidar": "10. Generating LIDAR terrain",
    "complete_processing": "11. Completing processing",
}


def cli_progress(step_name: str, status: str, message: str) -> None:
    """Click-based progress output for CLI usage."""
    label = _STEP_LABELS.get(step_name, step_name)

    if status == "skipped":
        click.echo(f"\n{label}... skipped ({message})")
    elif status == "success":
        click.echo(f"\n{label}...")
        if message:
            click.echo(f"  {message}")
    elif status in ("failed", "error"):
        click.echo(f"\n{label}... WARNING: {message}")
