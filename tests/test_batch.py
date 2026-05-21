"""Tests for batch tile processing: BatchTileProcessor and export_from_tiles."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock


from cartoload.config import LayerConfig
from cartoload.downloader.wmts.download import WMTSDownloader
from cartoload.exporters.garmin_img import GarminImgExporter
from cartoload.processor.batch import BatchTileProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 256, height: int = 256) -> bytes:
    """Create a minimal JPEG image."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _write_tile_with_world_file(
    tile_path: Path,
    pixel_size_x: float = 0.01,
    pixel_size_y: float = -0.01,
    top_left_x: float = 7.0,
    top_left_y: float = 47.0,
) -> Path:
    """Write a JPEG tile + world file to the given path."""
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    jpeg_bytes = _make_jpeg()
    tile_path.write_bytes(jpeg_bytes)

    # Write world file
    wf_path = tile_path.with_suffix(".jgw")
    wf_path.write_text(
        f"{pixel_size_x:.10f}\n"
        f"0.0000000000\n"
        f"0.0000000000\n"
        f"{pixel_size_y:.10f}\n"
        f"{top_left_x:.10f}\n"
        f"{top_left_y:.10f}\n"
    )
    return tile_path


def _make_downloader(
    tmp_path: Path,
    source_id: str = "test_source",
    crs: str | None = None,
) -> WMTSDownloader:
    return WMTSDownloader(
        source_id=source_id,
        url_template="https://example.com/{z}/{x}/{y}.jpeg",
        cache_dir=tmp_path / "cache",
        delay_ms=0,
        crs=crs,
    )


def _write_cached_tiles(
    downloader: WMTSDownloader,
    tile_coords: list[tuple[int, int]],
    zoom: int,
) -> None:
    """Write JPEG tiles + world files to the downloader cache."""
    for x, y in tile_coords:
        tile_path = downloader._cache_path(x, y, zoom)
        _write_tile_with_world_file(tile_path)


# ===================================================================
# BatchTileProcessor tests
# ===================================================================


class TestBatchTileProcessorInit:
    def test_default_params(self) -> None:
        proc = BatchTileProcessor()
        assert proc._source_crs is None
        assert proc._target_crs == "EPSG:4326"
        assert proc._batch_size == 500

    def test_custom_params(self) -> None:
        proc = BatchTileProcessor(
            source_crs="EPSG:3857",
            batch_size=100,
            max_workers=4,
        )
        assert proc._source_crs == "EPSG:3857"
        assert proc._batch_size == 100
        assert proc._max_workers == 4

    def test_default_max_workers(self) -> None:
        import os

        proc = BatchTileProcessor()
        expected = min(8, os.cpu_count() or 4)
        assert proc._max_workers == expected


class TestProcessZoomLevel:
    def test_empty_coords(self) -> None:
        proc = BatchTileProcessor(max_workers=2)
        dl = MagicMock()
        result = proc.process_zoom_level(dl, [], 10)
        assert result == []

    def test_single_tile(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2)
        dl = _make_downloader(tmp_path)
        _write_cached_tiles(dl, [(541, 362)], 10)

        results = proc.process_zoom_level(dl, [(541, 362)], 10)
        assert len(results) == 1
        jpeg_bytes, bounds = results[0]
        assert jpeg_bytes[:2] == b"\xff\xd8"
        assert len(bounds) == 4

    def test_multiple_tiles(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2)
        dl = _make_downloader(tmp_path)
        coords = [(541, 362), (542, 362), (541, 363)]
        _write_cached_tiles(dl, coords, 10)

        results = proc.process_zoom_level(dl, coords, 10)
        assert len(results) == 3
        for jpeg_bytes, bounds in results:
            assert jpeg_bytes[:2] == b"\xff\xd8"
            assert len(bounds) == 4

    def test_missing_tiles_skipped(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2)
        dl = _make_downloader(tmp_path)
        # Only write one of two tiles
        _write_cached_tiles(dl, [(541, 362)], 10)

        results = proc.process_zoom_level(dl, [(541, 362), (999, 999)], 10)
        assert len(results) == 1

    def test_progress_callback(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2, batch_size=2)
        dl = _make_downloader(tmp_path)
        coords = [(541, 362), (542, 362), (541, 363)]
        _write_cached_tiles(dl, coords, 10)

        progress_calls: list[tuple[str, int, int]] = []
        proc.process_zoom_level(
            dl,
            coords,
            10,
            progress_callback=lambda *args: progress_calls.append(args),
        )

        # Should have initial (0, total) and final calls
        assert len(progress_calls) >= 2
        assert progress_calls[0] == ("processing", 0, 3)

    def test_batched_processing(self, tmp_path: Path) -> None:
        """With batch_size=2, 5 tiles should produce 3 batches."""
        proc = BatchTileProcessor(max_workers=2, batch_size=2)
        dl = _make_downloader(tmp_path)
        coords = [(i, 0) for i in range(5)]
        _write_cached_tiles(dl, coords, 10)

        results = proc.process_zoom_level(dl, coords, 10)
        assert len(results) == 5


class TestProcessZoomLevelBatched:
    def test_empty_coords_yields_nothing(self) -> None:
        proc = BatchTileProcessor(max_workers=2)
        dl = MagicMock()
        batches = list(proc.process_zoom_level_batched(dl, [], 10))
        assert batches == []

    def test_yields_batches(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2, batch_size=2)
        dl = _make_downloader(tmp_path)
        coords = [(i, 0) for i in range(5)]
        _write_cached_tiles(dl, coords, 10)

        batches = list(proc.process_zoom_level_batched(dl, coords, 10))
        assert len(batches) == 3  # 2 + 2 + 1
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    def test_batch_results_are_valid(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2, batch_size=2)
        dl = _make_downloader(tmp_path)
        coords = [(541, 362), (542, 362)]
        _write_cached_tiles(dl, coords, 10)

        batches = list(proc.process_zoom_level_batched(dl, coords, 10))
        assert len(batches) == 1
        for jpeg_bytes, bounds in batches[0]:
            assert jpeg_bytes[:2] == b"\xff\xd8"
            assert len(bounds) == 4

    def test_progress_callback(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=2, batch_size=2)
        dl = _make_downloader(tmp_path)
        coords = [(i, 0) for i in range(3)]
        _write_cached_tiles(dl, coords, 10)

        progress_calls: list[tuple[str, int, int]] = []
        list(
            proc.process_zoom_level_batched(
                dl,
                coords,
                10,
                progress_callback=lambda *args: progress_calls.append(args),
            )
        )

        assert len(progress_calls) >= 2
        assert progress_calls[0] == ("processing", 0, 3)


class TestProcessBatchParallel:
    def test_parallel_reads(self, tmp_path: Path) -> None:
        """Verify that tiles are processed in parallel (order may vary)."""
        proc = BatchTileProcessor(max_workers=4)
        dl = _make_downloader(tmp_path)
        coords = [(i, 0) for i in range(10)]
        _write_cached_tiles(dl, coords, 10)

        results = proc._process_batch(dl, coords, 10)
        assert len(results) == 10

    def test_partial_failure(self, tmp_path: Path) -> None:
        """Tiles that fail should be silently skipped."""
        proc = BatchTileProcessor(max_workers=2)
        dl = _make_downloader(tmp_path)
        # Only write 2 of 4 tiles
        _write_cached_tiles(dl, [(0, 0), (1, 0)], 10)

        results = proc._process_batch(dl, [(0, 0), (1, 0), (2, 0), (3, 0)], 10)
        assert len(results) == 2


class TestProcessSingleTile:
    def test_existing_tile(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=1)
        dl = _make_downloader(tmp_path)
        _write_cached_tiles(dl, [(541, 362)], 10)

        results = proc.process_zoom_level(dl, [(541, 362)], 10)
        assert len(results) == 1
        jpeg_bytes, bounds = results[0]
        assert jpeg_bytes[:2] == b"\xff\xd8"

    def test_missing_tile(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor(max_workers=1)
        dl = _make_downloader(tmp_path)

        results = proc.process_zoom_level(dl, [(999, 999)], 10)
        assert len(results) == 0


class TestGetSourceTilePath:
    def test_wmts_downloader(self, tmp_path: Path) -> None:
        proc = BatchTileProcessor()
        dl = _make_downloader(tmp_path)

        path = proc._get_source_tile_path(dl, 541, 362, 10)
        assert path is not None
        assert "10" in str(path)
        assert "541" in str(path)
        assert "362" in str(path)

    def test_non_wmts_returns_none(self) -> None:
        proc = BatchTileProcessor()
        dl = MagicMock(spec=[])  # Not a WMTSDownloader

        path = proc._get_source_tile_path(dl, 541, 362, 10)
        assert path is None


# ===================================================================
# export_from_tiles tests
# ===================================================================


class TestExportFromTiles:
    def _make_layer_config(self) -> LayerConfig:
        return LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="test_source",
            zoom_levels=[10],
            bounds={
                "west": 5.0,
                "east": 10.0,
                "south": 45.0,
                "north": 48.0,
            },
        )

    def test_export_with_pre_encoded_tiles(self, tmp_path: Path) -> None:
        """export_from_tiles should create a valid IMG from pre-encoded JPEG bytes."""
        jpeg_bytes = _make_jpeg()
        compressed_tiles: dict[int, list] = {
            10: [
                (jpeg_bytes, (46.0, 7.0, 47.0, 8.0)),
                (jpeg_bytes, (45.0, 8.0, 46.0, 9.0)),
            ]
        }

        output_path = tmp_path / "output.img"
        exporter = GarminImgExporter()
        layer_config = self._make_layer_config()

        result = exporter.export_from_tiles(compressed_tiles, layer_config, output_path)

        assert len(result) == 1
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_export_preserves_progress_callback(self, tmp_path: Path) -> None:
        """Progress callback should be called during export_from_tiles."""
        jpeg_bytes = _make_jpeg()
        compressed_tiles = {
            10: [(jpeg_bytes, (46.0, 7.0, 47.0, 8.0))],
        }

        progress_calls: list[tuple[str, int, int]] = []

        output_path = tmp_path / "output.img"
        exporter = GarminImgExporter()
        layer_config = self._make_layer_config()

        exporter.export_from_tiles(
            compressed_tiles,
            layer_config,
            output_path,
            progress_callback=lambda *args: progress_calls.append(args),
        )

        assert len(progress_calls) >= 1

    def test_export_no_tiles(self, tmp_path: Path) -> None:
        """Export with empty tiles should still produce a file."""
        compressed_tiles: dict[int, list] = {10: []}

        output_path = tmp_path / "output.img"
        exporter = GarminImgExporter()
        layer_config = self._make_layer_config()

        result = exporter.export_from_tiles(compressed_tiles, layer_config, output_path)

        assert len(result) == 1
        assert output_path.exists()


# ===================================================================
# Integration: BatchTileProcessor → export_from_tiles
# ===================================================================


class TestBatchToIntegration:
    def test_batch_processor_to_img(self, tmp_path: Path) -> None:
        """Full flow: cached tiles → BatchTileProcessor → export_from_tiles → IMG."""
        # Setup: create downloader with cached tiles
        dl = _make_downloader(tmp_path, crs="EPSG:4326")
        coords = [(541, 362), (542, 362)]
        _write_cached_tiles(dl, coords, 10)

        # Process tiles
        proc = BatchTileProcessor(
            source_crs="EPSG:4326",  # No reprojection needed
            max_workers=2,
        )
        tiles = proc.process_zoom_level(dl, coords, 10)
        assert len(tiles) == 2

        # Export to IMG
        compressed_tiles = {10: tiles}
        layer_config = LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="test_source",
            zoom_levels=[10],
            bounds={
                "west": 5.0,
                "east": 10.0,
                "south": 45.0,
                "north": 48.0,
            },
        )

        output_path = tmp_path / "output.img"
        exporter = GarminImgExporter()
        result = exporter.export_from_tiles(compressed_tiles, layer_config, output_path)

        assert len(result) == 1
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_batch_processor_to_img_multiple_zooms(self, tmp_path: Path) -> None:
        """Full flow with multiple zoom levels."""
        dl = _make_downloader(tmp_path, crs="EPSG:4326")

        # Create tiles at zoom 10 and 11
        coords_10 = [(541, 362)]
        coords_11 = [(1082, 724), (1083, 724)]
        _write_cached_tiles(dl, coords_10, 10)
        _write_cached_tiles(dl, coords_11, 11)

        proc = BatchTileProcessor(source_crs="EPSG:4326", max_workers=2)

        tiles_10 = proc.process_zoom_level(dl, coords_10, 10)
        tiles_11 = proc.process_zoom_level(dl, coords_11, 11)

        compressed_tiles = {10: tiles_10, 11: tiles_11}
        layer_config = LayerConfig(
            id="test_layer",
            name="Test",
            source="test_source",
            zoom_levels=[10, 11],
            bounds={"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0},
        )

        output_path = tmp_path / "output.img"
        exporter = GarminImgExporter()
        result = exporter.export_from_tiles(compressed_tiles, layer_config, output_path)

        assert len(result) == 1
        assert output_path.exists()
