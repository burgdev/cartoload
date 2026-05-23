"""Vector rasterizer: render GeoPackage line features onto transparent PNG tiles.

Reads vector features from GPKG via OGR with spatial filtering, applies
style rules from the style engine, and draws lines using Pillow onto
transparent RGBA tiles. Output tiles are compatible with the composite pipeline.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from osgeo import ogr, osr
from PIL import Image, ImageDraw
from pyproj import Transformer

from cartoload.style import StyleEngine
from cartoload.style.model import LineStyle
from cartoload.tile_math import bounds_to_tile_coords

logger = logging.getLogger(__name__)

TILE_SIZE = 256


# ---- Feature reading ----


def read_features(
    gpkg_path: Path,
    bbox: tuple[float, float, float, float],
    target_crs: str = "EPSG:4326",
    layer: str | None = None,
) -> list[tuple[Any, dict[str, Any]]]:
    """Read vector features from a GeoPackage within a bounding box.

    Args:
        gpkg_path: Path to the .gpkg file.
        bbox: Bounding box as (west, south, east, north) in target_crs.
        target_crs: Target CRS for the features (default EPSG:4326).
        layer: Optional layer name within the GeoPackage.

    Returns:
        List of (geometry, attributes) tuples in target_crs.
    """
    features: list[tuple[Any, dict[str, Any]]] = []

    try:
        ds = ogr.Open(str(gpkg_path))
        if ds is None:
            return features

        # Select layer
        if layer:
            lyr = ds.GetLayerByName(layer)
        else:
            lyr = ds.GetLayerByIndex(0)
        if lyr is None:
            return features

        # Get source CRS
        src_srs = lyr.GetSpatialRef()
        src_crs_str = _srs_to_string(src_srs) if src_srs else None

        # Set up coordinate transformer if CRS differs
        need_reproject = False
        transformer = None
        forward_transformer = None
        if src_crs_str and src_crs_str != target_crs:
            need_reproject = True
            transformer = Transformer.from_crs(src_crs_str, target_crs, always_xy=True)
            forward_transformer = Transformer.from_crs(
                target_crs, src_crs_str, always_xy=True
            )

        # Reproject bbox to source CRS for spatial filtering
        if forward_transformer:
            west_s, south_s = forward_transformer.transform(bbox[0], bbox[1])
            east_s, north_s = forward_transformer.transform(bbox[2], bbox[3])
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint(west_s, south_s)
            ring.AddPoint(east_s, south_s)
            ring.AddPoint(east_s, north_s)
            ring.AddPoint(west_s, north_s)
            ring.AddPoint(west_s, south_s)
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)
            lyr.SetSpatialFilter(poly)
        else:
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint(bbox[0], bbox[1])
            ring.AddPoint(bbox[2], bbox[1])
            ring.AddPoint(bbox[2], bbox[3])
            ring.AddPoint(bbox[0], bbox[3])
            ring.AddPoint(bbox[0], bbox[1])
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)
            lyr.SetSpatialFilter(poly)

        # Iterate features
        feat = lyr.GetNextFeature()
        while feat:
            geom_ogr = feat.GetGeometryRef()
            if geom_ogr is not None:
                geom = json.loads(geom_ogr.ExportToJson())

                attrs: dict[str, Any] = {}
                for i in range(feat.GetFieldCount()):
                    val = feat.GetField(i)
                    if val is not None:
                        attrs[feat.GetFieldDefnRef(i).GetName()] = val

                if need_reproject and transformer:
                    geom = _reproject_geometry(geom, transformer)

                features.append((geom, attrs))

            feat = lyr.GetNextFeature()

    except Exception as e:
        logger.warning("Failed to read features from %s: %s", gpkg_path, e)

    return features


def _srs_to_string(srs: osr.SpatialReference) -> str | None:
    """Convert an OGR SpatialReference to a string like 'EPSG:4326'."""
    if srs is None:
        return None
    srs.AutoIdentifyEPSG()
    code = srs.GetAuthorityCode(None)
    if code:
        return f"EPSG:{code}"
    return None


def _reproject_geometry(geom: dict, transformer: Transformer) -> dict:
    """Reproject a GeoJSON-like geometry dict."""
    geom_type = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if geom_type == "LineString":
        new_coords = [_reproject_coord(c, transformer) for c in coords]
        return {"type": geom_type, "coordinates": new_coords}
    elif geom_type == "MultiLineString":
        new_coords = [
            [_reproject_coord(c, transformer) for c in line] for line in coords
        ]
        return {"type": geom_type, "coordinates": new_coords}
    elif geom_type == "Point":
        return {"type": geom_type, "coordinates": _reproject_coord(coords, transformer)}
    elif geom_type == "MultiPoint":
        return {
            "type": geom_type,
            "coordinates": [_reproject_coord(c, transformer) for c in coords],
        }

    return geom  # fallback


def _reproject_coord(coord: list, transformer: Transformer) -> list:
    """Reproject a single [x, y] coordinate."""
    if len(coord) >= 2:
        x, y = transformer.transform(coord[0], coord[1])
        return [x, y]
    return coord


# ---- Coordinate projection to tile pixels ----


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Compute the geographic bounds (west, south, east, north) of a tile.

    Returns bounds in EPSG:4326 (lon/lat degrees).
    """
    n = 2**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0

    # Web Mercator inverse for latitude
    def y_to_lat(y_tile: int) -> float:
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y_tile / n)))
        return math.degrees(lat_rad)

    north = y_to_lat(y)
    south = y_to_lat(y + 1)

    return (west, south, east, north)


def geo_to_tile_pixel(
    lon: float,
    lat: float,
    bounds: tuple[float, float, float, float],
    size: int = TILE_SIZE,
) -> tuple[float, float]:
    """Project a geographic coordinate to tile pixel coordinates.

    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.
        bounds: Tile bounds (west, south, east, north).
        size: Tile pixel size (default 256).

    Returns:
        (pixel_x, pixel_y) as floats.
    """
    west, south, east, north = bounds
    if east == west or north == south:
        return (0.0, 0.0)
    px = (lon - west) / (east - west) * size
    py = (north - lat) / (north - south) * size
    return (px, py)


def geometry_to_pixel_lines(
    geom: dict,
    bounds: tuple[float, float, float, float],
) -> list[list[tuple[float, float]]]:
    """Convert a GeoJSON geometry to pixel-coordinate polylines.

    Returns a list of polylines, where each polyline is a list of
    (px, py) tuples.
    """
    geom_type = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if geom_type == "LineString":
        return [[geo_to_tile_pixel(c[0], c[1], bounds) for c in coords if len(c) >= 2]]
    elif geom_type == "MultiLineString":
        return [
            [geo_to_tile_pixel(c[0], c[1], bounds) for c in line if len(c) >= 2]
            for line in coords
        ]
    elif geom_type == "Point":
        px, py = geo_to_tile_pixel(coords[0], coords[1], bounds)
        return [[(px, py)]]
    elif geom_type == "MultiPoint":
        return [[geo_to_tile_pixel(c[0], c[1], bounds)] for c in coords if len(c) >= 2]

    return []


# ---- Line rendering ----


def draw_line(
    image: Image.Image,
    pixel_coords: list[tuple[float, float]],
    style: LineStyle,
) -> None:
    """Draw a styled line onto a PIL RGBA image.

    Handles solid lines, dashed lines, and border/casing.
    """
    if len(pixel_coords) < 2:
        return

    draw = ImageDraw.Draw(image)
    width = max(1, round(style.width))

    # Draw border first (if present)
    if style.border_color is not None and style.border_width is not None:
        border_width = width + round(2 * style.border_width)
        border_rgba = (*style.border_color, _opacity_to_alpha(style.opacity))

        if style.dash:
            _draw_dashed_line(draw, pixel_coords, border_rgba, border_width, style.dash)
        else:
            draw.line(pixel_coords, fill=border_rgba, width=border_width)

    # Draw core line
    core_rgba = (*style.color, _opacity_to_alpha(style.opacity))

    if style.dash:
        _draw_dashed_line(draw, pixel_coords, core_rgba, width, style.dash)
    else:
        draw.line(pixel_coords, fill=core_rgba, width=width)


def _draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    pixel_coords: list[tuple[float, float]],
    color: tuple[int, int, int, int],
    width: int,
    dash_pattern: list[float],
) -> None:
    """Draw a dashed line by segmenting the polyline.

    Walks the polyline accumulating length, alternating between
    "on" (draw) and "off" (skip) segments based on the dash pattern.
    """
    if not dash_pattern or len(pixel_coords) < 2:
        return

    # Calculate cumulative distances between points
    distances: list[float] = [0.0]
    for i in range(1, len(pixel_coords)):
        dx = pixel_coords[i][0] - pixel_coords[i - 1][0]
        dy = pixel_coords[i][1] - pixel_coords[i - 1][1]
        distances.append(distances[-1] + math.sqrt(dx * dx + dy * dy))

    total_length = distances[-1]
    if total_length < 0.5:
        return

    # Walk along the polyline, toggling on/off
    pattern_len = sum(dash_pattern)
    if pattern_len <= 0:
        return

    dash_idx = 0
    pos = 0.0  # position along the line
    is_on = True

    while pos < total_length:
        segment_len = dash_pattern[dash_idx % len(dash_pattern)]
        segment_end = pos + segment_len

        if is_on and segment_len > 0:
            # Extract the polyline points for this "on" segment
            seg_points = _extract_segment(pixel_coords, distances, pos, segment_end)
            if len(seg_points) >= 2:
                draw.line(seg_points, fill=color, width=width)

        pos = segment_end
        dash_idx += 1
        is_on = not is_on


def _extract_segment(
    pixel_coords: list[tuple[float, float]],
    distances: list[float],
    start_dist: float,
    end_dist: float,
) -> list[tuple[float, float]]:
    """Extract polyline points between two cumulative distances."""
    points: list[tuple[float, float]] = []

    for i in range(len(pixel_coords)):
        d = distances[i]

        if d >= start_dist and d <= end_dist:
            points.append(pixel_coords[i])
        elif d > end_dist:
            # Interpolate end point
            if i > 0 and distances[i - 1] < end_dist:
                frac = (end_dist - distances[i - 1]) / (d - distances[i - 1])
                px = pixel_coords[i - 1][0] + frac * (
                    pixel_coords[i][0] - pixel_coords[i - 1][0]
                )
                py = pixel_coords[i - 1][1] + frac * (
                    pixel_coords[i][1] - pixel_coords[i - 1][1]
                )
                points.append((px, py))
            break
        elif i == 0 or distances[i] < start_dist:
            # Check if next point crosses start
            if i + 1 < len(distances) and distances[i + 1] > start_dist:
                frac = (start_dist - d) / (distances[i + 1] - d)
                px = pixel_coords[i][0] + frac * (
                    pixel_coords[i + 1][0] - pixel_coords[i][0]
                )
                py = pixel_coords[i][1] + frac * (
                    pixel_coords[i + 1][1] - pixel_coords[i][1]
                )
                points.append((px, py))

    return points


def _opacity_to_alpha(opacity: float) -> int:
    """Convert opacity (0.0-1.0) to alpha channel value (0-255)."""
    return max(0, min(255, round(opacity * 255)))


# ---- Tile rasterizer ----


class VectorRasterizer:
    """Renders vector features from GPKG onto transparent PNG tiles.

    For each tile, computes bounds, reads intersecting features,
    applies style rules, and draws lines onto a transparent RGBA image.
    """

    def __init__(
        self,
        gpkg_paths: list[Path],
        style_engine: StyleEngine,
        *,
        max_workers: int = 4,
        layer: str | None = None,
    ) -> None:
        self.gpkg_paths = gpkg_paths
        self.style_engine = style_engine
        self.max_workers = max_workers
        self.layer = layer

    def render_tile(self, z: int, x: int, y: int) -> Image.Image | None:
        """Render a single tile.

        Returns an RGBA Image with rendered features, or None if no
        features intersect the tile.
        """
        bounds = tile_bounds(z, x, y)
        image = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        has_content = False

        for gpkg_path in self.gpkg_paths:
            features = read_features(
                gpkg_path,
                bbox=bounds,
                target_crs="EPSG:4326",
                layer=self.layer,
            )

            for geom, attrs in features:
                style = self.style_engine.resolve(attrs, z)
                if style is None:
                    continue

                pixel_lines = geometry_to_pixel_lines(geom, bounds)
                for polyline in pixel_lines:
                    if len(polyline) >= 2:
                        draw_line(image, polyline, style)
                        has_content = True

        return image if has_content else None

    def render_tiles(
        self,
        zoom_levels: list[int],
        bounds: dict[str, float],
        cache_dir: Path,
        source_id: str = "",
        progress_callback: Any = None,
    ) -> list[Path]:
        """Render all tiles for the given zoom levels and bounds.

        Args:
            zoom_levels: List of zoom levels to render.
            bounds: Geographic bounds dict with west, south, east, north.
            cache_dir: Base cache directory for output tiles.
            source_id: Source identifier for cache path structure.
            progress_callback: Optional callback(stage, description).

        Returns:
            List of paths to written PNG tiles.
        """
        written: list[Path] = []
        total_tiles = 0

        for zoom in zoom_levels:
            tile_coords = bounds_to_tile_coords(
                bounds["west"], bounds["south"], bounds["east"], bounds["north"], zoom
            )
            total_tiles += len(tile_coords)

        if progress_callback:
            progress_callback(
                "rasterize",
                f"Rasterizing {total_tiles} tiles across {len(zoom_levels)} zoom levels",
            )

        rendered_count = 0

        for zoom in zoom_levels:
            tile_coords = bounds_to_tile_coords(
                bounds["west"], bounds["south"], bounds["east"], bounds["north"], zoom
            )

            for x, y in tile_coords:
                image = self.render_tile(zoom, x, y)
                if image is None:
                    continue

                # Write to cache
                tile_dir = cache_dir / source_id / str(zoom) / str(x)
                tile_dir.mkdir(parents=True, exist_ok=True)
                tile_path = tile_dir / f"{y}.png"
                image.save(tile_path, format="PNG", optimize=True)
                written.append(tile_path)
                rendered_count += 1

        if progress_callback:
            progress_callback(
                "rasterize",
                f"Rasterized {rendered_count}/{total_tiles} tiles with features",
            )

        logger.info(
            "Rasterized %d/%d tiles with features",
            rendered_count,
            total_tiles,
        )
        return written
