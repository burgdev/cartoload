"""Streaming batch tile processor: read, reproject, and encode tiles in configurable batches."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from cartoload.downloader.base import BaseDownloader
from cartoload.downloader.wmts.download import WMTSDownloader
from cartoload.processor.rasterio_warp import warp_tile_to_jpeg

logger = logging.getLogger(__name__)

# Type for processed tile: (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
ProcessedTile = tuple[bytes, tuple[float, float, float, float]]

# Progress callback: (stage, current, total)
ProgressCallback = Callable[[str, int, int], None]


def _process_tile_worker(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    source_crs: str,
    target_crs: str,
) -> ProcessedTile | None:
    """Top-level worker function for ProcessPoolExecutor.

    Must be a top-level function (not a method) to be picklable.
    """
    return warp_tile_to_jpeg(source_path, x, y, zoom, source_crs, target_crs)


class BatchTileProcessor:
    """Process tiles from cache in batches with optional reprojection.

    Reads tiles from the download cache, reprojects via rasterio in-process,
    and yields batches for the IMG writer. Uses ProcessPoolExecutor for
    true parallelism (rasterio holds the GIL, so threads give no speedup).
    """

    def __init__(
        self,
        source_crs: str | None = None,
        target_crs: str = "EPSG:4326",
        quality: int = 95,
        batch_size: int = 500,
        max_workers: int | None = None,
    ) -> None:
        self._source_crs = source_crs
        self._target_crs = target_crs
        self._batch_size = batch_size
        if max_workers is None:
            cpu_count = os.cpu_count() or 4
            self._max_workers = min(8, cpu_count)
        else:
            self._max_workers = max_workers

    def process_zoom_level(
        self,
        downloader: BaseDownloader,
        tile_coords: list[tuple[int, int]],
        zoom: int,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> list[ProcessedTile]:
        """Process all tiles for a zoom level, returning encoded tiles.

        Args:
            downloader: Downloader instance (for cache paths)
            tile_coords: List of (x, y) tile coordinates
            zoom: Zoom level
            progress_callback: Called with (stage, current, total) for progress

        Returns:
            List of (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) tuples
        """
        total = len(tile_coords)
        if total == 0:
            return []

        logger.info(
            "Processing %d tiles at zoom %d (batch_size=%d, workers=%d)",
            total,
            zoom,
            self._batch_size,
            self._max_workers,
        )

        results: list[ProcessedTile] = []
        if progress_callback:
            progress_callback("processing", 0, total)

        processed = 0
        for batch_start in range(0, total, self._batch_size):
            batch_end = min(batch_start + self._batch_size, total)
            batch = tile_coords[batch_start:batch_end]

            batch_results = self._process_batch(downloader, batch, zoom)
            results.extend(batch_results)
            processed += len(batch)

            if progress_callback:
                progress_callback("processing", processed, total)

        logger.info("Processed %d/%d tiles at zoom %d", len(results), total, zoom)
        return results

    def process_zoom_level_batched(
        self,
        downloader: BaseDownloader,
        tile_coords: list[tuple[int, int]],
        zoom: int,
        *,
        progress_callback: ProgressCallback | None = None,
    ):
        """Generator that yields batches of processed tiles for a zoom level.

        This is useful for streaming directly to the IMG writer without
        accumulating all tiles in memory.

        Yields:
            Lists of (jpeg_bytes, bounds) tuples, one batch at a time
        """
        total = len(tile_coords)
        if total == 0:
            return

        processed = 0
        if progress_callback:
            progress_callback("processing", 0, total)

        for batch_start in range(0, total, self._batch_size):
            batch_end = min(batch_start + self._batch_size, total)
            batch = tile_coords[batch_start:batch_end]

            batch_results = self._process_batch(downloader, batch, zoom)
            processed += len(batch)

            if progress_callback:
                progress_callback("processing", processed, total)

            yield batch_results

    def _process_batch(
        self,
        downloader: BaseDownloader,
        tile_coords: list[tuple[int, int]],
        zoom: int,
    ) -> list[ProcessedTile]:
        """Process a batch of tiles in parallel using ProcessPoolExecutor."""
        # Resolve source paths for all tiles in the batch
        path_coords: list[tuple[Path, int, int]] = []
        for x, y in tile_coords:
            source_path = self._get_source_tile_path(downloader, x, y, zoom)
            if source_path is not None and source_path.exists():
                path_coords.append((source_path, x, y))

        if not path_coords:
            return []

        results: list[ProcessedTile] = [None] * len(path_coords)  # type: ignore[list-item]

        # Use ProcessPoolExecutor for true parallelism (rasterio holds the GIL)
        source_crs = self._source_crs or "EPSG:3857"
        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _process_tile_worker,
                    source_path,
                    x,
                    y,
                    zoom,
                    source_crs,
                    self._target_crs,
                ): idx
                for idx, (source_path, x, y) in enumerate(path_coords)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    if result is not None:
                        results[idx] = result
                except Exception as e:
                    source_path, x, y = path_coords[idx]
                    logger.warning(
                        "Failed to process tile (%d, %d, z=%d): %s", x, y, zoom, e
                    )

        return [r for r in results if r is not None]

    def _get_source_tile_path(
        self, downloader: BaseDownloader, x: int, y: int, zoom: int
    ) -> Path | None:
        """Get the source tile cache path."""
        if isinstance(downloader, WMTSDownloader):
            return downloader._cache_path(x, y, zoom)
        return None
