"""Tests for GeoTIFF pre-warping with gdalwarp CLI and VRT mosaic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cartoload.processor.geotiff.prewarp import (
    cleanup_after_warp,
    merge_prewarped_geotiffs,
    prewarp_geotiff,
    _run_gdalwarp,
    _run_gdalbuildvrt,
)


# ---------------------------------------------------------------------------
# Helper: create a minimal GeoTIFF using rasterio
# ---------------------------------------------------------------------------


def _create_geotiff(
    path: Path,
    width: int = 10,
    height: int = 10,
    crs: str = "EPSG:21781",
    paletted: bool = False,
) -> None:
    """Create a minimal GeoTIFF for testing."""
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import ColorInterp
    from rasterio.transform import from_bounds

    data = np.zeros((height, width), dtype="uint8")
    transform = from_bounds(600000, 200000, 600100, 200100, width, height)

    if paletted:
        from rasterio.profiles import DefaultGTiffProfile

        profile = DefaultGTiffProfile(
            count=1,
            width=width,
            height=height,
            crs=CRS.from_user_input(crs),
            transform=transform,
        )
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)
            # Write a colormap
            cmap = {i: (i, i, i, 255) for i in range(256)}
            dst.write_colormap(1, cmap)
            dst.colorinterp = [ColorInterp.palette]
    else:
        import numpy as np

        data3 = np.zeros((3, height, width), dtype="uint8")
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": 3,
            "dtype": "uint8",
            "crs": CRS.from_user_input(crs),
            "transform": transform,
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data3)


def _create_4326_geotiff(
    path: Path,
    width: int = 10,
    height: int = 10,
) -> None:
    """Create a minimal EPSG:4326 RGB GeoTIFF."""
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds

    data = np.zeros((3, height, width), dtype="uint8")
    transform = from_bounds(7.0, 46.0, 7.5, 46.5, width, height)
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 3,
        "dtype": "uint8",
        "crs": CRS.from_epsg(4326),
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


# ---------------------------------------------------------------------------
# Tests for _run_gdalwarp
# ---------------------------------------------------------------------------


class TestRunGdalwarp:
    """Tests for the _run_gdalwarp helper."""

    @patch("cartoload.processor.geotiff.prewarp.subprocess.run")
    def test_basic_invocation(self, mock_run):
        """_run_gdalwarp calls gdalwarp with correct flags."""
        mock_run.return_value = MagicMock(returncode=0)
        src = Path("/tmp/test.tif")
        dst = Path("/tmp/test_4326.tif")

        _run_gdalwarp(src, dst)

        args = mock_run.call_args[0][0]
        assert "-r" in args
        assert "cubic" in args
        assert "-t_srs" in args
        assert "EPSG:4326" in args
        assert "-of" in args
        assert "GTiff" in args
        assert str(src) in args
        assert str(dst) in args

    @patch("cartoload.processor.geotiff.prewarp.subprocess.run")
    def test_no_expand_flag(self, mock_run):
        """gdalwarp is not called with -expand (it's a gdal_translate option)."""
        mock_run.return_value = MagicMock(returncode=0)

        _run_gdalwarp(Path("/tmp/a.tif"), Path("/tmp/b.tif"))

        args = mock_run.call_args[0][0]
        assert "-expand" not in args

    @patch("cartoload.processor.geotiff.prewarp.subprocess.run")
    def test_failure_raises_runtime_error(self, mock_run):
        """Non-zero exit code raises RuntimeError with stderr."""
        mock_run.return_value = MagicMock(returncode=1, stderr="something went wrong")

        with pytest.raises(RuntimeError, match="gdalwarp failed"):
            _run_gdalwarp(Path("/tmp/a.tif"), Path("/tmp/b.tif"))


# ---------------------------------------------------------------------------
# Tests for _run_gdalbuildvrt
# ---------------------------------------------------------------------------


class TestRunGdalbuildvrt:
    """Tests for the _run_gdalbuildvrt helper."""

    @patch("cartoload.processor.geotiff.prewarp.subprocess.run")
    def test_basic_invocation(self, mock_run):
        """_run_gdalbuildvrt calls gdalbuildvrt with correct args."""
        mock_run.return_value = MagicMock(returncode=0)
        vrt = Path("/tmp/mosaic.vrt")
        sources = [Path("/tmp/a_4326.tif"), Path("/tmp/b_4326.tif")]

        _run_gdalbuildvrt(vrt, sources)

        args = mock_run.call_args[0][0]
        assert str(vrt) in args
        assert str(sources[0]) in args
        assert str(sources[1]) in args

    @patch("cartoload.processor.geotiff.prewarp.subprocess.run")
    def test_failure_raises_runtime_error(self, mock_run):
        """Non-zero exit code raises RuntimeError."""
        mock_run.return_value = MagicMock(returncode=1, stderr="build failed")

        with pytest.raises(RuntimeError, match="gdalbuildvrt failed"):
            _run_gdalbuildvrt(Path("/tmp/mosaic.vrt"), [Path("/tmp/a.tif")])


# ---------------------------------------------------------------------------
# Tests for prewarp_geotiff
# ---------------------------------------------------------------------------


class TestPrewarpGeotiff:
    """Tests for prewarp_geotiff."""

    def test_skip_already_4326_rgb(self, tmp_path):
        """File already in EPSG:4326 and 3-band RGB returns source path."""
        src = tmp_path / "test.tif"
        _create_4326_geotiff(src)

        result = prewarp_geotiff(src)
        assert result == src

    @patch("cartoload.processor.geotiff.prewarp._run_gdalwarp")
    def test_warp_creates_cache(self, mock_warp, tmp_path):
        """Non-4326 file triggers gdalwarp and returns cache path."""
        src = tmp_path / "test.tif"
        _create_geotiff(src, crs="EPSG:21781")

        # Simulate gdalwarp creating the output file
        def fake_warp(s, d, **kw):
            _create_4326_geotiff(d)

        mock_warp.side_effect = fake_warp

        result = prewarp_geotiff(src)
        assert result == tmp_path / "test_4326.tif"
        mock_warp.assert_called_once()

    @patch("cartoload.processor.geotiff.prewarp._run_gdalwarp")
    def test_cached_skip(self, mock_warp, tmp_path):
        """Existing fresh cache with completion marker skips warp."""
        src = tmp_path / "test.tif"
        cache = tmp_path / "test_4326.tif"
        marker = tmp_path / "test_4326.json"
        _create_geotiff(src, crs="EPSG:21781")
        _create_4326_geotiff(cache)
        marker.write_text('{"warped": true}')

        result = prewarp_geotiff(src)
        assert result == cache
        mock_warp.assert_not_called()

    @patch("cartoload.processor.geotiff.prewarp._run_gdalwarp")
    @patch("cartoload.processor.geotiff.prewarp._run_gdal_translate_expand")
    def test_paletted_uses_translate_then_warp(
        self, mock_translate, mock_warp, tmp_path
    ):
        """Paletted file is first expanded via gdal_translate, then warped."""
        src = tmp_path / "test.tif"
        _create_geotiff(src, crs="EPSG:21781", paletted=True)

        def fake_translate(s, d):
            _create_4326_geotiff(d)

        def fake_warp(s, d, **kw):
            # The warp input should be the intermediate _rgb.tif, not the source
            assert s.name == "test_rgb.tif"
            _create_4326_geotiff(d)

        mock_translate.side_effect = fake_translate
        mock_warp.side_effect = fake_warp

        prewarp_geotiff(src)

        mock_translate.assert_called_once()
        mock_warp.assert_called_once()
        # Intermediate _rgb.tif should be cleaned up
        assert not (tmp_path / "test_rgb.tif").exists()

    def test_deleted_original_uses_warped_cache(self, tmp_path):
        """When original was deleted after warp, returns warped path directly."""
        src = tmp_path / "test.tif"
        cache = tmp_path / "test_4326.tif"
        marker = tmp_path / "test_4326.json"
        _create_4326_geotiff(cache)
        marker.write_text('{"warped": true}')
        # Source does NOT exist — it was cleaned up after previous warp

        result = prewarp_geotiff(src)
        assert result == cache

    def test_deleted_original_no_warped_returns_source(self, tmp_path):
        """When original and warped are both missing, returns source path."""
        src = tmp_path / "missing.tif"
        # Neither source nor warped cache exists

        result = prewarp_geotiff(src)
        assert result == src


# ---------------------------------------------------------------------------
# Tests for cleanup_after_warp
# ---------------------------------------------------------------------------


class TestCleanupAfterWarp:
    """Tests for cleanup_after_warp."""

    def test_deletes_original_and_writes_json(self, tmp_path):
        """Original file is deleted and metadata JSON is written."""
        src = tmp_path / "test.tif"
        warped = tmp_path / "test_4326.tif"
        src.write_bytes(b"fake tiff data")
        warped.write_bytes(b"fake warped data")

        cleanup_after_warp(src, warped, metadata={"etag": "abc123"})

        assert not src.exists()
        meta_path = tmp_path / "test.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["item_id"] == "test"
        assert meta["original_size"] > 0
        assert meta["etag"] == "abc123"

    def test_preserves_existing_metadata(self, tmp_path):
        """Existing download metadata (etag, url) is preserved when rewriting."""
        src = tmp_path / "test.tif"
        warped = tmp_path / "test_4326.tif"
        src.write_bytes(b"fake tiff data")
        warped.write_bytes(b"fake warped data")

        # Simulate download metadata written by _write_metadata
        meta_path = tmp_path / "test.json"
        meta_path.write_text(
            json.dumps(
                {
                    "item_id": "test",
                    "url": "https://example.com/test.tif",
                    "etag": "original-etag",
                    "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                    "download_date": "2025-01-01T00:00:00+00:00",
                }
            )
        )

        cleanup_after_warp(src, warped, metadata={"new_key": "new_val"})

        assert not src.exists()
        meta = json.loads(meta_path.read_text())
        # Existing fields preserved
        assert meta["etag"] == "original-etag"
        assert meta["url"] == "https://example.com/test.tif"
        assert meta["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"
        assert meta["download_date"] == "2025-01-01T00:00:00+00:00"
        # New fields added
        assert meta["item_id"] == "test"
        assert meta["original_size"] > 0
        assert meta["warp_date"] is not None
        assert meta["new_key"] == "new_val"

    def test_skip_when_warped_equals_source(self, tmp_path):
        """No cleanup when warped path equals source path (no warp needed)."""
        src = tmp_path / "test.tif"
        src.write_bytes(b"data")

        cleanup_after_warp(src, src)

        assert src.exists()

    def test_skip_when_source_missing(self, tmp_path):
        """No error when source file was already deleted."""
        src = tmp_path / "missing.tif"
        warped = tmp_path / "missing_4326.tif"
        warped.write_bytes(b"data")

        cleanup_after_warp(src, warped)  # should not raise


# ---------------------------------------------------------------------------
# Tests for merge_prewarped_geotiffs (VRT)
# ---------------------------------------------------------------------------


class TestMergePrewarpedGeotiffs:
    """Tests for merge_prewarped_geotiffs with VRT output."""

    @patch("cartoload.processor.geotiff.prewarp._run_gdalbuildvrt")
    def test_creates_vrt(self, mock_build_vrt, tmp_path):
        """Calls gdalbuildvrt and returns VRT path."""
        sources = [tmp_path / "a_4326.tif", tmp_path / "b_4326.tif"]
        for s in sources:
            s.write_bytes(b"fake")

        result = merge_prewarped_geotiffs(sources, cache_dir=tmp_path)

        assert result == tmp_path / "mosaic.vrt"
        mock_build_vrt.assert_called_once_with(tmp_path / "mosaic.vrt", sources)

    @patch("cartoload.processor.geotiff.prewarp._run_gdalbuildvrt")
    def test_cached_vrt_skip(self, mock_build_vrt, tmp_path):
        """Existing fresh VRT skips rebuild."""
        sources = [tmp_path / "a_4326.tif"]
        sources[0].write_bytes(b"fake")

        # Create a VRT newer than sources
        vrt = tmp_path / "mosaic.vrt"
        vrt.write_text("<VRTDataset/>")

        result = merge_prewarped_geotiffs(sources, cache_dir=tmp_path)

        assert result == vrt
        mock_build_vrt.assert_not_called()

    def test_empty_paths_raises(self, tmp_path):
        """Empty path list raises ValueError."""
        with pytest.raises(ValueError, match="No pre-warped GeoTIFFs"):
            merge_prewarped_geotiffs([], cache_dir=tmp_path)
