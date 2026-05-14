"""Tests for dry-run flag: build plan display without file creation."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cartoload.cli import main


def _write_config(tmp_path: Path) -> str:
    """Write a unified config file, return its path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "sources": {
                    "test_src": {
                        "type": "wmts",
                        "url_template": "https://example.com/{z}/{x}/{y}.jpeg",
                    }
                },
                "bounds": {
                    "west": 7.0,
                    "east": 8.0,
                    "south": 46.0,
                    "north": 47.0,
                },
                "layers": {
                    "test_layer": {
                        "name": "Test Layer",
                        "source": "test_src",
                        "zoom_levels": [10],
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                },
            }
        )
    )

    return str(config_file)


class TestDryRun:
    def test_dry_run_shows_summary(self, tmp_path: Path) -> None:
        """Dry run should display build plan summary."""
        config = _write_config(tmp_path)
        output_dir = tmp_path / "output"
        cache_dir = tmp_path / "cache"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "build",
                "-c",
                config,
                "-l",
                "test_layer",
                "-o",
                str(output_dir),
                "-C",
                str(cache_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Build plan" in result.output
        assert "Dry run" in result.output

    def test_dry_run_creates_no_output_dir(self, tmp_path: Path) -> None:
        """Dry run should not create the output directory."""
        config = _write_config(tmp_path)
        output_dir = tmp_path / "output"
        cache_dir = tmp_path / "cache"

        runner = CliRunner()
        runner.invoke(
            main,
            [
                "build",
                "-c",
                config,
                "-l",
                "test_layer",
                "-o",
                str(output_dir),
                "-C",
                str(cache_dir),
                "--dry-run",
            ],
        )

        # Output dir should not exist (no files created)
        assert not output_dir.exists()

    def test_dry_run_creates_no_cache_files(self, tmp_path: Path) -> None:
        """Dry run should not write any cache files."""
        config = _write_config(tmp_path)
        output_dir = tmp_path / "output"
        cache_dir = tmp_path / "cache"

        runner = CliRunner()
        runner.invoke(
            main,
            [
                "build",
                "-c",
                config,
                "-l",
                "test_layer",
                "-o",
                str(output_dir),
                "-C",
                str(cache_dir),
                "--dry-run",
            ],
        )

        # No cache directory should be created
        assert not cache_dir.exists()

    def test_dry_run_creates_no_img_files(self, tmp_path: Path) -> None:
        """Dry run should not create any IMG files."""
        config = _write_config(tmp_path)
        output_dir = tmp_path / "output"
        cache_dir = tmp_path / "cache"

        runner = CliRunner()
        runner.invoke(
            main,
            [
                "build",
                "-c",
                config,
                "-l",
                "test_layer",
                "-o",
                str(output_dir),
                "-C",
                str(cache_dir),
                "--dry-run",
            ],
        )

        # No .img files anywhere in tmp_path
        img_files = list(tmp_path.rglob("*.img"))
        assert len(img_files) == 0
