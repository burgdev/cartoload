"""Tests for CLI commands: build, download, split, list, and error messages."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import click.testing
import pytest
import yaml

from cartoload.cli import _human_size, _parse_bounds, _parse_zoom, main
from cartoload.pipeline import DownloadError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_files(
    tmp_path: Path,
    source_id: str = "test_src",
    source_type: str = "geotiff",
    layer_id: str = "test_layer",
    **layer_overrides,
) -> tuple[Path, Path]:
    """Create minimal source + layer config YAML files."""
    sources_data = {
        "sources": {
            source_id: {
                "type": source_type,
                "stac_url": "https://stac.example.com",
            }
        }
    }
    layer_def = {
        "name": "Test Layer",
        "source": source_id,
        "zoom_levels": [12, 14],
        "exporter": "garmin-img",
        "output": "test_layer.img",
    }
    layer_def.update(layer_overrides)
    layers_data = {
        "bounds": {"west": 5.0, "south": 45.0, "east": 10.0, "north": 48.0},
        "layers": {layer_id: layer_def},
    }

    src_file = tmp_path / "sources.yaml"
    src_file.write_text(yaml.dump(sources_data))
    lyr_file = tmp_path / "layers.yaml"
    lyr_file.write_text(yaml.dump(layers_data))
    return src_file, lyr_file


@pytest.fixture
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestParseBounds:
    def test_valid(self):
        result = _parse_bounds("5.0,45.0,10.0,48.0")
        assert result == {"west": 5.0, "south": 45.0, "east": 10.0, "north": 48.0}

    def test_none(self):
        assert _parse_bounds(None) is None

    def test_invalid_parts_count(self):
        with pytest.raises(click.BadParameter, match="west,south,east,north"):
            _parse_bounds("1,2,3")

    def test_non_numeric(self):
        with pytest.raises(click.BadParameter, match="numeric"):
            _parse_bounds("a,b,c,d")


class TestParseZoom:
    def test_valid(self):
        assert _parse_zoom("10,12,14") == [10, 12, 14]

    def test_none(self):
        assert _parse_zoom(None) is None

    def test_non_numeric(self):
        with pytest.raises(click.BadParameter, match="integers"):
            _parse_zoom("a,b")


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500) == "500.0 B"

    def test_kb(self):
        assert _human_size(2048) == "2.0 KB"

    def test_mb(self):
        assert _human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gb(self):
        assert _human_size(2 * 1024**3) == "2.0 GB"


# ---------------------------------------------------------------------------
# 10.1 build command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_requires_layer_flag(self, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        result = runner.invoke(
            main,
            ["build", "--sources", str(src), "--layers", str(lyr)],
        )
        assert result.exit_code != 0
        assert "--layer is required" in result.output

    def test_missing_layer_id(self, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path, layer_id="real_layer")
        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "nonexistent",
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("cartoload.cli.asyncio.run")
    def test_build_invokes_pipeline(self, mock_asyncio_run, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)

        # Make asyncio.run return a fake output path
        output_path = tmp_path / "output" / "test_layer.img"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x00" * 1024)
        mock_asyncio_run.return_value = [output_path]

        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "test_layer",
                "--output-dir",
                str(tmp_path / "output"),
                "--cache-dir",
                str(tmp_path / "cache"),
            ],
        )
        assert result.exit_code == 0
        assert "Output:" in result.output
        mock_asyncio_run.assert_called_once()

    @patch("cartoload.cli.asyncio.run")
    def test_build_with_no_download(self, mock_asyncio_run, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        output_path = tmp_path / "output" / "test_layer.img"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x00" * 512)
        mock_asyncio_run.return_value = [output_path]

        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "test_layer",
                "--no-download",
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code == 0

    @patch("cartoload.cli.asyncio.run", side_effect=DownloadError("src", "fail"))
    def test_build_download_error(self, mock_run, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "test_layer",
            ],
        )
        assert result.exit_code != 0
        assert "Download failed" in result.output

    @patch("cartoload.cli.asyncio.run", side_effect=Exception("unexpected"))
    def test_build_unexpected_error(self, mock_run, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "test_layer",
            ],
        )
        assert result.exit_code != 0
        assert "Unexpected error" in result.output
        assert "report this issue" in result.output


# ---------------------------------------------------------------------------
# 10.2 download command
# ---------------------------------------------------------------------------


class TestDownloadCommand:
    def test_requires_layer_flag(self, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        result = runner.invoke(
            main,
            ["download", "--sources", str(src), "--layers", str(lyr)],
        )
        assert result.exit_code != 0
        assert "--layer is required" in result.output

    @patch("cartoload.cli.get_downloader")
    def test_download_invokes_downloader(self, mock_get_dl, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        mock_dl = MagicMock()
        tile = tmp_path / "cache" / "tile.tif"
        tile.parent.mkdir(parents=True, exist_ok=True)
        tile.write_bytes(b"\x00" * 1024)
        mock_dl.run.return_value = [tile]
        mock_get_dl.return_value = mock_dl

        result = runner.invoke(
            main,
            [
                "download",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "test_layer",
                "--cache-dir",
                str(tmp_path / "cache"),
            ],
        )
        assert result.exit_code == 0
        assert "Downloaded" in result.output
        mock_dl.run.assert_called_once()

    def test_download_missing_layer(self, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path, layer_id="other")
        result = runner.invoke(
            main,
            [
                "download",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
                "--layer",
                "nonexistent",
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# 10.3 split command
# ---------------------------------------------------------------------------


class TestSplitCommand:
    def test_file_not_found(self, runner, tmp_path):
        result = runner.invoke(main, ["split", str(tmp_path / "nonexistent.img")])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_small_file_no_split(self, runner, tmp_path):
        small = tmp_path / "small.img"
        small.write_bytes(b"\x00" * 1024)
        result = runner.invoke(main, ["split", str(small)])
        assert result.exit_code == 0
        assert "not needed" in result.output

    @patch("cartoload.cli.shutil.which", return_value=None)
    def test_gmt_not_found(self, mock_which, runner, tmp_path):
        big = tmp_path / "big.img"
        big.write_bytes(b"\x00" * (4_294_967_297))  # > 4 GB
        # Can't actually write 4GB, so patch stat instead
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 5_000_000_000
            result = runner.invoke(main, ["split", str(big)])
            assert result.exit_code != 0
            assert "gmt" in result.output.lower() or "GMapTool" in result.output

    @patch("cartoload.cli.shutil.which", return_value="/usr/bin/gmt")
    @patch("cartoload.cli.subprocess.run")
    def test_split_success(self, mock_run, mock_which, runner, tmp_path):
        big = tmp_path / "big.img"
        big.write_bytes(b"\x00" * 1024)
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 5_000_000_000
            result = runner.invoke(main, ["split", str(big)])
            assert result.exit_code == 0
            assert "Split complete" in result.output
            mock_run.assert_called_once()

    @patch("cartoload.cli.shutil.which", return_value="/usr/bin/gmt")
    @patch("cartoload.cli.subprocess.run")
    def test_split_gmt_failure(self, mock_run, mock_which, runner, tmp_path):
        big = tmp_path / "big.img"
        big.write_bytes(b"\x00" * 1024)
        mock_run.return_value = MagicMock(returncode=1, stderr="error details")

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 5_000_000_000
            result = runner.invoke(main, ["split", str(big)])
            assert result.exit_code != 0
            assert "gmt failed" in result.output


# ---------------------------------------------------------------------------
# 10.4 Error messages
# ---------------------------------------------------------------------------


class TestErrorMessages:
    def test_missing_config_file(self, runner, tmp_path):
        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(tmp_path / "missing.yaml"),
                "--layers",
                str(tmp_path / "missing.yaml"),
                "--layer",
                "x",
            ],
        )
        assert result.exit_code != 0

    def test_unknown_source_type_error(self, runner, tmp_path):
        """Config with unknown source type should give clear error."""
        src = tmp_path / "sources.yaml"
        src.write_text(
            yaml.dump(
                {
                    "sources": {
                        "bad_src": {"type": "invalid_type"},
                    }
                }
            )
        )
        result = runner.invoke(
            main,
            [
                "build",
                "--sources",
                str(src),
                "--layers",
                str(tmp_path / "layers.yaml"),
                "--layer",
                "x",
            ],
        )
        assert result.exit_code != 0

    def test_list_no_config(self, runner):
        result = runner.invoke(main, ["list"])
        assert result.exit_code != 0

    def test_list_valid_config(self, runner, tmp_path):
        src, lyr = _make_config_files(tmp_path)
        result = runner.invoke(
            main,
            [
                "list",
                "--sources",
                str(src),
                "--layers",
                str(lyr),
            ],
        )
        assert result.exit_code == 0
        assert "test_layer" in result.output
        assert "Test Layer" in result.output
