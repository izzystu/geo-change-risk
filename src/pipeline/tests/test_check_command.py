"""Tests for the `check` CLI command (new imagery availability check).

The check command queries the API for an AOI, looks up the latest completed
processing run, searches STAC for new scenes, filters out already-processed
scenes, and reports whether new imagery is available.

All external dependencies (ApiClient, search_scenes) are mocked to avoid
real HTTP and STAC calls.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from georisk.cli import cli
from georisk.stac.search import SceneInfo

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_scene(scene_id: str = "S2B_20240701",
                dt: datetime | None = None,
                cloud_cover: float = 5.0) -> SceneInfo:
    """Build a SceneInfo with sensible defaults."""
    if dt is None:
        dt = datetime(2024, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    return SceneInfo(
        scene_id=scene_id,
        datetime=dt,
        cloud_cover=cloud_cover,
        bbox=(-121.7, 39.7, -121.5, 39.8),
        assets={"B04": {"href": "https://example.com/B04.tif"}},
        platform="Sentinel-2B",
        epsg=32610,
    )


SAMPLE_AOI = {
    "aoiId": "test-aoi-1",
    "name": "Test AOI",
    "boundingBox": [-121.7, 39.7, -121.5, 39.8],
    "maxCloudCover": 20.0,
    "defaultLookbackDays": 90,
}


SAMPLE_LAST_RUN = {
    "runId": "run-001",
    "aoiId": "test-aoi-1",
    "status": 5,
    "afterDate": "2024-06-15T00:00:00Z",
    "beforeDate": "2024-03-15T00:00:00Z",
    "afterSceneId": "SCENE_A",
    "beforeSceneId": "SCENE_B",
}


@pytest.fixture
def runner():
    """Click CliRunner for invoking commands."""
    return CliRunner()


@pytest.fixture
def mock_api():
    """Patch ApiClient used in georisk.cli so no real HTTP calls occur.

    Returns the mock class whose return_value is the mock instance.
    The instance's context-manager methods are wired up so
    ``with ApiClient() as api:`` works.
    """
    with patch("georisk.cli.ApiClient") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)

        # Defaults -- tests can override on the instance
        instance.get_aoi.return_value = SAMPLE_AOI.copy()
        instance.get_latest_completed_run.return_value = None

        yield instance


@pytest.fixture
def mock_search():
    """Patch search_scenes used in georisk.cli."""
    with patch("georisk.cli.search_scenes") as mock:
        yield mock


# ---------------------------------------------------------------------------
# Priority 2: JSON contract tests
# ---------------------------------------------------------------------------

class TestJsonContractNewDataFound:
    """1. JSON output has correct keys when new data found."""

    def test_json_keys_present(self, runner, mock_api, mock_search):
        mock_search.return_value = [_make_scene()]
        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        expected_keys = {
            "new_data", "scene_id", "scene_date",
            "cloud_cover", "recommended_before_date", "recommended_after_date",
        }
        assert expected_keys == set(data.keys())


class TestJsonContractNoNewData:
    """2. JSON output has correct keys when no new data."""

    def test_json_no_new_data_keys(self, runner, mock_api, mock_search):
        mock_search.return_value = []
        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["new_data"] is False


class TestExitCodes:
    """3 & 4. Exit codes for new data / no new data."""

    def test_exit_code_0_when_new_data(self, runner, mock_api, mock_search):
        mock_search.return_value = [_make_scene()]
        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])
        assert result.exit_code == 0

    def test_exit_code_1_when_no_new_data(self, runner, mock_api, mock_search):
        mock_search.return_value = []
        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Priority 3: Scene deduplication tests
# ---------------------------------------------------------------------------

class TestSceneDeduplication:
    """5-8. Filtering out already-processed scenes."""

    def test_after_scene_id_filtered(self, runner, mock_api, mock_search):
        """5. Scenes matching last run's afterSceneId are filtered."""
        mock_api.get_latest_completed_run.return_value = SAMPLE_LAST_RUN.copy()
        scene_a = _make_scene(scene_id="SCENE_A",
                              dt=datetime(2024, 7, 1, tzinfo=timezone.utc))
        scene_b = _make_scene(scene_id="SCENE_B_NEW",
                              dt=datetime(2024, 7, 5, tzinfo=timezone.utc))
        mock_search.return_value = [scene_b, scene_a]  # newest first

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["new_data"] is True
        assert data["scene_id"] == "SCENE_B_NEW"

    def test_before_scene_id_filtered(self, runner, mock_api, mock_search):
        """6. Scenes matching last run's beforeSceneId are filtered."""
        mock_api.get_latest_completed_run.return_value = SAMPLE_LAST_RUN.copy()
        scene_b = _make_scene(scene_id="SCENE_B",  # matches beforeSceneId
                              dt=datetime(2024, 7, 1, tzinfo=timezone.utc))
        scene_c = _make_scene(scene_id="SCENE_C",
                              dt=datetime(2024, 7, 5, tzinfo=timezone.utc))
        mock_search.return_value = [scene_c, scene_b]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["new_data"] is True
        assert data["scene_id"] == "SCENE_C"

    def test_no_previous_run_no_filtering(self, runner, mock_api, mock_search):
        """7. No previous run means no filtering -- all scenes available."""
        mock_api.get_latest_completed_run.return_value = None
        scenes = [
            _make_scene(scene_id="SCENE_X",
                        dt=datetime(2024, 7, 5, tzinfo=timezone.utc)),
            _make_scene(scene_id="SCENE_Y",
                        dt=datetime(2024, 7, 1, tzinfo=timezone.utc)),
        ]
        mock_search.return_value = scenes

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["new_data"] is True
        # Best scene is first (newest)
        assert data["scene_id"] == "SCENE_X"

    def test_all_scenes_filtered_returns_no_data(self, runner, mock_api, mock_search):
        """8. All scenes filtered out returns no new data."""
        mock_api.get_latest_completed_run.return_value = SAMPLE_LAST_RUN.copy()
        # Only return scenes that match the last run's processed IDs
        mock_search.return_value = [
            _make_scene(scene_id="SCENE_A",
                        dt=datetime(2024, 7, 1, tzinfo=timezone.utc)),
        ]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["new_data"] is False
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Priority 3: Date logic tests
# ---------------------------------------------------------------------------

class TestDateLogic:
    """9-12. Since-date derivation and recommended date logic."""

    def test_since_date_is_after_date_plus_one(self, runner, mock_api, mock_search):
        """9. Since date is afterDate + 1 day."""
        last_run = SAMPLE_LAST_RUN.copy()
        last_run["afterDate"] = "2024-06-15T00:00:00Z"
        mock_api.get_latest_completed_run.return_value = last_run
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        # search_scenes should have been called with start_date="2024-06-16"
        call_kwargs = mock_search.call_args
        assert call_kwargs is not None
        # call_args can be (args, kwargs) or just kwargs
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs["start_date"] == "2024-06-16"
        else:
            # positional: bbox, start_date, end_date, ...
            assert call_kwargs[1]["start_date"] == "2024-06-16" or call_kwargs[0][1] == "2024-06-16"

    def test_no_previous_run_defaults_30_day_lookback(self, runner, mock_api, mock_search):
        """10. No previous run defaults to 30-day lookback."""
        mock_api.get_latest_completed_run.return_value = None
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        call_kwargs = mock_search.call_args
        expected_since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        if call_kwargs.kwargs:
            actual_since = call_kwargs.kwargs["start_date"]
        else:
            actual_since = call_kwargs[0][1]
        assert actual_since == expected_since

    def test_recommended_before_date_from_last_run(self, runner, mock_api, mock_search):
        """11. Recommended before date from last run's afterDate."""
        last_run = SAMPLE_LAST_RUN.copy()
        last_run["afterDate"] = "2024-06-15T00:00:00Z"
        mock_api.get_latest_completed_run.return_value = last_run
        mock_search.return_value = [_make_scene(scene_id="NEW_SCENE")]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["recommended_before_date"] == "2024-06-15"

    def test_recommended_before_date_uses_lookback_when_no_last_run(
        self, runner, mock_api, mock_search
    ):
        """12. Recommended before date uses scene_date minus defaultLookbackDays."""
        mock_api.get_latest_completed_run.return_value = None
        aoi = SAMPLE_AOI.copy()
        aoi["defaultLookbackDays"] = 90
        mock_api.get_aoi.return_value = aoi

        scene_dt = datetime(2024, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_search.return_value = [_make_scene(dt=scene_dt)]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        expected = (scene_dt - timedelta(days=90)).strftime("%Y-%m-%d")
        assert data["recommended_before_date"] == expected


# ---------------------------------------------------------------------------
# Priority 2: Additional contract tests
# ---------------------------------------------------------------------------

class TestJsonValueTypes:
    """13. JSON values have correct types."""

    def test_value_types(self, runner, mock_api, mock_search):
        mock_search.return_value = [_make_scene(cloud_cover=12.5)]
        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)

        assert isinstance(data["new_data"], bool)
        assert isinstance(data["cloud_cover"], float)
        # Dates should be YYYY-MM-DD strings
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", data["scene_date"])
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", data["recommended_before_date"])
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", data["recommended_after_date"])

    def test_no_data_value_types(self, runner, mock_api, mock_search):
        mock_search.return_value = []
        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert isinstance(data["new_data"], bool)
        assert data["new_data"] is False


class TestCliOptionOverrides:
    """14-15. CLI option overrides for cloud cover and since date."""

    def test_max_cloud_overrides_aoi_setting(self, runner, mock_api, mock_search):
        """14. Custom --max-cloud overrides AOI maxCloudCover setting."""
        aoi = SAMPLE_AOI.copy()
        aoi["maxCloudCover"] = 20.0
        mock_api.get_aoi.return_value = aoi
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, ["check", "--aoi-id", "test", "--max-cloud", "10", "--json"])

        call_kwargs = mock_search.call_args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs["max_cloud_cover"] == 10.0
        else:
            # Keyword args mixed in: check named params
            _, kwargs = call_kwargs
            assert kwargs["max_cloud_cover"] == 10.0

    def test_since_overrides_last_run_date(self, runner, mock_api, mock_search):
        """15. --since overrides last run date."""
        last_run = SAMPLE_LAST_RUN.copy()
        last_run["afterDate"] = "2024-06-15T00:00:00Z"
        mock_api.get_latest_completed_run.return_value = last_run
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, [
            "check", "--aoi-id", "test", "--since", "2024-01-01", "--json",
        ])

        call_kwargs = mock_search.call_args
        if call_kwargs.kwargs:
            actual_since = call_kwargs.kwargs["start_date"]
        else:
            actual_since = call_kwargs[0][1]
        assert actual_since == "2024-01-01"

    def test_since_skips_get_latest_completed_run(self, runner, mock_api, mock_search):
        """When --since is provided, get_latest_completed_run should NOT be called."""
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, [
            "check", "--aoi-id", "test", "--since", "2024-01-01", "--json",
        ])

        mock_api.get_latest_completed_run.assert_not_called()

    def test_aoi_max_cloud_used_when_no_override(self, runner, mock_api, mock_search):
        """Without --max-cloud, the AOI's maxCloudCover should be used."""
        aoi = SAMPLE_AOI.copy()
        aoi["maxCloudCover"] = 15.0
        mock_api.get_aoi.return_value = aoi
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        call_kwargs = mock_search.call_args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs["max_cloud_cover"] == 15.0
        else:
            _, kwargs = call_kwargs
            assert kwargs["max_cloud_cover"] == 15.0


# ---------------------------------------------------------------------------
# Non-JSON (human-readable) output tests
# ---------------------------------------------------------------------------

class TestHumanReadableOutput:
    """Verify the human-readable (non-JSON) output format."""

    def test_new_imagery_message(self, runner, mock_api, mock_search):
        mock_search.return_value = [_make_scene(scene_id="S2B_20240701", cloud_cover=5.0)]
        result = runner.invoke(cli, ["check", "--aoi-id", "test"])

        assert "New imagery available!" in result.output
        assert "S2B_20240701" in result.output

    def test_no_imagery_message(self, runner, mock_api, mock_search):
        mock_search.return_value = []
        result = runner.invoke(cli, ["check", "--aoi-id", "test"])

        assert "No new imagery found" in result.output

    def test_since_date_displayed(self, runner, mock_api, mock_search):
        mock_search.return_value = [_make_scene()]
        result = runner.invoke(cli, ["check", "--aoi-id", "test"])

        assert "Checking for new imagery since" in result.output


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify error paths produce exit code 2 and proper error output."""

    def test_api_error_exit_code_2(self, runner, mock_api, mock_search):
        """An exception from ApiClient should produce exit code 2."""
        mock_api.get_aoi.side_effect = Exception("Connection refused")

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        assert result.exit_code == 2

    def test_api_error_json_output(self, runner, mock_api, mock_search):
        """JSON error output should contain new_data=false and error message."""
        mock_api.get_aoi.side_effect = Exception("Connection refused")

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["new_data"] is False
        assert "error" in data
        assert "Connection refused" in data["error"]

    def test_stac_error_exit_code_2(self, runner, mock_api, mock_search):
        """An exception from search_scenes should produce exit code 2."""
        mock_search.side_effect = Exception("STAC timeout")

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Scene selection tests
# ---------------------------------------------------------------------------

class TestSceneSelection:
    """Verify the best scene is the first (newest) in the sorted list."""

    def test_best_scene_is_newest(self, runner, mock_api, mock_search):
        """The best scene should be the first scene (newest, since sorted desc)."""
        older = _make_scene(scene_id="OLD",
                            dt=datetime(2024, 6, 25, tzinfo=timezone.utc),
                            cloud_cover=3.0)
        newer = _make_scene(scene_id="NEW",
                            dt=datetime(2024, 7, 5, tzinfo=timezone.utc),
                            cloud_cover=8.0)
        # search_scenes returns them sorted newest-first
        mock_search.return_value = [newer, older]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["scene_id"] == "NEW"

    def test_scene_date_matches_best_scene(self, runner, mock_api, mock_search):
        scene_dt = datetime(2024, 7, 10, 12, 30, 0, tzinfo=timezone.utc)
        mock_search.return_value = [_make_scene(dt=scene_dt)]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["scene_date"] == "2024-07-10"
        assert data["recommended_after_date"] == "2024-07-10"

    def test_cloud_cover_from_best_scene(self, runner, mock_api, mock_search):
        mock_search.return_value = [_make_scene(cloud_cover=7.3)]

        result = runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        data = json.loads(result.output)
        assert data["cloud_cover"] == 7.3


# ---------------------------------------------------------------------------
# Bounding box pass-through test
# ---------------------------------------------------------------------------

class TestBboxPassthrough:
    """Verify the AOI bounding box is passed to search_scenes."""

    def test_bbox_passed_to_search(self, runner, mock_api, mock_search):
        aoi = SAMPLE_AOI.copy()
        aoi["boundingBox"] = [-122.0, 39.0, -121.0, 40.0]
        mock_api.get_aoi.return_value = aoi
        mock_search.return_value = [_make_scene()]

        runner.invoke(cli, ["check", "--aoi-id", "test", "--json"])

        call_kwargs = mock_search.call_args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs["bbox"] == (-122.0, 39.0, -121.0, 40.0)
        else:
            assert call_kwargs[0][0] == (-122.0, 39.0, -121.0, 40.0)
