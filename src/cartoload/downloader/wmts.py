from __future__ import annotations

import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

import requests

from cartoload.template import expand
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from cartoload.downloader.base import BaseDownloader
from cartoload.downloader.cache_key import migrate_cache_key, url_to_cache_key

logger = logging.getLogger(__name__)


class _PerUrlRateLimiter:
    """Thread-safe per-URL rate limiter."""

    def __init__(self, delay_ms: int):
        self._delay = delay_ms / 1000.0
        self._lock = threading.Lock()
        self._last_request: float = 0.0

    def wait(self) -> None:
        """Block until the rate limit allows the next request."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._delay:
                time.sleep(self._delay - elapsed)
            self._last_request = time.monotonic()


class _UrlSelector:
    """Round-robin URL selector with failover tracking."""

    def __init__(self, urls: Sequence[str], max_consecutive_failures: int = 5):
        self._urls = list(urls)
        self._max_failures = max_consecutive_failures
        self._consecutive_failures: dict[str, int] = {u: 0 for u in self._urls}
        self._disabled: set[str] = set()
        self._lock = threading.Lock()
        self._index = 0

    @property
    def active_urls(self) -> list[str]:
        return [u for u in self._urls if u not in self._disabled]

    def next(self) -> str | None:
        """Get next URL in round-robin order, skipping disabled ones."""
        with self._lock:
            active = self.active_urls
            if not active:
                return None
            self._index = self._index % len(active)
            url = active[self._index]
            self._index += 1
            return url

    def report_success(self, url: str) -> None:
        with self._lock:
            self._consecutive_failures[url] = 0

    def report_failure(self, url: str) -> None:
        with self._lock:
            self._consecutive_failures[url] += 1
            if self._consecutive_failures[url] >= self._max_failures:
                self._disabled.add(url)
                logger.warning(
                    "URL disabled after %d consecutive failures: %s",
                    self._max_failures,
                    url,
                )


class WMTSDownloader(BaseDownloader):
    """Downloads tiles from WMTS/XYZ tile services."""

    def __init__(
        self,
        source_id: str,
        url_template: str,
        cache_dir: str | Path = "cache",
        max_workers: int = 4,
        delay_ms: int = 150,
        tile_format: str = "jpeg",
        layer_name: str = "",
        crs: str | None = None,
        urls: Sequence[str] | None = None,
        display_name: str = "",
    ) -> None:
        super().__init__(source_id, cache_dir, max_workers, delay_ms, crs=crs)
        self._url_template = url_template
        self._tile_format = tile_format
        self._layer_name = layer_name
        self._display_name = display_name or layer_name or source_id

        # Multi-URL support: if additional URLs provided, use round-robin
        all_urls = [url_template] if url_template else []
        if urls:
            for u in urls:
                if u not in all_urls:
                    all_urls.append(u)
        self._all_urls = all_urls
        self._url_selector = _UrlSelector(all_urls) if len(all_urls) > 1 else None

        # Per-URL rate limiters
        self._rate_limiters: dict[str, _PerUrlRateLimiter] = {
            u: _PerUrlRateLimiter(delay_ms) for u in all_urls
        }

        # Scale thread pool with URL count
        if urls and len(urls) > 1 and max_workers == 4:
            self._max_workers = max(4, len(all_urls) * 2)

        # Cache key: human-readable key derived from URL path to differentiate
        # layers that share the same source but have different template args
        # (e.g. different WMTS layers, extensions, or other source_args).
        self._cache_key = url_to_cache_key(url_template) if url_template else ""

        # Auto-migrate old hash-based cache directories to new format
        if self._cache_key:
            migrate_cache_key(self._cache_dir / self._source_id, self._cache_key)

    @property
    def source_cache_dir(self) -> Path:
        """Cache directory for this source (includes cache key if set)."""
        base = self._cache_dir / self._source_id
        if self._cache_key:
            return base / self._cache_key
        return base

    # ------------------------------------------------------------------
    # Tile grid computation
    # ------------------------------------------------------------------

    @staticmethod
    def _lon_to_tile_x(lon: float, zoom: int) -> int:
        """Convert longitude to tile X index at given zoom."""
        n = 2**zoom
        x = int((lon + 180.0) / 360.0 * n)
        return max(0, min(x, n - 1))

    @staticmethod
    def _lat_to_tile_y(lat: float, zoom: int) -> int:
        """Convert latitude to tile Y index at given zoom (Web Mercator / OGC)."""
        lat_rad = math.radians(lat)
        n = 2**zoom
        y = int(
            (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
            / 2.0
            * n
        )
        return max(0, min(y, n - 1))

    @staticmethod
    def _bbox_to_tile_indices(
        bbox: tuple[float, float, float, float], zoom: int
    ) -> list[tuple[int, int]]:
        """Convert a WGS84 bounding box to tile (x, y) indices at the given zoom.

        Args:
            bbox: (min_lon, min_lat, max_lon, max_lat) in WGS84 degrees.
            zoom: Zoom level.

        Returns:
            Sorted list of (x, y) tile coordinate tuples covering the bbox.
        """
        min_lon, min_lat, max_lon, max_lat = bbox

        # Handle antimeridian wrapping: min_lon > max_lon means we wrap
        if min_lon > max_lon:
            # Split into two bboxes: [min_lon, 180] and [-180, max_lon]
            west_indices = WMTSDownloader._bbox_to_tile_indices(
                (min_lon, min_lat, 180.0, max_lat), zoom
            )
            east_indices = WMTSDownloader._bbox_to_tile_indices(
                (-180.0, min_lat, max_lon, max_lat), zoom
            )
            combined = set(west_indices) | set(east_indices)
            return sorted(combined)

        n = 2**zoom

        x_min = int((min_lon + 180.0) / 360.0 * n)
        x_max = int((max_lon + 180.0) / 360.0 * n)
        # Clamp to valid range
        x_min = max(0, min(x_min, n - 1))
        x_max = max(0, min(x_max, n - 1))

        lat_rad_min = math.radians(min_lat)
        lat_rad_max = math.radians(max_lat)

        y_max = int(
            (
                1.0
                - math.log(math.tan(lat_rad_min) + 1.0 / math.cos(lat_rad_min))
                / math.pi
            )
            / 2.0
            * n
        )
        y_min = int(
            (
                1.0
                - math.log(math.tan(lat_rad_max) + 1.0 / math.cos(lat_rad_max))
                / math.pi
            )
            / 2.0
            * n
        )
        # Clamp to valid range
        y_min = max(0, min(y_min, n - 1))
        y_max = max(0, min(y_max, n - 1))

        tiles = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tiles.append((x, y))

        return tiles

    # ------------------------------------------------------------------
    # Tile georeferencing
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_tile_bounds(
        x: int, y: int, zoom: int
    ) -> tuple[float, float, float, float]:
        """Compute the bounding box of a Web Mercator tile in EPSG:3857 meters.

        Returns:
            (left, top, right, bottom) in meters.
        """
        origin = -20037508.342789244  # -2 * pi * 6378137 / 2
        tile_size = 40075016.68557849 / 2**zoom  # 2 * pi * 6378137 / 2^z

        left = origin + x * tile_size
        top = -origin - y * tile_size  # Y starts from +20M (85° N), decreases south
        right = left + tile_size
        bottom = top - tile_size

        return (left, top, right, bottom)

    @staticmethod
    def _world_file_suffix(tile_format: str) -> str:
        """Return the world file suffix for a given tile format."""
        return ".jgw" if tile_format in ("jpeg", "jpg") else ".pgw"

    def _write_world_file(
        self, cache_path: Path, x: int, y: int, zoom: int, tile_pixels: int = 256
    ) -> None:
        """Write a GDAL-compatible world file alongside the cached tile."""
        left, top, _right, _bottom = self._compute_tile_bounds(x, y, zoom)
        tile_size_m = 40075016.68557849 / 2**zoom

        pixel_size_x = tile_size_m / tile_pixels
        pixel_size_y = -tile_size_m / tile_pixels  # negative: Y axis inverted

        world_path = cache_path.with_suffix(self._world_file_suffix(self._tile_format))
        lines = [
            f"{pixel_size_x:.10f}",
            "0.0000000000",
            "0.0000000000",
            f"{pixel_size_y:.10f}",
            f"{left:.10f}",
            f"{top:.10f}",
        ]
        world_path.write_text("\n".join(lines) + "\n")

    # ------------------------------------------------------------------
    # URL template interpolation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tile_url(
        template: str,
        x: int,
        y: int,
        zoom: int,
        source_id: str = "",
        layer_name: str = "",
    ) -> str:
        """Substitute per-tile variables in a URL template.

        Config-level variables (${layer}, ${extension}, etc.) are already
        resolved by the pipeline. This handles the per-tile coordinates.
        Supports both ${x}/${y}/${z}/${zoom}/${source_id}/${layer} and
        legacy {x}/{y}/{z}/{zoom}/{source_id}/{layer} syntax.
        """
        variables = {
            "x": str(x),
            "y": str(y),
            "z": str(zoom),
            "zoom": str(zoom),
            "source_id": source_id,
            "layer": layer_name or source_id,
        }
        # Expand ${VAR} syntax via template engine
        result = expand(template, variables)
        # Also handle legacy {VAR} syntax for backward compat
        result = (
            result.replace("{zoom}", str(zoom))
            .replace("{z}", str(zoom))
            .replace("{x}", str(x))
            .replace("{y}", str(y))
            .replace("{source_id}", source_id)
            .replace("{layer}", layer_name or source_id)
        )
        return result

    # ------------------------------------------------------------------
    # Caching helpers
    # ------------------------------------------------------------------

    def _cache_path(self, x: int, y: int, zoom: int) -> Path:
        """Return the cache file path for a tile.

        Uses a URL-based cache key to differentiate layers sharing the
        same source:
            cache_dir / source_id / <cache_key> / zoom / x / y.ext
        If no cache key (empty URL template), falls back to:
            cache_dir / source_id / zoom / x / y.ext
        """
        base = self._cache_dir / self._source_id
        if self._cache_key:
            base = base / self._cache_key
        return base / str(zoom) / str(x) / f"{y}.{self._tile_format}"

    def _world_file_path(self, tile_path: Path) -> Path:
        """Return the expected world file path for a tile."""
        return tile_path.with_suffix(self._world_file_suffix(self._tile_format))

    def _is_cached(self, path: Path) -> bool:
        """Check if a tile and its world file are already cached on disk."""
        if not (path.exists() and path.stat().st_size > 0):
            return False
        return self._world_file_path(path).exists()

    def _write_to_cache(self, path: Path, data: bytes) -> None:
        """Write tile data to cache atomically (tmp + rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_bytes(data)
        os.rename(tmp_path, path)

    # ------------------------------------------------------------------
    # Retry with exponential backoff
    # ------------------------------------------------------------------

    def _download_with_retry(self, url: str, x: int, y: int, zoom: int) -> bytes | None:
        """Download a tile with retry on transient HTTP errors.

        Returns tile bytes on success, None on failure.
        """
        max_retries = 3
        backoff_times = [1, 2, 4]

        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    return response.content
                elif response.status_code == 404:
                    logger.warning(
                        "Tile (%d, %d, z=%d) returned 404, not retrying",
                        x,
                        y,
                        zoom,
                    )
                    return None
                elif response.status_code in (429, *range(500, 600)):
                    if attempt < max_retries - 1:
                        sleep_time = backoff_times[attempt]
                        logger.warning(
                            "Tile (%d, %d, z=%d) HTTP %d, retry %d/%d in %ds",
                            x,
                            y,
                            zoom,
                            response.status_code,
                            attempt + 1,
                            max_retries,
                            sleep_time,
                        )
                        time.sleep(sleep_time)
                    else:
                        logger.warning(
                            "Tile (%d, %d, z=%d) HTTP %d, exhausted retries",
                            x,
                            y,
                            zoom,
                            response.status_code,
                        )
                else:
                    logger.warning(
                        "Tile (%d, %d, z=%d) HTTP %d, not retrying",
                        x,
                        y,
                        zoom,
                        response.status_code,
                    )
                    return None
            except requests.RequestException as exc:
                if attempt < max_retries - 1:
                    sleep_time = backoff_times[attempt]
                    logger.warning(
                        "Tile (%d, %d, z=%d) request error: %s, retry %d/%d in %ds",
                        x,
                        y,
                        zoom,
                        exc,
                        attempt + 1,
                        max_retries,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                else:
                    logger.warning(
                        "Tile (%d, %d, z=%d) request error: %s, exhausted retries",
                        x,
                        y,
                        zoom,
                        exc,
                    )

        return None

    # ------------------------------------------------------------------
    # Single tile download (implements BaseDownloader)
    # ------------------------------------------------------------------

    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        """Download a single tile and return its cached path."""
        cache_path = self._cache_path(x, y, zoom)

        if self._is_cached(cache_path):
            return cache_path

        # Tile exists but world file is missing — regenerate without downloading
        if cache_path.exists() and cache_path.stat().st_size > 0:
            self._write_world_file(cache_path, x, y, zoom)
            return cache_path

        url = self._build_tile_url(
            self._url_template, x, y, zoom, self._source_id, self._layer_name
        )
        delay_seconds = self._delay_ms / 1000.0
        time.sleep(delay_seconds)

        data = self._download_with_retry(url, x, y, zoom)
        if data is not None:
            self._write_to_cache(cache_path, data)
            self._write_world_file(cache_path, x, y, zoom)
        else:
            logger.warning("Failed to download tile (%d, %d, z=%d)", x, y, zoom)

        return cache_path

    # ------------------------------------------------------------------
    # Grid download (implements BaseDownloader)
    # ------------------------------------------------------------------

    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        """Download all tiles covering the bbox at the given zoom level."""
        tiles = self._bbox_to_tile_indices(bbox, zoom)
        total = len(tiles)

        if total == 0:
            return []

        # Separate cached vs uncached
        cached_paths: list[Path] = []
        uncached: list[tuple[int, int]] = []
        for x, y in tiles:
            path = self._cache_path(x, y, zoom)
            if self._is_cached(path):
                cached_paths.append(path)
            else:
                uncached.append((x, y))

        cached_count = len(cached_paths)

        results: list[Path] = list(cached_paths)

        if not uncached:
            logger.info("All %d tiles already cached", total)
            return results

        # Write CRS metadata on first download
        self.write_cache_metadata()

        logger.info(
            "Downloading %d tiles (%d cached, %d to fetch) at zoom %d",
            total,
            cached_count,
            len(uncached),
            zoom,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        ) as progress:
            task_id = progress.add_task(
                f"Downloading {self._display_name} z{zoom}",
                total=total,
            )
            # Fast-forward for cached tiles
            if cached_count > 0:
                progress.update(task_id, advance=cached_count)

            failed = 0
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                future_to_tile = {
                    executor.submit(self._download_worker, x, y, zoom): (x, y)
                    for x, y in uncached
                }

                for future in as_completed(future_to_tile):
                    x, y = future_to_tile[future]
                    try:
                        path = future.result()
                        if path and path.exists():
                            results.append(path)
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
                        logger.warning("Tile (%d, %d, z=%d) failed", x, y, zoom)
                    progress.update(task_id, advance=1)

        if failed > 0:
            logger.warning(
                "Zoom %d: %d/%d tiles failed to download",
                zoom,
                failed,
                len(uncached),
            )

        return results

    def _download_worker(self, x: int, y: int, zoom: int) -> Path | None:
        """Worker function for downloading a single tile (used by ThreadPoolExecutor)."""
        cache_path = self._cache_path(x, y, zoom)

        # Double-check cache (another thread may have downloaded it)
        if self._is_cached(cache_path):
            return cache_path

        # Tile exists but world file is missing — regenerate without downloading
        if cache_path.exists() and cache_path.stat().st_size > 0:
            self._write_world_file(cache_path, x, y, zoom)
            return cache_path

        # Select URL (round-robin or single)
        if self._url_selector:
            url_template = self._url_selector.next()
            if url_template is None:
                logger.error(
                    "All URLs disabled, cannot download tile (%d, %d, z=%d)", x, y, zoom
                )
                return None
        else:
            url_template = self._url_template

        url = self._build_tile_url(
            url_template, x, y, zoom, self._source_id, self._layer_name
        )

        # Per-URL rate limiting
        limiter = self._rate_limiters.get(url_template)
        if limiter:
            limiter.wait()

        data = self._download_with_retry(url, x, y, zoom)
        if data is not None:
            self._write_to_cache(cache_path, data)
            self._write_world_file(cache_path, x, y, zoom)
            if self._url_selector:
                self._url_selector.report_success(url_template)
            return cache_path

        logger.warning("Failed to download tile (%d, %d, z=%d)", x, y, zoom)
        if self._url_selector:
            self._url_selector.report_failure(url_template)
        return None
