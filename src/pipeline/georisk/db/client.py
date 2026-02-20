"""HTTP client for the GeoRisk API."""

from enum import IntEnum
from typing import Any
from uuid import UUID

import httpx
import structlog

from georisk.config import get_config
from georisk.raster.change import ChangePolygon

logger = structlog.get_logger()


class ApiClient:
    """Client for interacting with the GeoRisk API."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        """Initialize the API client.

        Args:
            base_url: API base URL.
            timeout: Request timeout in seconds.
        """
        config = get_config()
        self.base_url = (base_url or config.api.base_url).rstrip("/")
        self.timeout = timeout or config.api.timeout
        self.api_key = config.api.api_key

        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["X-Api-Key"] = self.api_key
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # Health check

    def health_check(self) -> dict[str, Any]:
        """Check API health."""
        response = self.client.get("/api/system/health")
        response.raise_for_status()
        return response.json()

    # Areas of Interest

    def get_aoi(self, aoi_id: str) -> dict[str, Any]:
        """Get an Area of Interest by ID.

        Args:
            aoi_id: The AOI identifier.

        Returns:
            AOI details including bounding box and center.
        """
        response = self.client.get(f"/api/areas-of-interest/{aoi_id}")
        response.raise_for_status()
        return response.json()

    def get_aoi_bbox(self, aoi_id: str) -> tuple[float, float, float, float]:
        """Get the bounding box for an AOI.

        Args:
            aoi_id: The AOI identifier.

        Returns:
            Bounding box as (min_lon, min_lat, max_lon, max_lat).
        """
        aoi = self.get_aoi(aoi_id)
        bbox = aoi.get("boundingBox", [])
        if len(bbox) != 4:
            raise ValueError(f"Invalid bounding box for AOI {aoi_id}")
        return tuple(bbox)

    def list_aois(self) -> list[dict[str, Any]]:
        """List all Areas of Interest.

        Returns:
            List of AOI summaries.
        """
        response = self.client.get("/api/areas-of-interest")
        response.raise_for_status()
        return response.json()

    # Assets

    def get_assets(
        self,
        aoi_id: str,
        asset_types: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get assets for an AOI.

        Args:
            aoi_id: The AOI identifier.
            asset_types: Optional list of asset type IDs to filter.

        Returns:
            List of asset dictionaries.
        """
        params = {"aoiId": aoi_id}
        if asset_types:
            params["assetTypes"] = ",".join(str(t) for t in asset_types)

        response = self.client.get("/api/assets", params=params)
        response.raise_for_status()
        return response.json()

    def get_assets_geojson(
        self,
        aoi_id: str,
        asset_types: list[int] | None = None,
    ) -> dict[str, Any]:
        """Get assets as a GeoJSON FeatureCollection.

        Args:
            aoi_id: The AOI identifier.
            asset_types: Optional list of asset type IDs to filter.

        Returns:
            GeoJSON FeatureCollection.
        """
        params = {"aoiId": aoi_id}
        if asset_types:
            params["assetTypes"] = ",".join(str(t) for t in asset_types)

        response = self.client.get("/api/assets/geojson", params=params)
        response.raise_for_status()
        return response.json()

    # Processing Runs

    def create_processing_run(
        self,
        aoi_id: str,
        before_date: str,
        after_date: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new processing run.

        Args:
            aoi_id: The AOI identifier.
            before_date: Before date in ISO format.
            after_date: After date in ISO format.
            parameters: Optional processing parameters.

        Returns:
            Created processing run details.
        """
        payload = {
            "aoiId": aoi_id,
            "beforeDate": before_date,
            "afterDate": after_date,
        }
        if parameters:
            payload["parameters"] = parameters

        response = self.client.post("/api/processing/runs", json=payload)
        response.raise_for_status()
        return response.json()

    def update_processing_run(
        self,
        run_id: str | UUID,
        status: int | None = None,
        before_scene_id: str | None = None,
        after_scene_id: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a processing run.

        Args:
            run_id: The processing run ID.
            status: New status value.
            before_scene_id: Before scene identifier.
            after_scene_id: After scene identifier.
            error_message: Error message if failed.
            metadata: Additional metadata to merge.

        Returns:
            Updated processing run details.
        """
        payload = {}
        if status is not None:
            payload["status"] = status
        if before_scene_id:
            payload["beforeSceneId"] = before_scene_id
        if after_scene_id:
            payload["afterSceneId"] = after_scene_id
        if error_message:
            payload["errorMessage"] = error_message
        if metadata:
            payload["metadata"] = metadata

        response = self.client.put(f"/api/processing/runs/{run_id}", json=payload)
        response.raise_for_status()
        return response.json()

    def get_processing_run(self, run_id: str | UUID) -> dict[str, Any]:
        """Get a processing run by ID.

        Args:
            run_id: The processing run ID.

        Returns:
            Processing run details.
        """
        response = self.client.get(f"/api/processing/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    def get_latest_completed_run(self, aoi_id: str) -> dict[str, Any] | None:
        """Get the latest completed processing run for an AOI.

        Args:
            aoi_id: The AOI identifier.

        Returns:
            Latest completed processing run or None if not found.
        """
        params = {"aoiId": aoi_id, "status": ProcessingStatus.COMPLETED, "limit": 1}
        response = self.client.get("/api/processing/runs", params=params)
        response.raise_for_status()
        runs = response.json()
        return runs[0] if runs else None

    # Change Polygons

    def create_change_polygons(
        self,
        run_id: str | UUID,
        polygons: list[ChangePolygon] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create change polygons for a processing run.

        Args:
            run_id: The processing run ID.
            polygons: List of ChangePolygon objects or dictionaries.

        Returns:
            Bulk creation result.
        """
        polygon_data = [
            p.to_dict() if isinstance(p, ChangePolygon) else p
            for p in polygons
        ]

        payload = {
            "runId": str(run_id),
            "polygons": polygon_data,
        }

        response = self.client.post("/api/changes/bulk", json=payload)
        response.raise_for_status()
        return response.json()

    # Risk Events

    def create_risk_events(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create risk events.

        Args:
            events: List of risk event dictionaries.

        Returns:
            Bulk creation result.
        """
        payload = {"events": events}

        response = self.client.post("/api/risk-events/bulk", json=payload)
        response.raise_for_status()
        return response.json()

    def get_risk_events(
        self,
        aoi_id: str | None = None,
        min_score: int | None = None,
        risk_level: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get risk events with optional filters.

        Args:
            aoi_id: Filter by AOI ID.
            min_score: Minimum risk score.
            risk_level: Filter by risk level.
            limit: Maximum number of results.

        Returns:
            List of risk event dictionaries.
        """
        params = {"limit": limit}
        if aoi_id:
            params["aoiId"] = aoi_id
        if min_score is not None:
            params["minScore"] = min_score
        if risk_level is not None:
            params["riskLevel"] = risk_level

        response = self.client.get("/api/risk-events", params=params)
        response.raise_for_status()
        return response.json()


# Processing status enum values (matching C# enum)
class ProcessingStatus(IntEnum):
    """Processing status values for API updates."""

    PENDING = 0
    FETCHING_IMAGERY = 1
    CALCULATING_NDVI = 2
    DETECTING_CHANGES = 3
    SCORING_RISK = 4
    COMPLETED = 5
    FAILED = 6
