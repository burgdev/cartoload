"""Tests for cache CLI commands: status and clean."""

from __future__ import annotations

from pathlib import Path

import click.testing
import pytest

from cartoload.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


# ===================================================================
# CLI cache commands
# ===================================================================


class TestCacheStatusCommand:
    """Tests for cartoload cache status."""

    def test_empty_cache(self, runner: click.testing.CliRunner, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = runner.invoke(main, ["cache", "-C", str(cache_dir), "status"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_nonexistent_cache_dir(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            main, ["cache", "-C", str(tmp_path / "nonexistent"), "status"]
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

        result = runner.invoke(main, ["cache", "-C", str(cache_dir), "status"])
        assert result.exit_code == 0
        assert "my_source" in result.output
        assert "Tiles: 2" in result.output

    def test_status_shows_total(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / "cache"
        source_dir = cache_dir / "src" / "10" / "0"
        source_dir.mkdir(parents=True)
        (source_dir / "0.jpeg").write_bytes(b"x" * 1024)

        result = runner.invoke(main, ["cache", "-C", str(cache_dir), "status"])
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
            main, ["cache", "-C", str(cache_dir), "clean", "--force"]
        )
        assert result.exit_code == 0
        assert "Nothing to clean" in result.output

    def test_clean_nonexistent_cache(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            main, ["cache", "-C", str(tmp_path / "nonexistent"), "clean", "--force"]
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
            main, ["cache", "-C", str(cache_dir), "clean", "--force"]
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
                "-C",
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
            ["cache", "-C", str(cache_dir), "clean"],
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
            ["cache", "-C", str(cache_dir), "clean"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not source_dir.exists()
