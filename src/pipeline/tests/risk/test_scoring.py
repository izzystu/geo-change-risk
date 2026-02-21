"""Tests for the risk scoring module."""

import pytest
from shapely.geometry import Point, Polygon

from georisk.raster.change import ChangePolygon
from georisk.risk.proximity import ProximityResult
from georisk.risk.scoring import RiskScore, RiskScorer, ScoringFactor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_change(**overrides) -> ChangePolygon:
    """Build a ChangePolygon with sensible defaults, applying any overrides."""
    defaults = dict(
        geometry=Polygon([
            (-121.6, 39.75), (-121.59, 39.75),
            (-121.59, 39.76), (-121.6, 39.76), (-121.6, 39.75),
        ]),
        area_sq_meters=15000,
        ndvi_drop_mean=-0.35,
        ndvi_drop_max=-0.55,
        change_type="VegetationLoss",
        slope_degree_mean=22.0,
        slope_degree_max=35.0,
        aspect_degrees=180.0,
        elevation_m=850.0,
    )
    defaults.update(overrides)
    return ChangePolygon(**defaults)


def _make_proximity(**overrides) -> ProximityResult:
    """Build a ProximityResult with sensible defaults, applying any overrides."""
    defaults = dict(
        asset_id="asset-001",
        asset_name="Test Building",
        asset_type=0,
        asset_type_name="Building",
        criticality=1,
        criticality_name="Medium",
        distance_meters=250.0,
        asset_geometry=Point(-121.595, 39.755),
        asset_elevation_m=800.0,
        elevation_diff_m=50.0,
        is_upslope=True,
        slope_toward_asset_deg=5.0,
    )
    defaults.update(overrides)
    return ProximityResult(**defaults)


# ---------------------------------------------------------------------------
# Distance scoring
# ---------------------------------------------------------------------------

class TestDistanceScoring:
    """Tests for RiskScorer._score_distance."""

    @pytest.mark.parametrize(
        "distance, expected_points, expected_reason",
        [
            (50, 28, "DISTANCE_LT_100M"),
            (99, 28, "DISTANCE_LT_100M"),
            (100, 21, "DISTANCE_LT_500M"),
            (250, 21, "DISTANCE_LT_500M"),
            (499, 21, "DISTANCE_LT_500M"),
            (500, 14, "DISTANCE_LT_1KM"),
            (750, 14, "DISTANCE_LT_1KM"),
            (999, 14, "DISTANCE_LT_1KM"),
            (1000, 7, "DISTANCE_LT_2.5KM"),
            (2000, 7, "DISTANCE_LT_2.5KM"),
            (2499, 7, "DISTANCE_LT_2.5KM"),
            (2500, 0, "DISTANCE_FAR"),
            (5000, 0, "DISTANCE_FAR"),
        ],
        ids=[
            "very_close_50m",
            "just_under_100m",
            "exactly_100m",
            "mid_range_250m",
            "just_under_500m",
            "exactly_500m",
            "mid_range_750m",
            "just_under_1000m",
            "exactly_1000m",
            "mid_range_2000m",
            "just_under_2500m",
            "exactly_2500m",
            "far_5000m",
        ],
    )
    def test_distance_thresholds(self, distance, expected_points, expected_reason):
        scorer = RiskScorer()
        factor = scorer._score_distance(distance)

        assert factor.points == expected_points
        assert factor.reason_code == expected_reason
        assert factor.name == "Distance"
        assert factor.max_points == 28

    def test_distance_zero(self):
        scorer = RiskScorer()
        factor = scorer._score_distance(0)
        assert factor.points == 28
        assert factor.reason_code == "DISTANCE_LT_100M"


# ---------------------------------------------------------------------------
# NDVI drop scoring
# ---------------------------------------------------------------------------

class TestNdviScoring:
    """Tests for RiskScorer._score_ndvi."""

    @pytest.mark.parametrize(
        "ndvi_drop, expected_points, expected_reason",
        [
            (-0.60, 25, "NDVI_DROP_SEVERE"),
            (-0.50, 25, "NDVI_DROP_SEVERE"),
            (-0.45, 20, "NDVI_DROP_STRONG"),
            (-0.40, 20, "NDVI_DROP_STRONG"),
            (-0.35, 15, "NDVI_DROP_MODERATE"),
            (-0.30, 15, "NDVI_DROP_MODERATE"),
            (-0.25, 10, "NDVI_DROP_MILD"),
            (-0.20, 10, "NDVI_DROP_MILD"),
            (-0.15, 0, "NDVI_DROP_MINIMAL"),
            (-0.10, 0, "NDVI_DROP_MINIMAL"),
            (0.0, 0, "NDVI_DROP_MINIMAL"),
        ],
        ids=[
            "severe_-0.60",
            "boundary_-0.50",
            "strong_-0.45",
            "boundary_-0.40",
            "moderate_-0.35",
            "boundary_-0.30",
            "mild_-0.25",
            "boundary_-0.20",
            "below_threshold_-0.15",
            "minimal_-0.10",
            "no_drop",
        ],
    )
    def test_ndvi_thresholds(self, ndvi_drop, expected_points, expected_reason):
        scorer = RiskScorer()
        factor = scorer._score_ndvi(ndvi_drop)

        assert factor.points == expected_points
        assert factor.reason_code == expected_reason
        assert factor.name == "NDVI Drop"
        assert factor.max_points == 25


# ---------------------------------------------------------------------------
# Area scoring
# ---------------------------------------------------------------------------

class TestAreaScoring:
    """Tests for RiskScorer._score_area."""

    @pytest.mark.parametrize(
        "area_m2, expected_points, expected_reason",
        [
            (100000, 15, "LARGE_AREA_GT_50000M2"),
            (50000, 15, "LARGE_AREA_GT_50000M2"),
            (30000, 11, "LARGE_AREA_GT_25000M2"),
            (25000, 11, "LARGE_AREA_GT_25000M2"),
            (15000, 8, "AREA_GT_10000M2"),
            (10000, 8, "AREA_GT_10000M2"),
            (7000, 4, "AREA_GT_5000M2"),
            (5000, 4, "AREA_GT_5000M2"),
            (4999, 0, "AREA_SMALL"),
            (1000, 0, "AREA_SMALL"),
            (0, 0, "AREA_SMALL"),
        ],
        ids=[
            "very_large_100k",
            "boundary_50k",
            "large_30k",
            "boundary_25k",
            "medium_15k",
            "boundary_10k",
            "small_7k",
            "boundary_5k",
            "just_under_5k",
            "tiny_1k",
            "zero_area",
        ],
    )
    def test_area_thresholds(self, area_m2, expected_points, expected_reason):
        scorer = RiskScorer()
        factor = scorer._score_area(area_m2)

        assert factor.points == expected_points
        assert factor.reason_code == expected_reason
        assert factor.name == "Area"
        assert factor.max_points == 15


# ---------------------------------------------------------------------------
# Directional slope scoring
# ---------------------------------------------------------------------------

class TestDirectionalSlopeScoring:
    """Tests for RiskScorer._score_directional_slope."""

    def test_upslope_increases_score(self):
        """Positive elevation_diff (change is upslope) should multiply the base score."""
        scorer = RiskScorer()
        # slope_deg=22 gives base 7 points (SLOPE_GT_20DEG)
        factor = scorer._score_directional_slope(slope_deg=22.0, elevation_diff_m=50.0)

        assert factor.points > 7, "Upslope modifier should increase beyond base points"
        assert factor.reason_code == "SLOPE_UPSLOPE"
        assert factor.name == "Slope + Direction"

    def test_downslope_decreases_score(self):
        """Negative elevation_diff (change is downslope) should reduce the base score."""
        scorer = RiskScorer()
        factor = scorer._score_directional_slope(slope_deg=22.0, elevation_diff_m=-50.0)

        assert factor.points < 7, "Downslope modifier should reduce below base points"
        assert factor.reason_code == "SLOPE_DOWNSLOPE"

    def test_no_elevation_data_returns_base(self):
        """When elevation_diff_m is None, the base slope score is returned unmodified."""
        scorer = RiskScorer()
        factor = scorer._score_directional_slope(slope_deg=22.0, elevation_diff_m=None)

        assert factor.points == 7
        assert factor.reason_code == "SLOPE_GT_20DEG"
        assert factor.name == "Slope"

    def test_level_terrain_returns_base(self):
        """Elevation diff within the threshold (+/-5m) should return the base score."""
        scorer = RiskScorer()
        factor = scorer._score_directional_slope(slope_deg=22.0, elevation_diff_m=3.0)

        assert factor.points == 7
        assert factor.reason_code == "SLOPE_LEVEL"

    def test_steep_upslope_caps_at_max(self):
        """Very steep upslope score must not exceed max_points (20)."""
        scorer = RiskScorer()
        factor = scorer._score_directional_slope(slope_deg=35.0, elevation_diff_m=200.0)

        assert factor.points <= 20
        assert factor.max_points == 20

    def test_flat_slope_with_upslope_diff(self):
        """A flat slope (0 deg) multiplied by upslope modifier still yields 0."""
        scorer = RiskScorer()
        factor = scorer._score_directional_slope(slope_deg=2.0, elevation_diff_m=50.0)

        # base_points is 0 for slope < 10 deg, 0 * multiplier = 0
        assert factor.points == 0

    @pytest.mark.parametrize(
        "slope_deg, expected_base_points",
        [
            (35, 10),
            (30, 10),
            (25, 7),
            (20, 7),
            (17, 5),
            (15, 5),
            (12, 3),
            (10, 3),
            (8, 0),
            (0, 0),
        ],
        ids=[
            "steep_35",
            "boundary_30",
            "moderate_25",
            "boundary_20",
            "mild_17",
            "boundary_15",
            "gentle_12",
            "boundary_10",
            "nearly_flat_8",
            "flat_0",
        ],
    )
    def test_base_slope_thresholds_via_no_elevation(self, slope_deg, expected_base_points):
        """Verify the base slope points by passing elevation_diff_m=None."""
        scorer = RiskScorer()
        factor = scorer._score_directional_slope(slope_deg, elevation_diff_m=None)
        assert factor.points == expected_base_points


# ---------------------------------------------------------------------------
# Aspect scoring
# ---------------------------------------------------------------------------

class TestAspectScoring:
    """Tests for RiskScorer._score_aspect."""

    @pytest.mark.parametrize(
        "aspect, expected_points, expected_reason",
        [
            (180.0, 5, "ASPECT_SOUTH"),
            (170.0, 5, "ASPECT_SOUTH"),
            (200.0, 5, "ASPECT_SOUTH"),
            (140.0, 4, "ASPECT_SE"),
            (210.0, 4, "ASPECT_SW"),
            (120.0, 2, "ASPECT_EAST"),
            (230.0, 2, "ASPECT_WEST"),
            (45.0, 1, "ASPECT_NE"),
            (315.0, 1, "ASPECT_NW"),
            (0.0, 0, "ASPECT_NORTH"),
            (10.0, 0, "ASPECT_NORTH"),
            (350.0, 0, "ASPECT_NORTH"),
        ],
        ids=[
            "south_180",
            "south_170",
            "south_200",
            "southeast_140",
            "southwest_210",
            "east_adjacent_120",
            "west_adjacent_230",
            "northeast_45",
            "northwest_315",
            "north_0",
            "north_10",
            "north_350",
        ],
    )
    def test_aspect_ranges(self, aspect, expected_points, expected_reason):
        scorer = RiskScorer()
        factor = scorer._score_aspect(aspect)

        assert factor.points == expected_points
        assert factor.reason_code == expected_reason
        assert factor.name == "Aspect"
        assert factor.max_points == 5

    def test_aspect_wraps_around_360(self):
        """An aspect of 370 degrees should be treated as 10 degrees (North)."""
        scorer = RiskScorer()
        factor = scorer._score_aspect(370.0)
        assert factor.points == 0
        assert factor.reason_code == "ASPECT_NORTH"


# ---------------------------------------------------------------------------
# Risk level classification
# ---------------------------------------------------------------------------

class TestRiskLevelClassification:
    """Tests for RiskScorer._get_risk_level."""

    @pytest.mark.parametrize(
        "score, expected_level",
        [
            (0, "Low"),
            (10, "Low"),
            (24, "Low"),
            (25, "Medium"),
            (30, "Medium"),
            (49, "Medium"),
            (50, "High"),
            (60, "High"),
            (74, "High"),
            (75, "Critical"),
            (80, "Critical"),
            (100, "Critical"),
        ],
        ids=[
            "low_0",
            "low_10",
            "low_boundary_24",
            "medium_boundary_25",
            "medium_30",
            "medium_boundary_49",
            "high_boundary_50",
            "high_60",
            "high_boundary_74",
            "critical_boundary_75",
            "critical_80",
            "critical_100",
        ],
    )
    def test_risk_levels(self, score, expected_level):
        scorer = RiskScorer()
        assert scorer._get_risk_level(score) == expected_level

    def test_risk_level_above_100_is_unknown(self):
        """Scores above 100 fall outside all defined ranges."""
        scorer = RiskScorer()
        assert scorer._get_risk_level(101) == "Unknown"


# ---------------------------------------------------------------------------
# Full integration: calculate_risk_score
# ---------------------------------------------------------------------------

class TestCalculateRiskScore:
    """Integration tests for RiskScorer.calculate_risk_score."""

    def test_returns_risk_score_object(self, sample_change_polygon, sample_proximity_result):
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        assert isinstance(result, RiskScore)

    def test_score_is_int_in_range(self, sample_change_polygon, sample_proximity_result):
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_level_is_valid_string(self, sample_change_polygon, sample_proximity_result):
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        assert result.level in {"Low", "Medium", "High", "Critical"}

    def test_factors_list_is_populated(self, sample_change_polygon, sample_proximity_result):
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        assert len(result.factors) > 0
        for f in result.factors:
            assert isinstance(f, ScoringFactor)
            assert isinstance(f.name, str)
            assert isinstance(f.points, int)
            assert isinstance(f.max_points, int)

    def test_scoring_factors_dict_structure(self, sample_change_polygon, sample_proximity_result):
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        d = result.scoring_factors_dict
        assert "total_score" in d
        assert "risk_level" in d
        assert "factors" in d
        assert isinstance(d["factors"], list)
        assert d["total_score"] == result.score
        assert d["risk_level"] == result.level
        for entry in d["factors"]:
            assert set(entry.keys()) == {"name", "points", "max_points", "reason_code", "details"}

    def test_expected_factor_names(self, sample_change_polygon, sample_proximity_result):
        """With terrain data available, all factor types should be present."""
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        factor_names = [f.name for f in result.factors]
        assert "Distance" in factor_names
        assert "NDVI Drop" in factor_names
        assert "Area" in factor_names
        assert "Slope + Direction" in factor_names
        assert "Aspect" in factor_names
        assert "Criticality" in factor_names

    def test_score_breakdown_is_consistent(self, sample_change_polygon, sample_proximity_result):
        """The total score should equal the sum of factor points times criticality.

        The Land Cover factor (if present) is a multiplicative adjustment already
        folded into total_score before criticality is applied, so we exclude both
        Land Cover and Criticality when reconstructing the expected score.
        """
        scorer = RiskScorer()
        result = scorer.calculate_risk_score(sample_change_polygon, sample_proximity_result)

        # Sum all factors except Criticality and Land Cover (which are multipliers, not additive)
        base_factors = [f for f in result.factors if f.name not in ("Criticality", "Land Cover")]
        base_sum = sum(f.points for f in base_factors)

        # Apply land cover multiplier if present
        lc_factor = next((f for f in result.factors if f.name == "Land Cover"), None)
        if lc_factor is not None:
            base_sum = base_sum + lc_factor.points  # lc_factor.points is the delta

        # Criticality multiplier for criticality=2 is 1.5
        expected_score = min(100, int(base_sum * 1.5))
        assert result.score == expected_score


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------

class TestCustomConfig:
    """Test that custom configuration overrides default scoring."""

    def test_custom_distance_thresholds(self):
        custom = {
            "scoring_factors": {
                "distance": {
                    "max_points": 50,
                    "thresholds": [
                        {"distance_m": 200, "points": 50, "reason_code": "CUSTOM_CLOSE"},
                        {"distance_m": 1000, "points": 25, "reason_code": "CUSTOM_MID"},
                    ],
                },
            },
        }
        scorer = RiskScorer(config=custom)

        close = scorer._score_distance(100)
        assert close.points == 50
        assert close.reason_code == "CUSTOM_CLOSE"
        assert close.max_points == 50

        mid = scorer._score_distance(500)
        assert mid.points == 25

    def test_custom_config_changes_distance_scoring(self):
        """A config that changes distance thresholds should be reflected in scoring."""
        scorer = RiskScorer(config={
            "scoring_factors": {
                "distance": {
                    "max_points": 50,
                    "thresholds": [
                        {"distance_m": 500, "points": 50, "reason_code": "CUSTOM_CLOSE"},
                    ],
                },
            },
        })

        change = _make_change(
            ndvi_drop_mean=-0.1,
            area_sq_meters=1000,
            slope_degree_mean=None,
            aspect_degrees=None,
        )
        proximity = _make_proximity(
            distance_meters=250.0,
            criticality=1,
            criticality_name="Medium",
            elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)

        # Distance factor should use custom 50 points, not default 21
        distance_factor = next(f for f in result.factors if f.name == "Distance")
        assert distance_factor.points == 50
        assert distance_factor.reason_code == "CUSTOM_CLOSE"


# ---------------------------------------------------------------------------
# Criticality multiplier
# ---------------------------------------------------------------------------

class TestCriticalityMultiplier:
    """Test that asset criticality affects the final score."""

    def test_higher_criticality_increases_score(self):
        scorer = RiskScorer()
        # Use modest base scores so multipliers don't all cap at 100
        change = _make_change(
            ndvi_drop_mean=-0.25,
            area_sq_meters=6000,
            slope_degree_mean=None,
            aspect_degrees=None,
        )

        low_crit = _make_proximity(criticality=0, criticality_name="Low", elevation_diff_m=None)
        med_crit = _make_proximity(criticality=1, criticality_name="Medium", elevation_diff_m=None)
        high_crit = _make_proximity(criticality=2, criticality_name="High", elevation_diff_m=None)
        crit_crit = _make_proximity(
            criticality=3, criticality_name="Critical",
            elevation_diff_m=None,
        )

        score_low = scorer.calculate_risk_score(change, low_crit).score
        score_med = scorer.calculate_risk_score(change, med_crit).score
        score_high = scorer.calculate_risk_score(change, high_crit).score
        score_crit = scorer.calculate_risk_score(change, crit_crit).score

        assert score_low < score_med < score_high < score_crit

    @pytest.mark.parametrize(
        "criticality, multiplier",
        [
            (0, 0.5),
            (1, 1.0),
            (2, 1.5),
            (3, 2.0),
        ],
        ids=["low_0.5x", "medium_1.0x", "high_1.5x", "critical_2.0x"],
    )
    def test_criticality_multiplier_values(self, criticality, multiplier):
        """Verify the exact multiplier applied for each criticality level."""
        scorer = RiskScorer()
        change = _make_change()
        proximity = _make_proximity(criticality=criticality, criticality_name="Test")

        result = scorer.calculate_risk_score(change, proximity)

        # Manually compute expected base sum
        base_factors = [f for f in result.factors if f.name != "Criticality"]
        base_sum = sum(f.points for f in base_factors)

        expected = min(100, int(base_sum * multiplier))
        assert result.score == expected

    def test_score_capped_at_100(self):
        """Even with high criticality the score should never exceed 100."""
        scorer = RiskScorer()
        # Very close, severe NDVI, large area, steep upslope, south-facing
        change = _make_change(
            area_sq_meters=100000,
            ndvi_drop_mean=-0.7,
            slope_degree_mean=35.0,
            aspect_degrees=180.0,
        )
        proximity = _make_proximity(
            distance_meters=10,
            criticality=3,
            criticality_name="Critical",
            elevation_diff_m=200.0,
        )
        result = scorer.calculate_risk_score(change, proximity)
        assert result.score <= 100


# ---------------------------------------------------------------------------
# Edge cases: missing terrain data
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test behavior when optional terrain fields are missing."""

    def test_no_slope_data_skips_slope_factor(self):
        """When slope_degree_mean is None, no slope factor should appear."""
        scorer = RiskScorer()
        change = _make_change(slope_degree_mean=None, slope_degree_max=None)
        proximity = _make_proximity()

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]

        assert "Slope + Direction" not in factor_names
        assert "Slope" not in factor_names

    def test_no_aspect_data_skips_aspect_factor(self):
        """When aspect_degrees is None, no aspect factor should appear."""
        scorer = RiskScorer()
        change = _make_change(aspect_degrees=None)
        proximity = _make_proximity()

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]

        assert "Aspect" not in factor_names

    def test_no_terrain_at_all(self):
        """No slope and no aspect -- only distance, NDVI, area, and criticality."""
        scorer = RiskScorer()
        change = _make_change(slope_degree_mean=None, slope_degree_max=None, aspect_degrees=None)
        proximity = _make_proximity()

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]

        assert set(factor_names) == {"Distance", "NDVI Drop", "Area", "Criticality"}

    def test_all_minimal_values_gives_low_risk(self):
        """Very small, far away change with minimal NDVI drop should be Low risk."""
        scorer = RiskScorer()
        change = _make_change(
            area_sq_meters=100,
            ndvi_drop_mean=-0.05,
            slope_degree_mean=None,
            aspect_degrees=None,
        )
        proximity = _make_proximity(
            distance_meters=5000,
            criticality=0,
            criticality_name="Low",
            elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)
        assert result.level == "Low"
        assert result.score == 0

    def test_all_maximal_values_gives_critical_risk(self):
        """Close, severe, large, steep, south-facing, critical asset should be Critical."""
        scorer = RiskScorer()
        change = _make_change(
            area_sq_meters=100000,
            ndvi_drop_mean=-0.8,
            slope_degree_mean=40.0,
            aspect_degrees=180.0,
        )
        proximity = _make_proximity(
            distance_meters=10,
            criticality=3,
            criticality_name="Critical",
            elevation_diff_m=200.0,
        )

        result = scorer.calculate_risk_score(change, proximity)
        assert result.level == "Critical"
        assert result.score >= 75


# ---------------------------------------------------------------------------
# Land cover multiplier
# ---------------------------------------------------------------------------

class TestLandCoverMultiplier:
    """Tests for land cover risk multiplier in scoring."""

    @pytest.mark.parametrize(
        "land_cover, expected_multiplier",
        [
            ("Forest", 1.0),
            ("Residential", 0.9),
            ("HerbaceousVegetation", 0.85),
            ("River", 0.8),
            ("PermanentCrop", 0.75),
            ("Pasture", 0.7),
            ("Industrial", 0.5),
            ("SeaLake", 0.4),
            ("AnnualCrop", 0.3),
            ("Highway", 0.25),
        ],
        ids=[
            "forest_1.0x",
            "residential_0.9x",
            "herbaceous_0.85x",
            "river_0.8x",
            "permanent_crop_0.75x",
            "pasture_0.7x",
            "industrial_0.5x",
            "sea_lake_0.4x",
            "annual_crop_0.3x",
            "highway_0.25x",
        ],
    )
    def test_multiplier_values(self, land_cover, expected_multiplier):
        scorer = RiskScorer()
        assert scorer._get_land_cover_multiplier(land_cover) == expected_multiplier

    def test_none_returns_neutral(self):
        """No land cover class means neutral 1.0x multiplier."""
        scorer = RiskScorer()
        assert scorer._get_land_cover_multiplier(None) == 1.0

    def test_unknown_class_returns_neutral(self):
        """An unrecognized class name defaults to 1.0x."""
        scorer = RiskScorer()
        assert scorer._get_land_cover_multiplier("UnknownClass") == 1.0

    def test_forest_does_not_change_score(self):
        """Forest (1.0x) should produce the same score as no land cover."""
        scorer = RiskScorer()
        change_none = _make_change(slope_degree_mean=None, aspect_degrees=None)
        change_forest = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="Forest",
        )
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        score_none = scorer.calculate_risk_score(change_none, proximity).score
        score_forest = scorer.calculate_risk_score(change_forest, proximity).score
        assert score_none == score_forest

    def test_annual_crop_reduces_score(self):
        """AnnualCrop (0.3x) should significantly reduce the score vs Forest."""
        scorer = RiskScorer()
        change_forest = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="Forest",
        )
        change_crop = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="AnnualCrop",
        )
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        score_forest = scorer.calculate_risk_score(change_forest, proximity).score
        score_crop = scorer.calculate_risk_score(change_crop, proximity).score
        assert score_crop < score_forest

    def test_land_cover_factor_appears_when_class_set(self):
        """A 'Land Cover' factor should appear when land_cover_class is set."""
        scorer = RiskScorer()
        change = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="AnnualCrop",
        )
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]
        assert "Land Cover" in factor_names

    def test_land_cover_factor_absent_when_class_is_none(self):
        """No 'Land Cover' factor when land_cover_class is None."""
        scorer = RiskScorer()
        change = _make_change(slope_degree_mean=None, aspect_degrees=None)
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]
        assert "Land Cover" not in factor_names

    def test_forest_factor_recorded_for_transparency(self):
        """Forest (1.0x) should still record a factor with 0 points."""
        scorer = RiskScorer()
        change = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="Forest",
        )
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)
        lc_factor = next(f for f in result.factors if f.name == "Land Cover")
        assert lc_factor.points == 0
        assert lc_factor.reason_code == "LANDCOVER_FOREST"

    def test_land_cover_applied_before_criticality(self):
        """Land cover multiplier adjusts the base score before criticality."""
        scorer = RiskScorer()
        change = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="AnnualCrop",
        )
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)

        # Additive base: Distance + NDVI + Area (no slope, no aspect)
        additive_factors = [f for f in result.factors
                           if f.name not in ("Criticality", "Land Cover")]
        additive_sum = sum(f.points for f in additive_factors)

        # AnnualCrop = 0.3x, Medium criticality = 1.0x
        expected = min(100, int(int(additive_sum * 0.3) * 1.0))
        assert result.score == expected

    def test_land_cover_and_criticality_compound(self):
        """Both multipliers should compound: base * lc * criticality."""
        scorer = RiskScorer()
        change = _make_change(
            slope_degree_mean=None, aspect_degrees=None, land_cover_class="Pasture",
        )
        proximity = _make_proximity(
            criticality=2, criticality_name="High", elevation_diff_m=None,
        )

        result = scorer.calculate_risk_score(change, proximity)

        additive_factors = [f for f in result.factors
                           if f.name not in ("Criticality", "Land Cover")]
        additive_sum = sum(f.points for f in additive_factors)

        # Pasture = 0.7x, High criticality = 1.5x
        after_lc = int(additive_sum * 0.7)
        expected = min(100, int(after_lc * 1.5))
        assert result.score == expected

    def test_ordering_forest_gt_crop_gt_highway(self):
        """Forest should score higher than Crop, which should score higher than Highway."""
        scorer = RiskScorer()
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=None,
        )

        scores = {}
        for lc in ["Forest", "AnnualCrop", "Highway"]:
            change = _make_change(
                slope_degree_mean=None, aspect_degrees=None, land_cover_class=lc,
            )
            scores[lc] = scorer.calculate_risk_score(change, proximity).score

        assert scores["Forest"] > scores["AnnualCrop"] >= scores["Highway"]


# ---------------------------------------------------------------------------
# Landslide scoring
# ---------------------------------------------------------------------------

class TestLandslideScoring:
    """Tests for the landslide detection multiplier in scoring."""

    def test_landslide_scores_higher_than_vegetation_loss(self):
        """A LandslideDebris polygon should score higher than an equivalent VegetationLoss."""
        scorer = RiskScorer()
        proximity = _make_proximity(
            criticality=1, criticality_name="Medium", elevation_diff_m=50.0,
        )

        change_veg = _make_change(change_type="VegetationLoss")
        change_ls = _make_change(change_type="LandslideDebris")

        score_veg = scorer.calculate_risk_score(change_veg, proximity).score
        score_ls = scorer.calculate_risk_score(change_ls, proximity).score

        assert score_ls > score_veg

    def test_upslope_landslide_scores_higher_than_level(self):
        """An upslope landslide should score higher than one on level terrain."""
        scorer = RiskScorer()

        # Use low base values so compounding multipliers don't both cap at 100
        change = _make_change(
            change_type="LandslideDebris",
            ndvi_drop_mean=-0.15,  # Below threshold = 0 points
            area_sq_meters=3000,   # Below threshold = 0 points
            slope_degree_mean=16.0,
            aspect_degrees=None,
        )

        prox_upslope = _make_proximity(
            distance_meters=800.0,
            criticality=0, criticality_name="Low",
            elevation_diff_m=50.0,
        )
        prox_level = _make_proximity(
            distance_meters=800.0,
            criticality=0, criticality_name="Low",
            elevation_diff_m=0.0,
        )

        score_upslope = scorer.calculate_risk_score(change, prox_upslope).score
        score_level = scorer.calculate_risk_score(change, prox_level).score

        assert score_upslope > score_level

    def test_non_landslide_has_no_landslide_factor(self):
        """VegetationLoss polygons should not have a 'Landslide Detection' factor."""
        scorer = RiskScorer()
        change = _make_change(change_type="VegetationLoss")
        proximity = _make_proximity()

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]

        assert "Landslide Detection" not in factor_names

    def test_landslide_factor_present(self):
        """LandslideDebris polygons should have a 'Landslide Detection' factor."""
        scorer = RiskScorer()
        change = _make_change(change_type="LandslideDebris")
        proximity = _make_proximity(elevation_diff_m=50.0)

        result = scorer.calculate_risk_score(change, proximity)
        factor_names = [f.name for f in result.factors]

        assert "Landslide Detection" in factor_names

    def test_landslide_factor_reason_code_upslope(self):
        """Upslope landslide should have LANDSLIDE_UPSLOPE reason code."""
        scorer = RiskScorer()
        change = _make_change(change_type="LandslideDebris")
        proximity = _make_proximity(elevation_diff_m=50.0)

        result = scorer.calculate_risk_score(change, proximity)
        ls_factor = next(f for f in result.factors if f.name == "Landslide Detection")

        assert ls_factor.reason_code == "LANDSLIDE_UPSLOPE"

    def test_landslide_factor_reason_code_detected(self):
        """Level-terrain landslide should have LANDSLIDE_DETECTED reason code."""
        scorer = RiskScorer()
        change = _make_change(change_type="LandslideDebris")
        proximity = _make_proximity(elevation_diff_m=0.0)

        result = scorer.calculate_risk_score(change, proximity)
        ls_factor = next(f for f in result.factors if f.name == "Landslide Detection")

        assert ls_factor.reason_code == "LANDSLIDE_DETECTED"

    def test_low_slope_landslide_has_zero_points(self):
        """Landslide on gentle slope should record factor but with 0 points."""
        scorer = RiskScorer()
        change = _make_change(
            change_type="LandslideDebris",
            slope_degree_mean=10.0,  # Below min_slope_deg of 15.0
        )
        proximity = _make_proximity(elevation_diff_m=50.0)

        result = scorer.calculate_risk_score(change, proximity)
        ls_factor = next(f for f in result.factors if f.name == "Landslide Detection")

        assert ls_factor.points == 0
        assert ls_factor.reason_code == "LANDSLIDE_LOW_SLOPE"

    def test_landslide_score_capped_at_100(self):
        """Even with all multipliers stacked, score should not exceed 100."""
        scorer = RiskScorer()
        change = _make_change(
            change_type="LandslideDebris",
            area_sq_meters=100000,
            ndvi_drop_mean=-0.8,
            slope_degree_mean=40.0,
            aspect_degrees=180.0,
        )
        proximity = _make_proximity(
            distance_meters=10,
            criticality=3,
            criticality_name="Critical",
            elevation_diff_m=200.0,
        )

        result = scorer.calculate_risk_score(change, proximity)
        assert result.score <= 100
