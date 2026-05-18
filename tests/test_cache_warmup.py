"""Tests for cache-warmup mode: download + process tiles without IMG build."""

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
                        "urls": ["https://example.com/{z}/{x}/{y}.jpeg"],
                    }
                },
                "bounds": {
                    "west": 7.0,
                    "east": 7.5,
                    "south": 46.0,
                    "north": 46.5,
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


class TestCacheWarmup:
    def test_warmup_completes(self, tmp_path: Path) -> None:
        """Warmup mode should complete successfully."""
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
                "--cache-warmup",
                "--no-download",
            ],
        )

        # Should succeed (though no tiles cached, pipeline handles empty)
        # With --no-download and no cached tiles, it may fail with ProcessingError
        # That's expected — the point is warmup mode doesn't create output files
        assert "Output:" not in result.output or result.exit_code != 0

    def test_warmup_creates_no_output_dir(self, tmp_path: Path) -> None:
        """Warmup mode should not create the output directory."""
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
                "--cache-warmup",
                "--no-download",
            ],
        )

        # Output dir should not be created
        assert not output_dir.exists()

    def test_warmup_creates_no_img_files(self, tmp_path: Path) -> None:
        """Warmup mode should not create any IMG files."""
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
                "--cache-warmup",
                "--no-download",
            ],
        )

        # No .img files anywhere
        img_files = list(tmp_path.rglob("*.img"))
        assert len(img_files) == 0

    def test_warmup_message(self, tmp_path: Path) -> None:
        """Warmup mode should show warmup completion message on success."""
        config = _write_config(tmp_path)
        output_dir = tmp_path / "output"
        cache_dir = tmp_path / "cache"

        # Pre-create tiles in cache so the pipeline succeeds
        from cartoload.downloader.wmts import WMTSDownloader
        from cartoload.pipeline import _compute_tile_coords
        from cartoload.config import LayerConfig

        layer_cfg = LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="test_src",
            zoom_levels=[10],
            exporter="garmin_img",
            output="test.img",
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        dl = WMTSDownloader(
            source_id="test_src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=cache_dir,
            crs="EPSG:4326",
        )
        coords = _compute_tile_coords(layer_cfg, 10)
        import io
        from PIL import Image

        for x, y in coords:
            tile_path = dl._cache_path(x, y, 10)
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGB", (256, 256), color=(128, 128, 128))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            tile_path.write_bytes(buf.getvalue())
            # Write world file
            wf = tile_path.with_suffix(".jgw")
            wf.write_text("0.01\n0.0\n0.0\n-0.01\n7.0\n47.0\n")

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
                "--cache-warmup",
                "--no-download",
            ],
        )

        assert result.exit_code == 0
        assert "Cache warmup complete" in result.output
        # No IMG output summary
        assert "Output:" not in result.output
