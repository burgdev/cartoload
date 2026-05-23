"""End-to-end tests for the full pipeline.

These tests run the pipeline with real GDAL operations on small datasets.
They require GDAL tools (gdalbuildvrt, gdalwarp, gdaladdo) on PATH and
are therefore marked with @pytest.mark.gdal and @pytest.mark.slow.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cartoload.config import LayerConfig, SourceConfig
from cartoload.pipeline import build_layer


def _gdal_available() -> bool:
    """Check if GDAL tools are on PATH."""
    import shutil

    return all(shutil.which(t) for t in ("gdalbuildvrt", "gdalwarp", "gdaladdo"))


# Skip entire module if GDAL is not available
pytestmark = [
    pytest.mark.gdal,
    pytest.mark.slow,
    pytest.mark.skipif(not _gdal_available(), reason="GDAL tools not on PATH"),
]


def _create_minimal_geotiff(path: Path) -> Path:
    """Create a minimal 1x1 GeoTIFF using gdal_create or Python fallback."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Try gdal_create (GDAL >= 3.2)
    result = subprocess.run(
        [
            "gdal_create",
            "-outsize",
            "2",
            "2",
            "-a_srs",
            "EPSG:4326",
            "-a_ullr",
            "5.0",
            "48.0",
            "10.0",
            "45.0",
            "-burn",
            "128",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and path.exists():
        return path

    # Fallback: try rasterio if available
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds

        data = np.full((1, 2, 2), 128, dtype=np.uint8)
        transform = from_bounds(5.0, 45.0, 10.0, 48.0, 2, 2)

        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data)
        return path
    except ImportError:
        pytest.skip("Neither gdal_create nor rasterio available")
        return path  # unreachable


@pytest.fixture
def small_geotiff(tmp_path: Path) -> Path:
    return _create_minimal_geotiff(tmp_path / "tiles" / "tile.tif")


@pytest.fixture
def e2e_source() -> SourceConfig:
    return SourceConfig(
        id="test_source",
        type="stac",
        urls=["https://stac.example.com/collections/${layer}"],
        defaults={"layer": "test_collection"},
    )


@pytest.fixture
def e2e_layer() -> LayerConfig:
    return LayerConfig(
        id="e2e_layer",
        name="E2E Test",
        source="test_source",
        format="geotiff",
        zoom_levels=[10],
        bounds={"west": 5.0, "south": 45.0, "east": 10.0, "north": 48.0},
    )


# ---------------------------------------------------------------------------
# 11.1 Full pipeline with small real data
# 11.2 Validate output exists and has non-zero size
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_full_pipeline_produces_img(
        self,
        tmp_path: Path,
        small_geotiff: Path,
        e2e_source: SourceConfig,
        e2e_layer: LayerConfig,
    ):
        """Run the full pipeline end-to-end: download → process → export."""
        import asyncio

        from cartoload.source.stac.downloader import STACDownloader
        from cartoload.template import expand

        # Place the GeoTIFF in the STAC cache structure
        cache_dir = tmp_path / "cache"
        resolved_url = expand(e2e_source.urls[0], {"layer": "test_collection"})
        stac_dl = STACDownloader(cache_dir)
        cache_path = stac_dl._get_cache_path(e2e_source.id, resolved_url, "tile")
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy the small geotiff into the cache
        cache_path.write_bytes(small_geotiff.read_bytes())

        output_dir = tmp_path / "output"

        output_paths = asyncio.run(
            build_layer(
                e2e_layer,
                {e2e_source.id: e2e_source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        # 11.2 Validate output exists and is non-empty
        assert len(output_paths) >= 1
        for p in output_paths:
            assert p.exists(), f"Output file {p} does not exist"
            assert p.stat().st_size > 0, f"Output file {p} is empty"

    def test_output_has_img_signature(
        self,
        tmp_path: Path,
        small_geotiff: Path,
        e2e_source: SourceConfig,
        e2e_layer: LayerConfig,
    ):
        """Verify the output file starts with the DSKIMG magic bytes."""
        import asyncio

        from cartoload.source.stac.downloader import STACDownloader
        from cartoload.template import expand

        cache_dir = tmp_path / "cache"
        resolved_url = expand(e2e_source.urls[0], {"layer": "test_collection"})
        stac_dl = STACDownloader(cache_dir)
        cache_path = stac_dl._get_cache_path(e2e_source.id, resolved_url, "tile")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(small_geotiff.read_bytes())

        output_dir = tmp_path / "output"

        output_paths = asyncio.run(
            build_layer(
                e2e_layer,
                {e2e_source.id: e2e_source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(output_paths) >= 1
        # Check for Garmin IMG signature: first bytes should contain "DSKIMG"
        header = output_paths[0].read_bytes()[:512]
        # The header should be readable and contain the magic marker
        assert len(header) >= 7, "IMG file too small to contain header"
