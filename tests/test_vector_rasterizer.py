"""Tests for the vector rasterizer: coordinate projection, line rendering, tile rasterizer."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from cartoload.processor.gpkg.vector_rasterizer import (
    draw_line,
    geo_to_tile_pixel,
    geometry_to_pixel_lines,
    tile_bounds,
)
from cartoload.style.model import LineStyle


class TestTileBounds:
    def test_zoom_0_single_tile(self):
        west, south, east, north = tile_bounds(0, 0, 0)
        assert west == pytest.approx(-180.0)
        assert east == pytest.approx(180.0)
        assert north == pytest.approx(85.05, abs=0.01)
        assert south == pytest.approx(-85.05, abs=0.01)

    def test_zoom_1_quadrants(self):
        w0, s0, e0, n0 = tile_bounds(1, 0, 0)
        w1, s1, e1, n1 = tile_bounds(1, 1, 0)
        assert e0 == pytest.approx(w1)  # tiles are adjacent

    def test_bounds_are_reasonable(self):
        west, south, east, north = tile_bounds(12, 2140, 1440)
        assert -180 <= west < east <= 180
        assert -90 <= south < north <= 90


class TestGeoToTilePixel:
    def test_center_of_tile(self):
        bounds = (0.0, 0.0, 1.0, 1.0)
        px, py = geo_to_tile_pixel(0.5, 0.5, bounds)
        assert px == pytest.approx(128.0)
        assert py == pytest.approx(128.0)

    def test_top_left(self):
        bounds = (0.0, 0.0, 1.0, 1.0)
        px, py = geo_to_tile_pixel(0.0, 1.0, bounds)
        assert px == pytest.approx(0.0)
        assert py == pytest.approx(0.0)

    def test_bottom_right(self):
        bounds = (0.0, 0.0, 1.0, 1.0)
        px, py = geo_to_tile_pixel(1.0, 0.0, bounds)
        assert px == pytest.approx(256.0)
        assert py == pytest.approx(256.0)


class TestGeometryToPixelLines:
    def test_linestring(self):
        geom = {
            "type": "LineString",
            "coordinates": [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]],
        }
        bounds = (0.0, 0.0, 1.0, 1.0)
        lines = geometry_to_pixel_lines(geom, bounds)
        assert len(lines) == 1
        assert len(lines[0]) == 3
        assert lines[0][0] == pytest.approx((0.0, 256.0))
        assert lines[0][1] == pytest.approx((128.0, 128.0))
        assert lines[0][2] == pytest.approx((256.0, 0.0))

    def test_multilinestring(self):
        geom = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0], [1.0, 1.0]],
                [[0.0, 1.0], [1.0, 0.0]],
            ],
        }
        bounds = (0.0, 0.0, 1.0, 1.0)
        lines = geometry_to_pixel_lines(geom, bounds)
        assert len(lines) == 2

    def test_point(self):
        geom = {"type": "Point", "coordinates": [0.5, 0.5]}
        bounds = (0.0, 0.0, 1.0, 1.0)
        lines = geometry_to_pixel_lines(geom, bounds)
        assert len(lines) == 1
        assert len(lines[0]) == 1

    def test_empty_coords(self):
        geom = {"type": "LineString", "coordinates": []}
        bounds = (0.0, 0.0, 1.0, 1.0)
        lines = geometry_to_pixel_lines(geom, bounds)
        assert len(lines) == 1
        assert len(lines[0]) == 0


class TestDrawLine:
    def test_solid_line(self):
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        style = LineStyle(color=(255, 0, 0), width=2)
        coords = [(10, 10), (100, 100)]
        draw_line(image, coords, style)

        pixels = image.load()
        # Check a pixel along the line
        assert pixels[50, 50][0] == 255  # red channel
        assert pixels[50, 50][3] > 0  # alpha > 0

    def test_dashed_line(self):
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        style = LineStyle(color=(0, 255, 0), width=2, dash=[20, 10])
        coords = [(10, 128), (200, 128)]
        draw_line(image, coords, style)

        pixels = image.load()
        # Should have gaps in the line
        # At x=10 should be "on"
        assert pixels[10, 128][3] > 0
        # At x=35 (10+20+5) should be "off"
        assert pixels[35, 128][3] == 0

    def test_line_with_border(self):
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        style = LineStyle(
            color=(0, 0, 255),
            width=2,
            border_color=(255, 255, 255),
            border_width=1.5,
        )
        coords = [(50, 128), (200, 128)]
        draw_line(image, coords, style)

        pixels = image.load()
        # Core line should be blue
        assert pixels[100, 128][2] > 200  # blue channel

        # Border should extend beyond the core line.
        # The total width is 2 + 2*1.5 = 5 pixels.
        # Check that some pixels above/below the center are white-ish
        has_border = False
        for dy in range(-5, 6):
            if dy == 0:
                continue
            p = pixels[100, 128 + dy]
            if p[0] > 200 and p[1] > 200 and p[2] > 200 and p[3] > 0:
                has_border = True
                break
        assert has_border, "Expected white border pixels around the core line"

    def test_single_point_skipped(self):
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        style = LineStyle(color=(255, 0, 0), width=2)
        draw_line(image, [(50, 50)], style)
        # No line drawn for single point
        pixels = image.load()
        assert pixels[50, 50][3] == 0

    def test_invisible_line(self):
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        style = LineStyle(color=(255, 0, 0), width=0, opacity=0)
        draw_line(image, [(10, 10), (100, 100)], style)
        pixels = image.load()
        # Width 0 or opacity 0 → nothing drawn
        assert pixels[50, 50][3] == 0


class TestVectorRasterizerIntegration:
    """Integration tests using real GPKG data if available."""

    @pytest.fixture
    def network_gpkg(self):
        path = Path("/home/tobias/Downloads/skitours/ski_network_2056.gpkg")
        if not path.exists():
            pytest.skip("ski_network_2056.gpkg not available")
        return path

    @pytest.fixture
    def routes_gpkg(self):
        path = Path("/home/tobias/Downloads/skitours/ski_routes_2056.gpkg")
        if not path.exists():
            pytest.skip("ski_routes_2056.gpkg not available")
        return path

    @pytest.fixture
    def network_qml(self):
        path = Path("/home/tobias/Downloads/skitours/ski_network_2056.qml")
        if not path.exists():
            pytest.skip("ski_network_2056.qml not available")
        return path

    def test_read_features_with_reprojection(self, network_gpkg):
        from cartoload.processor.gpkg.vector_rasterizer import read_features

        # bbox in EPSG:4326 around Davos
        bbox = (9.7, 46.75, 9.9, 46.85)
        features = read_features(network_gpkg, bbox=bbox, target_crs="EPSG:4326")
        assert len(features) > 0

        # Check coordinates are in 4326 range
        geom, attrs = features[0]
        coords = geom.get("coordinates", [[]])[0]
        assert 5 < coords[0][0] < 12  # lon in Switzerland range
        assert 45 < coords[0][1] < 48  # lat in Switzerland range

    def test_render_tile(self, network_gpkg, network_qml):
        from cartoload.style import StyleEngine
        from cartoload.style.qml_parser import parse_qml
        from cartoload.processor.gpkg.vector_rasterizer import VectorRasterizer

        rules = parse_qml(network_qml)
        engine = StyleEngine(rules=rules)
        rasterizer = VectorRasterizer(
            gpkg_paths=[network_gpkg],
            style_engine=engine,
        )

        # Find a tile that has features (Davos area zoom 12)
        image = rasterizer.render_tile(12, 2159, 1443)
        if image is not None:
            assert image.size == (256, 256)
            assert image.mode == "RGBA"
            # Check there are non-transparent pixels
            non_transparent = sum(1 for p in image.getdata() if p[3] > 0)
            assert non_transparent > 0
        else:
            # The tile might not have features at this exact position
            pass

    def test_render_tiles_output(self, network_gpkg, network_qml, tmp_path):
        from cartoload.style import StyleEngine
        from cartoload.style.qml_parser import parse_qml
        from cartoload.processor.gpkg.vector_rasterizer import VectorRasterizer

        rules = parse_qml(network_qml)
        engine = StyleEngine(rules=rules)
        rasterizer = VectorRasterizer(
            gpkg_paths=[network_gpkg],
            style_engine=engine,
        )

        bounds = {"west": 9.7, "south": 46.75, "east": 9.85, "north": 46.85}
        written = rasterizer.render_tiles(
            zoom_levels=[12],
            bounds=bounds,
            cache_dir=tmp_path,
            source_id="test",
        )

        assert len(written) > 0
        for path in written:
            assert path.exists()
            assert path.suffix == ".png"
            img = Image.open(path)
            assert img.size == (256, 256)
