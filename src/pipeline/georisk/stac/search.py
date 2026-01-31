"""High-level scene search functionality."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from georisk.stac.client import StacClient

logger = structlog.get_logger()


@dataclass
class SceneInfo:
    """Information about a satellite imagery scene."""

    scene_id: str
    datetime: datetime
    cloud_cover: float
    bbox: tuple[float, float, float, float]
    assets: dict[str, dict[str, str]]
    platform: str | None = None
    epsg: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneInfo":
        """Create SceneInfo from a STAC item dictionary."""
        dt_str = data.get("datetime", "")
        if dt_str:
            # Handle ISO format with Z timezone
            dt_str = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str)
        else:
            dt = datetime.now()

        return cls(
            scene_id=data["id"],
            datetime=dt,
            cloud_cover=data.get("cloud_cover", 0),
            bbox=tuple(data.get("bbox", [0, 0, 0, 0])),
            assets=data.get("assets", {}),
            platform=data.get("properties", {}).get("platform"),
            epsg=data.get("properties", {}).get("proj:epsg"),
        )

    def get_band_url(self, band: str) -> str | None:
        """Get the URL for a specific band."""
        asset = self.assets.get(band)
        return asset.get("href") if asset else None


def search_scenes(
    bbox: tuple[float, float, float, float],
    start_date: str,
    end_date: str,
    max_cloud_cover: float = 20.0,
    max_items: int = 50,
) -> list[SceneInfo]:
    """Search for satellite imagery scenes.

    Args:
        bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat).
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).
        max_cloud_cover: Maximum cloud cover percentage.
        max_items: Maximum number of scenes to return.

    Returns:
        List of SceneInfo objects sorted by date (newest first).
    """
    client = StacClient()
    results = client.search(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        max_items=max_items,
        max_cloud_cover=max_cloud_cover,
    )

    scenes = [SceneInfo.from_dict(r) for r in results]
    scenes.sort(key=lambda s: s.datetime, reverse=True)

    logger.info(
        "Scene search complete",
        num_scenes=len(scenes),
        date_range=f"{start_date} to {end_date}",
    )

    return scenes


def find_scene_pair(
    bbox: tuple[float, float, float, float],
    before_date: str,
    after_date: str,
    window_days: int = 30,
) -> tuple[SceneInfo | None, SceneInfo | None]:
    """Find a pair of scenes for before/after comparison.

    Args:
        bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat).
        before_date: Target date for "before" scene.
        after_date: Target date for "after" scene.
        window_days: Search window in days around target dates.

    Returns:
        Tuple of (before_scene, after_scene). Either may be None if not found.
    """
    client = StacClient()

    before_result = client.find_best_scene(bbox, before_date, window_days)
    after_result = client.find_best_scene(bbox, after_date, window_days)

    before_scene = SceneInfo.from_dict(before_result) if before_result else None
    after_scene = SceneInfo.from_dict(after_result) if after_result else None

    if before_scene and after_scene:
        logger.info(
            "Found scene pair",
            before_id=before_scene.scene_id,
            before_date=before_scene.datetime.isoformat(),
            after_id=after_scene.scene_id,
            after_date=after_scene.datetime.isoformat(),
        )
    else:
        logger.warning(
            "Could not find complete scene pair",
            before_found=before_scene is not None,
            after_found=after_scene is not None,
        )

    return before_scene, after_scene
