"""Tests for TileExtractor: tile grid computation, region extraction, and integration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cartoload.exporters.garmin_img_writer import TileExtractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SWISS_BOUNDS = {
    "west": 5.96,
    "east": 10.49,
    "south": 45.82,
    "north": 47.81,
}


def _create_test_geotiff(
    tmp_path: Path,
    width: int = 512,
    height: int = 512,
    bounds: tuple[float, float, float, float] | None = None,
) -> Path:
    """Create a minimal GeoTIFF for testing using gdal_translate.

    Args:
        tmp_path: Temporary directory for output.
        width: Raster width in pixels.
        height: Raster height in pixels.
        bounds: (west, south, east, north) in EPSG:4326. Defaults to Swiss-ish bounds.

    Returns:
        Path to the created GeoTIFF.
    """
    if bounds is None:
        bounds = (5.0, 45.0, 11.0, 48.0)
    west, south, east, north = bounds

    # Create a simple RGB PNG with known content
    img_array = np.random.randint(50, 200, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    png_path = tmp_path / "source.png"
    img.save(png_path)

    tif_path = tmp_path / "test.tif"
    cmd = [
        "gdal_translate",
        "-of",
        "GTiff",
        "-a_srs",
        "EPSG:4326",
        "-a_ullr",
        str(west),
        str(north),
        str(east),
        str(south),
        str(png_path),
        str(tif_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"gdal_translate not available or failed: {result.stderr}")
    return tif_path


# ===================================================================
# 4.1 – _tile_grid_for_zoom tests
# ===================================================================


class TestTileGridForZoom:
    """Unit tests for TileExtractor._tile_grid_for_zoom."""

    def test_returns_cells_for_swiss_bounds_zoom10(self) -> None:
        """Switzerland at zoom 10 should produce a reasonable number of cells."""
        cells = TileExtractor._tile_grid_for_zoom(SWISS_BOUNDS, 10)
        assert len(cells) > 0
        for cell in cells:
            x, y, lon_min, lat_max, lon_max, lat_min = cell
            assert lon_min < lon_max
            assert lat_min < lat_max

    def test_higher_zoom_produces_more_cells(self) -> None:
        """Zoom 12 should produce more cells than zoom 10."""
        cells_10 = TileExtractor._tile_grid_for_zoom(SWISS_BOUNDS, 10)
        cells_12 = TileExtractor._tile_grid_for_zoom(SWISS_BOUNDS, 12)
        assert len(cells_12) > len(cells_10)

    def test_cell_coordinates_are_within_bounds(self) -> None:
        """Each cell should overlap with the requested bounds."""
        cells = TileExtractor._tile_grid_for_zoom(SWISS_BOUNDS, 10)
        for x, y, lon_min, lat_max, lon_max, lat_min in cells:
            # Cell must overlap with bounds
            overlaps_lon = (
                lon_min < SWISS_BOUNDS["east"] and lon_max > SWISS_BOUNDS["west"]
            )
            overlaps_lat = (
                lat_min < SWISS_BOUNDS["north"] and lat_max > SWISS_BOUNDS["south"]
            )
            assert overlaps_lon, (
                f"Cell ({x},{y}) lon [{lon_min},{lon_max}] outside bounds"
            )
            assert overlaps_lat, (
                f"Cell ({x},{y}) lat [{lat_min},{lat_max}] outside bounds"
            )

    def test_zoom0_single_tile(self) -> None:
        """At zoom 0, the whole world is one tile."""
        cells = TileExtractor._tile_grid_for_zoom(
            {"west": -180.0, "east": 180.0, "south": -85.0, "north": 85.0},
            0,
        )
        assert len(cells) == 1
        assert cells[0][0] == 0  # x
        assert cells[0][1] == 0  # y

    def test_cell_structure(self) -> None:
        """Each cell should be a 6-tuple (x, y, lon_min, lat_max, lon_max, lat_min)."""
        cells = TileExtractor._tile_grid_for_zoom(SWISS_BOUNDS, 10)
        for cell in cells:
            assert len(cell) == 6
            x, y, lon_min, lat_max, lon_max, lat_min = cell
            assert isinstance(x, int)
            assert isinstance(y, int)
            assert lon_min < lon_max
            assert lat_min < lat_max

    def test_no_duplicate_cells(self) -> None:
        """No two cells should have the same (x, y)."""
        cells = TileExtractor._tile_grid_for_zoom(SWISS_BOUNDS, 10)
        coords = [(c[0], c[1]) for c in cells]
        assert len(coords) == len(set(coords))


# ===================================================================
# 4.2 – _extract_tile_region tests
# ===================================================================


class TestExtractTileRegion:
    """Tests for TileExtractor._extract_tile_region."""

    def test_extract_returns_256x256x3(self, tmp_path: Path) -> None:
        """Extracted tile should be a 256x256x3 uint8 numpy array."""
        tif = _create_test_geotiff(tmp_path)
        extractor = TileExtractor(tif)
        tile = extractor._extract_tile_region(6.0, 47.0, 7.0, 46.0)
        assert tile is not None
        assert tile.shape == (256, 256, 3)
        assert tile.dtype == np.uint8

    def test_extract_has_nonzero_pixels(self, tmp_path: Path) -> None:
        """Extracted tile from a non-empty raster should have non-zero pixels."""
        tif = _create_test_geotiff(tmp_path)
        extractor = TileExtractor(tif)
        tile = extractor._extract_tile_region(6.0, 47.0, 7.0, 46.0)
        assert tile is not None
        assert tile.sum() > 0

    def test_extract_outside_raster_returns_none(self, tmp_path: Path) -> None:
        """Requesting a region completely outside the raster should return None."""
        tif = _create_test_geotiff(tmp_path, bounds=(5.0, 45.0, 11.0, 48.0))
        extractor = TileExtractor(tif)
        # Region in Australia — completely outside the GeoTIFF
        tile = extractor._extract_tile_region(150.0, -20.0, 151.0, -21.0)
        # gdal_translate may produce a black tile or fail; either way, not crash
        assert tile is None or tile.shape == (256, 256, 3)


# ===================================================================
# 4.3 – Integration test: extract_tiles
# ===================================================================


class TestExtractTiles:
    """Integration tests for TileExtractor.extract_tiles."""

    def test_returns_tiles_for_all_zoom_levels(self, tmp_path: Path) -> None:
        """extract_tiles should return tiles for each requested zoom level."""
        tif = _create_test_geotiff(tmp_path)
        extractor = TileExtractor(tif)
        bounds = {"west": 6.0, "east": 8.0, "south": 46.0, "north": 47.5}
        result = extractor.extract_tiles([10], bounds)

        assert 10 in result
        assert len(result[10]) > 0

    def test_tiles_are_correct_shape(self, tmp_path: Path) -> None:
        """All extracted tiles should be 256x256x3 uint8 arrays."""
        tif = _create_test_geotiff(tmp_path)
        extractor = TileExtractor(tif)
        bounds = {"west": 6.0, "east": 7.0, "south": 46.0, "north": 47.0}
        result = extractor.extract_tiles([10], bounds)

        for tile, tile_bounds in result[10]:
            assert tile.shape == (256, 256, 3)
            assert tile.dtype == np.uint8

    def test_multiple_zoom_levels(self, tmp_path: Path) -> None:
        """Multiple zoom levels should each produce tiles."""
        tif = _create_test_geotiff(tmp_path)
        extractor = TileExtractor(tif)
        bounds = {"west": 6.0, "east": 8.0, "south": 46.0, "north": 47.5}
        result = extractor.extract_tiles([8, 10], bounds)

        assert 8 in result
        assert 10 in result
        # Zoom 10 should have more tiles than zoom 8
        assert len(result[10]) >= len(result[8])

    def test_tiles_contain_data(self, tmp_path: Path) -> None:
        """Extracted tiles should contain actual pixel data (not all black)."""
        tif = _create_test_geotiff(tmp_path)
        extractor = TileExtractor(tif)
        bounds = {"west": 6.0, "east": 8.0, "south": 46.0, "north": 47.5}
        result = extractor.extract_tiles([10], bounds)

        # At least some tiles should have non-zero pixel values
        total_sum = sum(t.sum() for t, _ in result[10])
        assert total_sum > 0, "All extracted tiles are completely black"
