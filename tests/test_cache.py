"""Tests for two-tier cache: paths, invalidation, CRS checks, and CLI commands."""

from __future__ import annotations

import time
from pathlib import Path

import click.testing
import pytest

from cartoload.cli import main
from cartoload.downloader.base import BaseDownloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyDownloader(BaseDownloader):
    """Minimal concrete downloader for testing cache methods."""

    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        return Path("/dummy")

    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        return []


def _make_downloader(tmp_path: Path, crs: str | None = None) -> _DummyDownloader:
    return _DummyDownloader("test_source", tmp_path / "cache", crs=crs)


@pytest.fixture
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


# ===================================================================
# 3.1 – Reprojection cache path tests
# ===================================================================


class TestReprojectionCachePath:
    """Tests for reprojection_cache_path and reprojection_cache_dir."""

    def test_path_format(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        path = dl.reprojection_cache_path(541, 362, 10, "EPSG:4326", "jpeg")
        assert (
            path
            == tmp_path / "cache" / "test_source_epsg_4326" / "10" / "541" / "362.jpeg"
        )

    def test_path_with_png(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        path = dl.reprojection_cache_path(0, 0, 5, "EPSG:4326", "png")
        assert path.suffix == ".png"

    def test_path_crs_normalization(self, tmp_path: Path) -> None:
        """CRS should be lowercased and colons replaced with underscores."""
        dl = _make_downloader(tmp_path)
        path = dl.reprojection_cache_path(0, 0, 0, "EPSG:4326", "jpeg")
        assert "test_source_epsg_4326" in str(path)

    def test_static_cache_dir(self) -> None:
        cache_dir = Path("/tmp/cache")
        result = BaseDownloader.reprojection_cache_dir(
            cache_dir, "my_source", "EPSG:4326"
        )
        assert result == Path("/tmp/cache/my_source_epsg_4326")

    def test_different_target_crs(self, tmp_path: Path) -> None:
        """Different target CRS should produce different paths."""
        dl = _make_downloader(tmp_path)
        path_4326 = dl.reprojection_cache_path(0, 0, 0, "EPSG:4326", "jpeg")
        path_3857 = dl.reprojection_cache_path(0, 0, 0, "EPSG:3857", "jpeg")
        assert path_4326 != path_3857


# ===================================================================
# 3.2 – mtime-based invalidation tests
# ===================================================================


class TestMtimeInvalidation:
    """Tests for is_reprojection_valid."""

    def test_valid_when_reprojected_newer(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        reproj = tmp_path / "reproj.jpeg"
        source.write_bytes(b"source")
        time.sleep(0.05)
        reproj.write_bytes(b"reprojected")

        assert dl.is_reprojection_valid(source, reproj) is True

    def test_invalid_when_reprojected_older(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        reproj = tmp_path / "reproj.jpeg"
        reproj.write_bytes(b"reprojected")
        time.sleep(0.05)
        source.write_bytes(b"source-updated")

        assert dl.is_reprojection_valid(source, reproj) is False

    def test_invalid_when_reprojected_missing(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        reproj = tmp_path / "reproj.jpeg"
        source.write_bytes(b"source")

        assert dl.is_reprojection_valid(source, reproj) is False

    def test_invalid_when_source_missing(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        reproj = tmp_path / "reproj.jpeg"
        reproj.write_bytes(b"reprojected")

        assert dl.is_reprojection_valid(source, reproj) is False

    def test_invalid_when_reprojected_empty(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        reproj = tmp_path / "reproj.jpeg"
        source.write_bytes(b"source")
        reproj.write_bytes(b"")

        assert dl.is_reprojection_valid(source, reproj) is False

    def test_valid_when_same_mtime(self, tmp_path: Path) -> None:
        """If mtimes are equal, reprojection should be considered valid."""
        dl = _make_downloader(tmp_path)
        source = tmp_path / "source.jpeg"
        reproj = tmp_path / "reproj.jpeg"
        source.write_bytes(b"source")
        reproj.write_bytes(b"reprojected")
        # Force same mtime
        mtime = source.stat().st_mtime
        import os

        os.utime(reproj, (mtime, mtime))

        assert dl.is_reprojection_valid(source, reproj) is True


# ===================================================================
# 3.3 – needs_reprojection tests
# ===================================================================


class TestNeedsReprojection:
    """Tests for the needs_reprojection static method."""

    def test_different_crs(self) -> None:
        assert BaseDownloader.needs_reprojection("EPSG:3857", "EPSG:4326") is True

    def test_same_crs(self) -> None:
        assert BaseDownloader.needs_reprojection("EPSG:4326", "EPSG:4326") is False

    def test_case_insensitive(self) -> None:
        assert BaseDownloader.needs_reprojection("epsg:4326", "EPSG:4326") is False

    def test_none_source(self) -> None:
        assert BaseDownloader.needs_reprojection(None, "EPSG:4326") is True

    def test_whitespace_handling(self) -> None:
        assert BaseDownloader.needs_reprojection("  EPSG:4326  ", "EPSG:4326") is False


# ===================================================================
# 3.4-3.5 – CLI cache commands
# ===================================================================


class TestCacheStatusCommand:
    """Tests for cartoload cache status."""

    def test_empty_cache(self, runner: click.testing.CliRunner, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = runner.invoke(main, ["cache", "-c", str(cache_dir), "status"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_nonexistent_cache_dir(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            main, ["cache", "-c", str(tmp_path / "nonexistent"), "status"]
        )
        assert result.exit_code == 0
        assert "does not exist" in result.output

    def test_status_with_tiles(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        source_dir = cache_dir / "my_source" / "10" / "541"
        source_dir.mkdir(parents=True)
        (source_dir / "362.jpeg").write_bytes(b"tile-data")
        (source_dir / "363.jpeg").write_bytes(b"tile-data")

        result = runner.invoke(main, ["cache", "-c", str(cache_dir), "status"])
        assert result.exit_code == 0
        assert "my_source" in result.output
        assert "download" in result.output
        assert "Tiles: 2" in result.output

    def test_status_with_reprojection_cache(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        reproj_dir = cache_dir / "my_source_epsg_4326" / "10" / "541"
        reproj_dir.mkdir(parents=True)
        (reproj_dir / "362.jpeg").write_bytes(b"reproj-data")

        result = runner.invoke(main, ["cache", "-c", str(cache_dir), "status"])
        assert result.exit_code == 0
        assert "my_source_epsg_4326" in result.output
        assert "reprojection" in result.output

    def test_status_shows_total(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        source_dir = cache_dir / "src" / "10" / "0"
        source_dir.mkdir(parents=True)
        (source_dir / "0.jpeg").write_bytes(b"x" * 1024)

        result = runner.invoke(main, ["cache", "-c", str(cache_dir), "status"])
        assert result.exit_code == 0
        assert "Total:" in result.output


class TestCacheCleanCommand:
    """Tests for cartoload cache clean."""

    def test_clean_empty_cache(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = runner.invoke(
            main, ["cache", "-c", str(cache_dir), "clean", "--force"]
        )
        assert result.exit_code == 0
        assert "Nothing to clean" in result.output

    def test_clean_nonexistent_cache(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            main, ["cache", "-c", str(tmp_path / "nonexistent"), "clean", "--force"]
        )
        assert result.exit_code == 0
        assert "does not exist" in result.output

    def test_clean_all_with_force(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        source_dir = cache_dir / "my_source" / "10"
        source_dir.mkdir(parents=True)
        (source_dir / "tile.jpeg").write_bytes(b"data")

        result = runner.invoke(
            main, ["cache", "-c", str(cache_dir), "clean", "--force"]
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not source_dir.exists()

    def test_clean_specific_source(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        dir_a = cache_dir / "source_a" / "10"
        dir_b = cache_dir / "source_b" / "10"
        dir_a.mkdir(parents=True)
        dir_b.mkdir(parents=True)
        (dir_a / "tile.jpeg").write_bytes(b"a")
        (dir_b / "tile.jpeg").write_bytes(b"b")

        result = runner.invoke(
            main,
            [
                "cache",
                "-c",
                str(cache_dir),
                "clean",
                "--source",
                "source_a",
                "--force",
            ],
        )
        assert result.exit_code == 0
        assert not dir_a.exists()
        assert dir_b.exists()

    def test_clean_also_removes_reprojection_for_source(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        dl_dir = cache_dir / "my_source" / "10"
        rp_dir = cache_dir / "my_source_epsg_4326" / "10"
        dl_dir.mkdir(parents=True)
        rp_dir.mkdir(parents=True)
        (dl_dir / "tile.jpeg").write_bytes(b"dl")
        (rp_dir / "tile.jpeg").write_bytes(b"rp")

        result = runner.invoke(
            main,
            [
                "cache",
                "-c",
                str(cache_dir),
                "clean",
                "--source",
                "my_source",
                "--force",
            ],
        )
        assert result.exit_code == 0
        assert not dl_dir.exists()
        assert not rp_dir.exists()

    def test_clean_reprojection_only(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        dl_dir = cache_dir / "my_source" / "10"
        rp_dir = cache_dir / "my_source_epsg_4326" / "10"
        dl_dir.mkdir(parents=True)
        rp_dir.mkdir(parents=True)
        (dl_dir / "tile.jpeg").write_bytes(b"dl")
        (rp_dir / "tile.jpeg").write_bytes(b"rp")

        result = runner.invoke(
            main,
            [
                "cache",
                "-c",
                str(cache_dir),
                "clean",
                "--reprojection-only",
                "--force",
            ],
        )
        assert result.exit_code == 0
        assert not rp_dir.exists()
        assert dl_dir.exists()

    def test_clean_prompts_without_force(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        source_dir = cache_dir / "my_source"
        source_dir.mkdir(parents=True)
        (source_dir / "tile.jpeg").write_bytes(b"data")

        # Respond 'n' to the confirmation prompt
        result = runner.invoke(
            main,
            ["cache", "-c", str(cache_dir), "clean"],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output
        assert source_dir.exists()

    def test_clean_confirmed_interactive(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        source_dir = cache_dir / "my_source"
        source_dir.mkdir(parents=True)
        (source_dir / "tile.jpeg").write_bytes(b"data")

        result = runner.invoke(
            main,
            ["cache", "-c", str(cache_dir), "clean"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not source_dir.exists()
