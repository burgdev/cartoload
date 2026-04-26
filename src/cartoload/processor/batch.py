"""Streaming batch tile processor: read, reproject, and encode tiles in configurable batches."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from cartoload.downloader.base import BaseDownloader
from cartoload.downloader.wmts import WMTSDownloader
from cartoload.processor.reproject import reproject_tile_cached
from cartoload.processor.tile_reader import TileCacheReader

logger = logging.getLogger(__name__)

# Type for processed tile: (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
ProcessedTile = tuple[bytes, tuple[float, float, float, float]]

# Progress callback: (stage, current, total)
ProgressCallback = Callable[[str, int, int], None]


class BatchTileProcessor:
    """Process tiles from cache in batches with optional reprojection.

    Reads tiles from the download cache, optionally reprojects them, encodes
    to JPEG, and yields batches for the IMG writer. This avoids loading all
    tiles into memory at once.
    """

    def __init__(
        self,
        source_crs: str | None = None,
        target_crs: str = "EPSG:4326",
        quality: int = 85,
        batch_size: int = 500,
        max_workers: int | None = None,
    ) -> None:
        self._source_crs = source_crs
        self._target_crs = target_crs
        self._quality = quality
        self._batch_size = batch_size
        if max_workers is None:
            cpu_count = os.cpu_count() or 4
            self._max_workers = min(32, cpu_count * 4)
        else:
            self._max_workers = max_workers
        self._reader = TileCacheReader(target_quality=quality)

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
        """Process a batch of tiles in parallel."""
        needs_reproj = BaseDownloader.needs_reprojection(
            self._source_crs, self._target_crs
        )

        results: list[ProcessedTile] = [None] * len(tile_coords)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    self._process_single_tile,
                    downloader,
                    x,
                    y,
                    zoom,
                    needs_reproj,
                ): idx
                for idx, (x, y) in enumerate(tile_coords)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    if result is not None:
                        results[idx] = result
                except Exception as e:
                    x, y = tile_coords[idx]
                    logger.warning(
                        "Failed to process tile (%d, %d, z=%d): %s", x, y, zoom, e
                    )

        return [r for r in results if r is not None]

    def _process_single_tile(
        self,
        downloader: BaseDownloader,
        x: int,
        y: int,
        zoom: int,
        needs_reproj: bool,
    ) -> ProcessedTile | None:
        """Process a single tile: find in cache, optionally reproject, read."""
        # Get source tile path from cache
        source_path = self._get_source_tile_path(downloader, x, y, zoom)
        if source_path is None or not source_path.exists():
            return None

        # Optionally reproject
        if needs_reproj:
            try:
                tile_path = reproject_tile_cached(
                    source_path,
                    x,
                    y,
                    zoom,
                    self._source_crs or "EPSG:3857",
                    self._target_crs,
                    "tif",
                    downloader,
                )
            except Exception as e:
                logger.warning(
                    "Reprojection failed for (%d, %d, z=%d): %s", x, y, zoom, e
                )
                return None
        else:
            tile_path = source_path

        # Read and encode
        try:
            return self._reader.read_tile(tile_path, x=x, y=y, zoom=zoom)
        except Exception as e:
            logger.warning("Failed to read tile (%d, %d, z=%d): %s", x, y, zoom, e)
            return None

    def _get_source_tile_path(
        self, downloader: BaseDownloader, x: int, y: int, zoom: int
    ) -> Path | None:
        """Get the source tile cache path."""
        if isinstance(downloader, WMTSDownloader):
            return downloader._cache_path(x, y, zoom)
        return None
