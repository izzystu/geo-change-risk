"""Risk scoring model for change-asset proximity."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from georisk.risk.proximity import ProximityResult
from georisk.raster.change import ChangePolygon

logger = structlog.get_logger()


@dataclass
class ScoringFactor:
    """A single scoring factor contribution."""

    name: str
    points: int
    max_points: int
    reason_code: str
    details: str


@dataclass
class RiskScore:
    """Calculated risk score for a change-asset pair."""

    score: int
    level: str
    factors: list[ScoringFactor] = field(default_factory=list)

    @property
    def scoring_factors_dict(self) -> dict[str, Any]:
        """Convert factors to dictionary for API submission."""
        return {
            "total_score": self.score,
            "risk_level": self.level,
            "factors": [
                {
                    "name": f.name,
                    "points": f.points,
                    "max_points": f.max_points,
                    "reason_code": f.reason_code,
                    "details": f.details,
                }
                for f in self.factors
            ],
        }


# Default scoring configuration
DEFAULT_SCORING = {
    "distance": {
        "max_points": 28,  # Reduced from 35 to make room for terrain factors
        "thresholds": [
            {"distance_m": 100, "points": 28, "reason_code": "DISTANCE_LT_100M"},
            {"distance_m": 500, "points": 21, "reason_code": "DISTANCE_LT_500M"},
            {"distance_m": 1000, "points": 14, "reason_code": "DISTANCE_LT_1KM"},
            {"distance_m": 2500, "points": 7, "reason_code": "DISTANCE_LT_2.5KM"},
        ],
    },
    "ndvi_drop": {
        "max_points": 25,
        "thresholds": [
            {"delta": -0.5, "points": 25, "reason_code": "NDVI_DROP_SEVERE"},
            {"delta": -0.4, "points": 20, "reason_code": "NDVI_DROP_STRONG"},
            {"delta": -0.3, "points": 15, "reason_code": "NDVI_DROP_MODERATE"},
            {"delta": -0.2, "points": 10, "reason_code": "NDVI_DROP_MILD"},
        ],
    },
    "area": {
        "max_points": 15,  # Reduced from 20 to make room for terrain factors
        "thresholds": [
            {"area_m2": 50000, "points": 15, "reason_code": "LARGE_AREA_GT_50000M2"},
            {"area_m2": 25000, "points": 11, "reason_code": "LARGE_AREA_GT_25000M2"},
            {"area_m2": 10000, "points": 8, "reason_code": "AREA_GT_10000M2"},
            {"area_m2": 5000, "points": 4, "reason_code": "AREA_GT_5000M2"},
        ],
    },
    "slope": {
        "max_points": 10,  # Base slope score before directional modifier
        "thresholds": [
            {"slope_deg": 30, "points": 10, "reason_code": "SLOPE_GT_30DEG"},
            {"slope_deg": 20, "points": 7, "reason_code": "SLOPE_GT_20DEG"},
            {"slope_deg": 15, "points": 5, "reason_code": "SLOPE_GT_15DEG"},
            {"slope_deg": 10, "points": 3, "reason_code": "SLOPE_GT_10DEG"},
        ],
    },
    "directional_slope": {
        "max_points": 20,  # Combined slope + direction can reach 20 points
        "upslope_threshold_m": 5.0,  # Elevation diff to consider "upslope"
        "downslope_threshold_m": -5.0,  # Elevation diff to consider "downslope"
        # Upslope: debris/erosion/landslide flows downhill toward asset
        "upslope_multiplier_base": 1.5,  # Base multiplier for upslope
        "upslope_multiplier_max": 2.5,  # Max multiplier for steep upslope
        "upslope_elev_scale": 100,  # Elevation diff to reach max multiplier
        # Downslope: fire spreads uphill toward asset, moderate discount only
        "downslope_multiplier_base": 0.9,  # Base multiplier for downslope
        "downslope_multiplier_min": 0.7,  # Min multiplier for steep downslope
        "downslope_elev_scale": 100,  # Elevation diff to reach min multiplier
    },
    "aspect": {
        "max_points": 5,  # South-facing slopes are drier/higher fire risk
        "ranges": [
            # South-facing (157.5-202.5 degrees)
            {"min_deg": 157.5, "max_deg": 202.5, "points": 5, "reason_code": "ASPECT_SOUTH"},
            # SW (202.5-225) and SE (135-157.5)
            {"min_deg": 135, "max_deg": 157.5, "points": 4, "reason_code": "ASPECT_SE"},
            {"min_deg": 202.5, "max_deg": 225, "points": 4, "reason_code": "ASPECT_SW"},
            # E/W adjacent (112.5-135, 225-247.5)
            {"min_deg": 112.5, "max_deg": 135, "points": 2, "reason_code": "ASPECT_EAST"},
            {"min_deg": 225, "max_deg": 247.5, "points": 2, "reason_code": "ASPECT_WEST"},
            # NE (22.5-67.5) and NW (292.5-337.5)
            {"min_deg": 22.5, "max_deg": 67.5, "points": 1, "reason_code": "ASPECT_NE"},
            {"min_deg": 292.5, "max_deg": 337.5, "points": 1, "reason_code": "ASPECT_NW"},
            # North (337.5-360, 0-22.5) - lowest risk
            {"min_deg": 337.5, "max_deg": 360, "points": 0, "reason_code": "ASPECT_NORTH"},
            {"min_deg": 0, "max_deg": 22.5, "points": 0, "reason_code": "ASPECT_NORTH"},
        ],
    },
    "land_cover": {
        "multipliers": {
            "Forest": 1.0,
            "Residential": 0.9,
            "HerbaceousVegetation": 0.85,
            "River": 0.8,
            "PermanentCrop": 0.75,
            "Pasture": 0.7,
            "Industrial": 0.5,
            "SeaLake": 0.4,
            "AnnualCrop": 0.3,
            "Highway": 0.25,
        },
    },
    "landslide": {
        "multiplier": 1.8,
        "upslope_boost": 0.5,
        "min_slope_deg": 15.0,
        "max_multiplier": 2.5,
    },
    "criticality": {
        "max_points": 10,
        "multipliers": {
            0: 0.5,   # Low
            1: 1.0,   # Medium
            2: 1.5,   # High
            3: 2.0,   # Critical
        },
    },
    "risk_levels": [
        {"name": "Low", "min_score": 0, "max_score": 24},
        {"name": "Medium", "min_score": 25, "max_score": 49},
        {"name": "High", "min_score": 50, "max_score": 74},
        {"name": "Critical", "min_score": 75, "max_score": 100},
    ],
}


class RiskScorer:
    """Risk scoring engine with configurable thresholds."""

    def __init__(self, config: dict[str, Any] | None = None, config_path: Path | None = None):
        """Initialize the scorer with optional configuration.

        Args:
            config: Scoring configuration dictionary.
            config_path: Path to YAML configuration file.
        """
        self.config = DEFAULT_SCORING.copy()

        if config_path and config_path.exists():
            with open(config_path) as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    self._merge_config(yaml_config)

        if config:
            self._merge_config(config)

    def _merge_config(self, config: dict[str, Any]) -> None:
        """Merge configuration into current config."""
        for key in ["scoring_factors", "risk_levels"]:
            if key in config:
                if key == "scoring_factors":
                    for factor, settings in config[key].items():
                        if factor in self.config:
                            self.config[factor].update(settings)
                else:
                    self.config[key] = config[key]

    def calculate_risk_score(
        self,
        change: ChangePolygon,
        proximity: ProximityResult,
    ) -> RiskScore:
        """Calculate risk score for a change-asset pair.

        Args:
            change: The detected change polygon.
            proximity: Proximity result linking change to asset.

        Returns:
            RiskScore with total score, level, and factor breakdown.
        """
        factors = []
        total_score = 0

        # Distance factor
        distance_score = self._score_distance(proximity.distance_meters)
        factors.append(distance_score)
        total_score += distance_score.points

        # NDVI drop factor
        ndvi_score = self._score_ndvi(change.ndvi_drop_mean)
        factors.append(ndvi_score)
        total_score += ndvi_score.points

        # Area factor
        area_score = self._score_area(change.area_sq_meters)
        factors.append(area_score)
        total_score += area_score.points

        # Directional slope factor (if terrain data available)
        # Uses elevation_diff_m from proximity to determine upslope/downslope
        if change.slope_degree_mean is not None:
            slope_score = self._score_directional_slope(
                change.slope_degree_mean,
                proximity.elevation_diff_m,
            )
            factors.append(slope_score)
            total_score += slope_score.points

        # Aspect factor (if available)
        if change.aspect_degrees is not None:
            aspect_score = self._score_aspect(change.aspect_degrees)
            factors.append(aspect_score)
            total_score += aspect_score.points

        # Apply land cover multiplier (before criticality)
        lc_multiplier = self._get_land_cover_multiplier(change.land_cover_class)
        if lc_multiplier != 1.0:
            lc_delta = int(total_score * lc_multiplier) - total_score
            lc_factor = ScoringFactor(
                name="Land Cover",
                points=lc_delta,
                max_points=0,
                reason_code=f"LANDCOVER_{change.land_cover_class.upper()}" if change.land_cover_class else "LANDCOVER_UNKNOWN",
                details=f"Land cover: {change.land_cover_class or 'unknown'} (multiplier: {lc_multiplier:.2f}x)",
            )
            factors.append(lc_factor)
            total_score = int(total_score * lc_multiplier)
        elif change.land_cover_class is not None:
            # Land cover is Forest (1.0x) — still record it for transparency
            lc_factor = ScoringFactor(
                name="Land Cover",
                points=0,
                max_points=0,
                reason_code=f"LANDCOVER_{change.land_cover_class.upper()}",
                details=f"Land cover: {change.land_cover_class} (multiplier: 1.00x, baseline)",
            )
            factors.append(lc_factor)

        # Apply landslide multiplier (after land cover, before criticality)
        ls_factor = self._score_landslide(change, proximity.elevation_diff_m)
        if ls_factor is not None:
            if ls_factor.reason_code != "LANDSLIDE_LOW_SLOPE":
                # Parse multiplier from the details string
                ls_config = self.config.get("landslide", {})
                base_mult = ls_config.get("multiplier", 1.8)
                upslope_boost = ls_config.get("upslope_boost", 0.5)
                max_mult = ls_config.get("max_multiplier", 2.5)

                ls_mult = base_mult
                if (proximity.elevation_diff_m is not None
                        and proximity.elevation_diff_m > 5.0):
                    ls_mult = min(base_mult + upslope_boost, max_mult)

                ls_delta = int(total_score * ls_mult) - total_score
                ls_factor.points = ls_delta
                total_score = int(total_score * ls_mult)
            factors.append(ls_factor)

        # Apply criticality multiplier
        multiplier = self.config["criticality"]["multipliers"].get(proximity.criticality, 1.0)
        adjusted_score = int(min(100, total_score * multiplier))

        # Add criticality factor for transparency
        crit_factor = ScoringFactor(
            name="Criticality",
            points=int(total_score * (multiplier - 1)) if multiplier > 1 else 0,
            max_points=self.config["criticality"]["max_points"],
            reason_code=f"CRITICALITY_{proximity.criticality_name.upper()}",
            details=f"Multiplier: {multiplier}x for {proximity.criticality_name} criticality",
        )
        factors.append(crit_factor)

        # Determine risk level
        level = self._get_risk_level(adjusted_score)

        return RiskScore(
            score=adjusted_score,
            level=level,
            factors=factors,
        )

    def _score_distance(self, distance_m: float) -> ScoringFactor:
        """Score based on distance."""
        config = self.config["distance"]
        max_pts = config["max_points"]

        for threshold in config["thresholds"]:
            if distance_m < threshold["distance_m"]:
                return ScoringFactor(
                    name="Distance",
                    points=threshold["points"],
                    max_points=max_pts,
                    reason_code=threshold["reason_code"],
                    details=f"Distance: {distance_m:.0f}m",
                )

        return ScoringFactor(
            name="Distance",
            points=0,
            max_points=max_pts,
            reason_code="DISTANCE_FAR",
            details=f"Distance: {distance_m:.0f}m (beyond threshold)",
        )

    def _score_ndvi(self, ndvi_drop: float) -> ScoringFactor:
        """Score based on NDVI drop magnitude."""
        config = self.config["ndvi_drop"]
        max_pts = config["max_points"]

        for threshold in config["thresholds"]:
            if ndvi_drop <= threshold["delta"]:
                return ScoringFactor(
                    name="NDVI Drop",
                    points=threshold["points"],
                    max_points=max_pts,
                    reason_code=threshold["reason_code"],
                    details=f"NDVI drop: {ndvi_drop:.3f}",
                )

        return ScoringFactor(
            name="NDVI Drop",
            points=0,
            max_points=max_pts,
            reason_code="NDVI_DROP_MINIMAL",
            details=f"NDVI drop: {ndvi_drop:.3f} (below threshold)",
        )

    def _score_area(self, area_m2: float) -> ScoringFactor:
        """Score based on change area."""
        config = self.config["area"]
        max_pts = config["max_points"]

        for threshold in config["thresholds"]:
            if area_m2 >= threshold["area_m2"]:
                return ScoringFactor(
                    name="Area",
                    points=threshold["points"],
                    max_points=max_pts,
                    reason_code=threshold["reason_code"],
                    details=f"Area: {area_m2:,.0f} m\u00b2",
                )

        return ScoringFactor(
            name="Area",
            points=0,
            max_points=max_pts,
            reason_code="AREA_SMALL",
            details=f"Area: {area_m2:,.0f} m\u00b2 (below threshold)",
        )

    def _score_slope(self, slope_deg: float) -> ScoringFactor:
        """Score based on terrain slope (basic, without directional modifier)."""
        config = self.config["slope"]
        max_pts = config["max_points"]

        for threshold in config["thresholds"]:
            if slope_deg >= threshold["slope_deg"]:
                return ScoringFactor(
                    name="Slope",
                    points=threshold["points"],
                    max_points=max_pts,
                    reason_code=threshold["reason_code"],
                    details=f"Slope: {slope_deg:.1f}\u00b0",
                )

        return ScoringFactor(
            name="Slope",
            points=0,
            max_points=max_pts,
            reason_code="SLOPE_FLAT",
            details=f"Slope: {slope_deg:.1f}\u00b0 (below threshold)",
        )

    def _score_directional_slope(
        self,
        slope_deg: float,
        elevation_diff_m: float | None,
    ) -> ScoringFactor:
        """Score based on terrain slope with directional modifier.

        Upslope changes (change is higher than asset, positive elevation_diff):
        - HIGHEST RISK: Debris, erosion, and sediment flow downhill toward asset
        - Destabilized slopes above infrastructure are an imminent threat
        - Root structure loss (forest/vegetation) increases landslide probability

        Downslope changes (change is lower than asset, negative elevation_diff):
        - MODERATE RISK: Fire spreads uphill 2-4x faster due to preheating,
          so a fire starting below the asset advances toward it
        - Debris/erosion flows away from asset (lower risk for those threats)
        - Net effect: reduced but still significant risk

        Args:
            slope_deg: Slope steepness in degrees.
            elevation_diff_m: Elevation difference (change - asset).
                             Positive = change is upslope from asset.

        Returns:
            ScoringFactor with directional slope score.
        """
        config = self.config.get("directional_slope", self.config["slope"])
        max_pts = config.get("max_points", 20)

        # Calculate base slope score (0-10 points)
        base_points = 0
        base_reason = "SLOPE_FLAT"

        slope_config = self.config["slope"]
        for threshold in slope_config["thresholds"]:
            if slope_deg >= threshold["slope_deg"]:
                base_points = threshold["points"]
                base_reason = threshold["reason_code"]
                break

        # If no elevation data, return base slope score
        if elevation_diff_m is None:
            return ScoringFactor(
                name="Slope",
                points=base_points,
                max_points=max_pts,
                reason_code=base_reason,
                details=f"Slope: {slope_deg:.1f}\u00b0 (no elevation data)",
            )

        # Calculate directional modifier
        upslope_threshold = config.get("upslope_threshold_m", 5.0)
        downslope_threshold = config.get("downslope_threshold_m", -5.0)

        if elevation_diff_m > upslope_threshold:
            # Change is upslope from asset - HIGHEST risk
            # Debris/erosion/landslide flows downhill toward asset
            upslope_base = config.get("upslope_multiplier_base", 1.5)
            upslope_max = config.get("upslope_multiplier_max", 2.5)
            elev_scale = config.get("upslope_elev_scale", 100)

            # Scale from base to max based on elevation difference
            modifier = upslope_base + min(
                upslope_max - upslope_base,
                (upslope_max - upslope_base) * elevation_diff_m / elev_scale,
            )
            direction = "UPSLOPE"
            direction_desc = f"upslope ({elevation_diff_m:.0f}m higher)"

        elif elevation_diff_m < downslope_threshold:
            # Change is downslope from asset - MODERATE risk
            # Fire spreads uphill toward asset, but debris flows away
            downslope_base = config.get("downslope_multiplier_base", 0.9)
            downslope_min = config.get("downslope_multiplier_min", 0.7)
            elev_scale = config.get("downslope_elev_scale", 100)

            # Scale from base to min based on elevation difference
            modifier = downslope_base - min(
                downslope_base - downslope_min,
                (downslope_base - downslope_min) * abs(elevation_diff_m) / elev_scale,
            )
            direction = "DOWNSLOPE"
            direction_desc = f"downslope ({abs(elevation_diff_m):.0f}m lower)"

        else:
            # Roughly level
            modifier = 1.0
            direction = "LEVEL"
            direction_desc = "approximately level"

        # Apply modifier to base points
        final_points = int(base_points * modifier)
        final_points = min(max_pts, final_points)  # Cap at max points

        return ScoringFactor(
            name="Slope + Direction",
            points=final_points,
            max_points=max_pts,
            reason_code=f"SLOPE_{direction}",
            details=f"Slope: {slope_deg:.1f}\u00b0, {direction_desc} (modifier: {modifier:.2f}x)",
        )

    def _score_aspect(self, aspect_degrees: float) -> ScoringFactor:
        """Score based on slope aspect (compass direction).

        South-facing slopes receive more sun, leading to drier vegetation
        and higher fire risk.

        Args:
            aspect_degrees: Aspect in degrees (0=N, 90=E, 180=S, 270=W).

        Returns:
            ScoringFactor with aspect score.
        """
        config = self.config.get("aspect", {})
        max_pts = config.get("max_points", 5)
        ranges = config.get("ranges", [])

        # Normalize to 0-360
        aspect = aspect_degrees % 360

        for range_def in ranges:
            min_deg = range_def.get("min_deg", 0)
            max_deg = range_def.get("max_deg", 360)

            if min_deg <= aspect < max_deg:
                return ScoringFactor(
                    name="Aspect",
                    points=range_def.get("points", 0),
                    max_points=max_pts,
                    reason_code=range_def.get("reason_code", "ASPECT_UNKNOWN"),
                    details=f"Aspect: {aspect:.0f}\u00b0 ({self._aspect_to_compass(aspect)})",
                )

        # Default for any unmatched range
        return ScoringFactor(
            name="Aspect",
            points=0,
            max_points=max_pts,
            reason_code="ASPECT_OTHER",
            details=f"Aspect: {aspect:.0f}\u00b0 ({self._aspect_to_compass(aspect)})",
        )

    def _get_land_cover_multiplier(self, land_cover_class: str | None) -> float:
        """Get risk multiplier for the land cover type.

        Land cover contextualizes the detected change: a forest-to-bare
        transition is inherently more concerning than a crop harvest.
        The multiplier is applied to the base score before criticality.

        Args:
            land_cover_class: EuroSAT class name (e.g. "Forest", "AnnualCrop"),
                             or None if classification was not performed.

        Returns:
            Multiplier in range [0.25, 1.0]. Returns 1.0 if no class provided.
        """
        if land_cover_class is None:
            return 1.0

        lc_config = self.config.get("land_cover", {})
        multipliers = lc_config.get("multipliers", {})
        return multipliers.get(land_cover_class, 1.0)

    def _score_landslide(
        self,
        change: ChangePolygon,
        elevation_diff_m: float | None,
    ) -> ScoringFactor | None:
        """Score based on landslide classification.

        Only applies when change_type is "LandslideDebris". Returns a
        multiplicative factor that amplifies the score for confirmed landslides,
        especially those upslope from assets.

        Args:
            change: The detected change polygon.
            elevation_diff_m: Elevation difference (change - asset).
                Positive = change is upslope from asset.

        Returns:
            ScoringFactor with landslide multiplier, or None for non-landslide polygons.
        """
        if change.change_type != "LandslideDebris":
            return None

        ls_config = self.config.get("landslide", {})
        base_multiplier = ls_config.get("multiplier", 1.8)
        upslope_boost = ls_config.get("upslope_boost", 0.5)
        min_slope_deg = ls_config.get("min_slope_deg", 15.0)
        max_multiplier = ls_config.get("max_multiplier", 2.5)

        slope = change.slope_degree_mean or 0.0

        # Below minimum slope: record informational factor but don't apply multiplier
        if slope < min_slope_deg:
            return ScoringFactor(
                name="Landslide Detection",
                points=0,
                max_points=0,
                reason_code="LANDSLIDE_LOW_SLOPE",
                details=(
                    f"Landslide detected but slope {slope:.1f}\u00b0 "
                    f"< {min_slope_deg:.0f}\u00b0 threshold"
                ),
            )

        # Calculate multiplier
        multiplier = base_multiplier
        direction_desc = "level/unknown terrain"

        if elevation_diff_m is not None and elevation_diff_m > 5.0:
            multiplier = min(base_multiplier + upslope_boost, max_multiplier)
            direction_desc = f"upslope ({elevation_diff_m:.0f}m higher)"
        elif elevation_diff_m is not None and elevation_diff_m < -5.0:
            direction_desc = f"downslope ({abs(elevation_diff_m):.0f}m lower)"

        return ScoringFactor(
            name="Landslide Detection",
            points=0,  # Points will be computed by the caller as a multiplicative delta
            max_points=0,
            reason_code="LANDSLIDE_UPSLOPE" if elevation_diff_m and elevation_diff_m > 5.0 else "LANDSLIDE_DETECTED",
            details=f"Landslide on {slope:.1f}\u00b0 slope, {direction_desc} (multiplier: {multiplier:.2f}x)",
        )

    def _aspect_to_compass(self, aspect: float) -> str:
        """Convert aspect degrees to compass direction."""
        directions = [
            (337.5, 360, "N"), (0, 22.5, "N"),
            (22.5, 67.5, "NE"),
            (67.5, 112.5, "E"),
            (112.5, 157.5, "SE"),
            (157.5, 202.5, "S"),
            (202.5, 247.5, "SW"),
            (247.5, 292.5, "W"),
            (292.5, 337.5, "NW"),
        ]
        aspect = aspect % 360
        for min_deg, max_deg, direction in directions:
            if min_deg <= aspect < max_deg:
                return direction
        return "N"

    def _get_risk_level(self, score: int) -> str:
        """Get risk level name from score."""
        for level in self.config["risk_levels"]:
            if level["min_score"] <= score <= level["max_score"]:
                return level["name"]
        return "Unknown"


# Convenience function with default scorer
def calculate_risk_score(
    change: ChangePolygon,
    proximity: ProximityResult,
) -> RiskScore:
    """Calculate risk score using the default scorer."""
    scorer = RiskScorer()
    return scorer.calculate_risk_score(change, proximity)
