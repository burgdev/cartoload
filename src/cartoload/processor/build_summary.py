"""Build summary and progress reporting.

Pre-computes tile grid, scans cache status, and prints a summary table
before builds start. Integrates with Rich progress bars for multi-stage
progress reporting.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..config import LayerConfig
from ..downloader.base import BaseDownloader
from ..downloader.wmts import WMTSDownloader
from ..pipeline import _compute_tile_coords

logger = logging.getLogger(__name__)

# Fallback bytes per JPEG tile when sampling is not possible
_FALLBACK_TILE_SIZE_BYTES = 30_000
# Maximum number of cached tiles to sample for size estimation
_MAX_SAMPLES = 5


@dataclass
class ZoomSummary:
    """Tile counts for a single zoom level."""

    zoom: int
    total_tiles: int = 0
    cached_tiles: int = 0

    @property
    def to_process(self) -> int:
        return self.total_tiles - self.cached_tiles


@dataclass
class BuildSummary:
    """Aggregated tile counts across all zoom levels for a layer."""

    layer_id: str
    zooms: list[ZoomSummary] = field(default_factory=list)
    _avg_tile_bytes: int = _FALLBACK_TILE_SIZE_BYTES

    @property
    def total_tiles(self) -> int:
        return sum(z.total_tiles for z in self.zooms)

    @property
    def cached_tiles(self) -> int:
        return sum(z.cached_tiles for z in self.zooms)

    @property
    def to_process(self) -> int:
        return sum(z.to_process for z in self.zooms)

    @property
    def estimated_output_size(self) -> int:
        """Estimate output IMG size in bytes based on sampled tile sizes."""
        return self.total_tiles * self._avg_tile_bytes

    @property
    def all_cached(self) -> bool:
        """True if all tiles are already in cache."""
        return self.total_tiles > 0 and self.cached_tiles == self.total_tiles


def _sample_tile_size(
    cached_paths: list[Path],
    quality: int,
) -> int:
    """Sample cached tiles re-encoded at the target quality to estimate output size.

    Opens up to _MAX_SAMPLES cached tiles, re-encodes them as JPEG at the given
    quality, and returns the average encoded size in bytes.

    Args:
        cached_paths: Paths to cached tile files
        quality: Target JPEG quality (1-100)

    Returns:
        Average encoded tile size in bytes
    """
    from PIL import Image

    samples: list[int] = []
    for path in cached_paths:
        if len(samples) >= _MAX_SAMPLES:
            break
        try:
            img = Image.open(path)
            if img.mode == "RGBA":
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            samples.append(buf.tell())
        except Exception:
            logger.debug("Failed to sample tile %s", path)
            continue

    if samples:
        return sum(samples) // len(samples)
    return _FALLBACK_TILE_SIZE_BYTES


def _download_sample_tile(
    downloader: WMTSDownloader,
    coords: list[tuple[int, int]],
    zoom: int,
    quality: int,
) -> int:
    """Download a single tile and re-encode at target quality to estimate size.

    Picks the middle tile from the grid, downloads it, re-encodes as JPEG
    at the given quality, and returns the encoded size.

    Args:
        downloader: WMTS downloader to use for downloading
        coords: Tile coordinate list for this zoom
        zoom: Zoom level
        quality: Target JPEG quality (1-100)

    Returns:
        Encoded tile size in bytes, or fallback if download fails
    """
    from PIL import Image

    # Pick the middle tile
    mid = len(coords) // 2
    x, y = coords[mid]

    try:
        url = WMTSDownloader._build_tile_url(
            downloader._url_template,
            x,
            y,
            zoom,
            downloader._source_id,
            downloader._layer_name,
        )
        data = downloader._download_with_retry(url, x, y, zoom)
        if data is None:
            return _FALLBACK_TILE_SIZE_BYTES

        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)

        # Also write to cache so the download wasn't wasted
        cache_path = downloader._cache_path(x, y, zoom)
        downloader._write_to_cache(cache_path, data)
        downloader._write_world_file(cache_path, x, y, zoom)

        return buf.tell()
    except Exception:
        logger.debug("Failed to download sample tile (%d, %d, z=%d)", x, y, zoom)
        return _FALLBACK_TILE_SIZE_BYTES


def compute_build_summary(
    layer: LayerConfig,
    downloader: BaseDownloader,
    *,
    quality: int = 85,
) -> BuildSummary:
    """Pre-compute tile grid and scan cache status for each zoom level.

    Samples cached tiles to estimate output size at the target JPEG quality.

    Args:
        layer: Layer configuration with bounds and zoom levels
        downloader: Downloader instance for cache path resolution
        quality: Target JPEG quality for size estimation

    Returns:
        BuildSummary with per-zoom tile counts and quality-aware size estimate
    """
    summary = BuildSummary(layer_id=layer.id)
    all_cached_paths: list[Path] = []

    for zoom in layer.zoom_levels:
        coords = _compute_tile_coords(layer, zoom)
        total = len(coords)
        cached = 0

        if isinstance(downloader, WMTSDownloader):
            for x, y in coords:
                cache_path = downloader._cache_path(x, y, zoom)
                if cache_path.exists():
                    cached += 1
                    if len(all_cached_paths) < _MAX_SAMPLES:
                        all_cached_paths.append(cache_path)

        summary.zooms.append(
            ZoomSummary(zoom=zoom, total_tiles=total, cached_tiles=cached)
        )

    # Estimate output size by sampling
    if all_cached_paths:
        summary._avg_tile_bytes = _sample_tile_size(all_cached_paths, quality)
    elif isinstance(downloader, WMTSDownloader):
        # No cached tiles — download one sample tile from the first zoom with tiles
        for zs in summary.zooms:
            if zs.total_tiles > 0:
                coords = _compute_tile_coords(layer, zs.zoom)
                summary._avg_tile_bytes = _download_sample_tile(
                    downloader,
                    coords,
                    zs.zoom,
                    quality,
                )
                break

    return summary


def format_build_summary(summary: BuildSummary, *, fast_build: bool = False) -> str:
    """Format a build summary as a plain-text table.

    Args:
        summary: Build summary to format
        fast_build: If True, all tiles are cached

    Returns:
        Formatted summary string
    """
    lines = []
    lines.append(f"Build plan for layer '{summary.layer_id}':")
    lines.append("")
    lines.append(f"  {'Zoom':>6}  {'Tiles':>8}  {'Cached':>8}  {'To process':>11}")
    lines.append(f"  {'─' * 6}  {'─' * 8}  {'─' * 8}  {'─' * 11}")

    for z in summary.zooms:
        lines.append(
            f"  {z.zoom:>6}  {z.total_tiles:>8}  {z.cached_tiles:>8}  {z.to_process:>11}"
        )

    lines.append(f"  {'─' * 6}  {'─' * 8}  {'─' * 8}  {'─' * 11}")
    lines.append(
        f"  {'Total':>6}  {summary.total_tiles:>8}  {summary.cached_tiles:>8}  {summary.to_process:>11}"
    )
    lines.append("")

    est_size = summary.estimated_output_size
    if est_size > 0:
        lines.append(f"  Estimated output size: {_human_size(est_size)}")

    if fast_build:
        lines.append("  Fast build expected (all tiles cached)")

    return "\n".join(lines)


def print_build_summary(
    summary: BuildSummary,
    *,
    console: Console | None = None,
    fast_build: bool = False,
) -> None:
    """Print a build summary as a Rich table.

    Args:
        summary: Build summary to display
        console: Rich console to print to (creates one if None)
        fast_build: If True, all tiles are cached
    """
    if console is None:
        console = Console()

    table = Table(title=f"Build plan for layer '{summary.layer_id}'")
    table.add_column("Zoom", justify="right")
    table.add_column("Tiles", justify="right")
    table.add_column("Cached", justify="right", style="green")
    table.add_column("To process", justify="right", style="yellow")

    for z in summary.zooms:
        table.add_row(
            str(z.zoom),
            str(z.total_tiles),
            str(z.cached_tiles),
            str(z.to_process),
        )

    # Total row
    table.add_row(
        "Total",
        str(summary.total_tiles),
        str(summary.cached_tiles),
        str(summary.to_process),
        style="bold",
    )

    console.print(table)

    est_size = summary.estimated_output_size
    if est_size > 0:
        console.print(f"  Estimated output size: {_human_size(est_size)}")

    if fast_build:
        console.print("  [green]Fast build expected (all tiles cached)[/green]")


def _human_size(size: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size //= 1024
    return f"{size:.1f} TB"
