"""STAC catalog client for Microsoft Planetary Computer."""

import planetary_computer
import pystac_client
import structlog

from georisk.config import get_config

logger = structlog.get_logger()


class StacClient:
    """Client for searching Sentinel-2 imagery in Planetary Computer."""

    def __init__(self, catalog_url: str | None = None):
        """Initialize the STAC client.

        Args:
            catalog_url: STAC catalog URL. Defaults to Planetary Computer.
        """
        config = get_config()
        self.catalog_url = catalog_url or config.stac.catalog_url
        self.collection = config.stac.collection
        self.max_cloud_cover = config.stac.max_cloud_cover

        self._client: pystac_client.Client | None = None

    @property
    def client(self) -> pystac_client.Client:
        """Get or create the STAC client."""
        if self._client is None:
            self._client = pystac_client.Client.open(
                self.catalog_url,
                modifier=planetary_computer.sign_inplace,
            )
            logger.info("Connected to STAC catalog", url=self.catalog_url)
        return self._client

    def search(
        self,
        bbox: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
        max_items: int = 100,
        max_cloud_cover: float | None = None,
    ) -> list[dict]:
        """Search for Sentinel-2 scenes within a bounding box and date range.

        Args:
            bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat).
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).
            max_items: Maximum number of items to return.
            max_cloud_cover: Maximum cloud cover percentage (0-100).

        Returns:
            List of scene metadata dictionaries.
        """
        cloud_cover = max_cloud_cover if max_cloud_cover is not None else self.max_cloud_cover

        logger.info(
            "Searching STAC catalog",
            bbox=bbox,
            date_range=f"{start_date}/{end_date}",
            max_cloud_cover=cloud_cover,
        )

        search = self.client.search(
            collections=[self.collection],
            bbox=bbox,
            datetime=f"{start_date}/{end_date}",
            query={"eo:cloud_cover": {"lt": cloud_cover}},
            max_items=max_items,
            sortby=[{"field": "properties.datetime", "direction": "desc"}],
        )

        items = list(search.items())
        logger.info("Search complete", num_results=len(items))

        return [self._item_to_dict(item) for item in items]

    def get_item(self, item_id: str) -> dict | None:
        """Get a specific STAC item by ID.

        Args:
            item_id: The STAC item ID.

        Returns:
            Scene metadata dictionary or None if not found.
        """
        try:
            # Search with a broad query and filter by ID
            # Note: Direct item access isn't always available via pystac_client
            search = self.client.search(
                collections=[self.collection],
                ids=[item_id],
                max_items=1,
            )
            items = list(search.items())
            if items:
                return self._item_to_dict(items[0])
            return None
        except Exception as e:
            logger.warning("Failed to get item", item_id=item_id, error=str(e))
            return None

    def _item_to_dict(self, item) -> dict:
        """Convert a STAC item to a metadata dictionary."""
        props = item.properties

        # Get asset URLs for Sentinel-2 bands
        # All 13 spectral bands indexed for ML land cover classification (EuroSAT)
        # Core bands: B02-B04 (RGB), B08 (NIR/NDVI), SCL (cloud mask), visual (preview)
        assets = {}
        for band_name in [
            "B01", "B02", "B03", "B04", "B05", "B06", "B07",
            "B08", "B8A", "B09", "B10", "B11", "B12",
            "SCL", "visual",
        ]:
            if band_name in item.assets:
                asset = item.assets[band_name]
                assets[band_name] = {
                    "href": asset.href,
                    "type": asset.media_type,
                }

        return {
            "id": item.id,
            "datetime": props.get("datetime"),
            "cloud_cover": props.get("eo:cloud_cover", 0),
            "bbox": item.bbox,
            "geometry": item.geometry,
            "assets": assets,
            "properties": {
                "platform": props.get("platform"),
                "instrument": props.get("instruments"),
                "gsd": props.get("gsd"),
                "proj:epsg": props.get("proj:epsg"),
            },
        }

    def find_best_scene(
        self,
        bbox: tuple[float, float, float, float],
        target_date: str,
        window_days: int = 30,
    ) -> dict | None:
        """Find the best scene closest to a target date.

        Args:
            bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat).
            target_date: Target date in ISO format (YYYY-MM-DD).
            window_days: Search window in days before and after target.

        Returns:
            Best matching scene or None if no scenes found.
        """
        from datetime import datetime, timedelta

        target = datetime.fromisoformat(target_date)
        start = (target - timedelta(days=window_days)).strftime("%Y-%m-%d")
        end = (target + timedelta(days=window_days)).strftime("%Y-%m-%d")

        scenes = self.search(bbox, start, end)

        if not scenes:
            logger.warning("No scenes found", target_date=target_date, window_days=window_days)
            return None

        # Find scene closest to target date with lowest cloud cover
        def score(scene: dict) -> tuple[int, float]:
            scene_date = datetime.fromisoformat(scene["datetime"].replace("Z", "+00:00"))
            days_diff = abs((scene_date.replace(tzinfo=None) - target).days)
            cloud = scene.get("cloud_cover", 100)
            return (days_diff, cloud)

        scenes.sort(key=score)
        best = scenes[0]
        logger.info(
            "Found best scene",
            scene_id=best["id"],
            datetime=best["datetime"],
            cloud_cover=best["cloud_cover"],
        )
        return best
