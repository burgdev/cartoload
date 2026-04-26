"""Tests for per-tile reprojection: reproject_tile, cache-aware wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cartoload.downloader.base import BaseDownloader
from cartoload.processor.reproject import (
    ReprojectionError,
    reproject_tile,
    reproject_tile_cached,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyDownloader(BaseDownloader):
    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        return Path("/dummy")

    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        return []


def _make_downloader(tmp_path: Path) -> _DummyDownloader:
    return _DummyDownloader("test_source", tmp_path / "cache")


def _mock_gdalwarp_success(cmd, **kwargs):
    """Simulate successful gdalwarp by writing output file."""
    # cmd is the full arg list, output path is the last element
    Path(cmd[-1]).write_bytes(b"reprojected-tiff")
    return MagicMock(returncode=0, stderr="")


# ===================================================================
# 4.1 – reproject_tile tests
# ===================================================================


class TestReprojectTile:
    """Tests for reproject_tile function."""

    @patch(
        "cartoload.processor.reproject.shutil.which", return_value="/usr/bin/gdalwarp"
    )
    @patch("cartoload.processor.reproject.subprocess.run")
    def test_successful_reprojection(
        self, mock_run, mock_which, tmp_path: Path
    ) -> None:
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source-tile")
        output = tmp_path / "output.tif"

        mock_run.side_effect = _mock_gdalwarp_success

        result = reproject_tile(source, "EPSG:3857", "EPSG:4326", output)
        assert result == output
        assert output.exists()

    @patch("cartoload.processor.reproject.shutil.which", return_value=None)
    def test_gdalwarp_not_found(self, mock_which, tmp_path: Path) -> None:
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")
        output = tmp_path / "output.tif"

        with pytest.raises(FileNotFoundError, match="gdalwarp not found"):
            reproject_tile(source, "EPSG:3857", "EPSG:4326", output)

    @patch(
        "cartoload.processor.reproject.shutil.which", return_value="/usr/bin/gdalwarp"
    )
    @patch("cartoload.processor.reproject.subprocess.run")
    def test_gdalwarp_failure(self, mock_run, mock_which, tmp_path: Path) -> None:
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")
        output = tmp_path / "output.tif"

        mock_run.return_value = MagicMock(returncode=1, stderr="error message")

        with pytest.raises(ReprojectionError, match="gdalwarp failed"):
            reproject_tile(source, "EPSG:3857", "EPSG:4326", output)

    @patch(
        "cartoload.processor.reproject.shutil.which", return_value="/usr/bin/gdalwarp"
    )
    @patch("cartoload.processor.reproject.subprocess.run")
    def test_gdalwarp_failure_cleans_up(
        self, mock_run, mock_which, tmp_path: Path
    ) -> None:
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")
        output = tmp_path / "output.tif"
        # Pre-create a partial output
        output.write_bytes(b"partial")

        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with pytest.raises(ReprojectionError):
            reproject_tile(source, "EPSG:3857", "EPSG:4326", output)

        assert not output.exists()

    @patch(
        "cartoload.processor.reproject.shutil.which", return_value="/usr/bin/gdalwarp"
    )
    @patch("cartoload.processor.reproject.subprocess.run")
    def test_creates_parent_dirs(self, mock_run, mock_which, tmp_path: Path) -> None:
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")
        output = tmp_path / "deep" / "nested" / "output.tif"

        mock_run.side_effect = _mock_gdalwarp_success

        reproject_tile(source, "EPSG:3857", "EPSG:4326", output)
        assert output.parent.exists()

    @patch(
        "cartoload.processor.reproject.shutil.which", return_value="/usr/bin/gdalwarp"
    )
    @patch("cartoload.processor.reproject.subprocess.run")
    def test_gdalwarp_command_args(self, mock_run, mock_which, tmp_path: Path) -> None:
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")
        output = tmp_path / "output.tif"

        mock_run.side_effect = _mock_gdalwarp_success

        reproject_tile(source, "EPSG:3857", "EPSG:4326", output)

        call_args = mock_run.call_args[0][0]
        assert "gdalwarp" in call_args[0]
        assert "-s_srs" in call_args
        assert "EPSG:3857" in call_args
        assert "-t_srs" in call_args
        assert "EPSG:4326" in call_args


# ===================================================================
# 4.2 – reproject_tile_cached tests
# ===================================================================


class TestReprojectTileCached:
    """Tests for the cache-aware wrapper."""

    def test_same_crs_returns_source(self, tmp_path: Path) -> None:
        """If source CRS equals target CRS, return source path directly."""
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")

        result = reproject_tile_cached(
            source, 0, 0, 0, "EPSG:4326", "EPSG:4326", "tif", dl
        )
        assert result == source

    def test_cache_hit_returns_cached(self, tmp_path: Path) -> None:
        """If valid cache exists, return it without reprojecting."""
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")

        # Create a cached reprojected tile that is newer than source
        cached = dl.reprojection_cache_path(0, 0, 0, "EPSG:4326", "tif")
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(b"cached-reproj")

        # Ensure cached is newer
        import time

        time.sleep(0.05)
        # Re-read source mtime; cached should be newer since we wrote it after
        source.write_bytes(b"source")
        # Re-create cached to be newer
        time.sleep(0.05)
        cached.write_bytes(b"cached-reproj-newer")

        result = reproject_tile_cached(
            source, 0, 0, 0, "EPSG:3857", "EPSG:4326", "tif", dl
        )
        assert result == cached

    @patch("cartoload.processor.reproject.reproject_tile")
    def test_cache_miss_reprojects(self, mock_reproj, tmp_path: Path) -> None:
        """If no valid cache, reproject and return result."""
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        source.write_bytes(b"source")

        expected_output = dl.reprojection_cache_path(0, 0, 0, "EPSG:4326", "tif")
        mock_reproj.return_value = expected_output

        result = reproject_tile_cached(
            source, 0, 0, 0, "EPSG:3857", "EPSG:4326", "tif", dl
        )
        assert result == expected_output
        mock_reproj.assert_called_once()

    @patch("cartoload.processor.reproject.reproject_tile")
    def test_stale_cache_reprojects(self, mock_reproj, tmp_path: Path) -> None:
        """If cache is stale (source newer), reproject again."""
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"

        # Write cached first, then source (source is newer)
        cached = dl.reprojection_cache_path(0, 0, 0, "EPSG:4326", "tif")
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(b"old-cached")

        import time

        time.sleep(0.05)
        source.write_bytes(b"new-source")

        expected_output = dl.reprojection_cache_path(0, 0, 0, "EPSG:4326", "tif")
        mock_reproj.return_value = expected_output

        reproject_tile_cached(source, 0, 0, 0, "EPSG:3857", "EPSG:4326", "tif", dl)
        mock_reproj.assert_called_once()
