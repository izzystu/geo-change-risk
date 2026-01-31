"""Shared geospatial utility functions."""

from pyproj import CRS, Transformer
from shapely.geometry import Point


def get_utm_crs(lon: float, lat: float) -> CRS:
    """Get the appropriate UTM CRS for a given WGS84 coordinate.

    Args:
        lon: Longitude in degrees (-180 to 180).
        lat: Latitude in degrees (-90 to 90).

    Returns:
        pyproj CRS object for the appropriate UTM zone.
    """
    utm_zone = int((lon + 180) / 6) + 1
    utm_zone = max(1, min(60, utm_zone))
    hemisphere = "north" if lat >= 0 else "south"
    return CRS.from_string(f"+proj=utm +zone={utm_zone} +{hemisphere} +datum=WGS84")


def get_utm_transformer(lon: float, lat: float) -> Transformer:
    """Get a WGS84 -> UTM transformer for a given coordinate.

    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.

    Returns:
        pyproj Transformer from WGS84 to the appropriate UTM zone.
    """
    utm_crs = get_utm_crs(lon, lat)
    return Transformer.from_crs(4326, utm_crs, always_xy=True)
