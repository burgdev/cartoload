"""Pipeline orchestration: wires config → downloader → processor → exporter."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Callable

from .config import LayerConfig, SourceConfig
from .downloader.base import BaseDownloader
from .downloader.geotiff import GeoTIFFDownloader
from .downloader.wmts import WMTSDownloader
from .exporters.garmin_img import GarminImgExporter
from .processor.checkpoint import (
    CheckpointData,
    delete_checkpoint,
    mark_zoom_complete,
    read_checkpoint,
    write_checkpoint,
)
from .processor.tile_metadata import compute_tile_metadata

# Legacy import — kept for backward compatibility and debug use
from .processor.raster import RasterProcessor  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class PipelineError(Exception):
    """Base exception for all pipeline errors."""


class DownloadError(PipelineError):
    """Error during the download stage."""

    def __init__(self, source_id: str, message: str, *, cause: Exception | None = None):
        self.source_id = source_id
        super().__init__(f"Download failed for source '{source_id}': {message}")
        if cause is not None:
            self.__cause__ = cause


class ProcessingError(PipelineError):
    """Error during the processing stage."""

    def __init__(self, layer_id: str, message: str, *, cause: Exception | None = None):
        self.layer_id = layer_id
        super().__init__(f"Processing failed for layer '{layer_id}': {message}")
        if cause is not None:
            self.__cause__ = cause


class ExportError(PipelineError):
    """Error during the export stage."""

    def __init__(self, layer_id: str, message: str, *, cause: Exception | None = None):
        self.layer_id = layer_id
        super().__init__(f"Export failed for layer '{layer_id}': {message}")
        if cause is not None:
            self.__cause__ = cause


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def get_downloader(
    source: SourceConfig, cache_dir: Path, *, layer_name: str = ""
) -> GeoTIFFDownloader | WMTSDownloader:
    """Return the correct downloader for the given source type.

    Args:
        source: Source configuration
        cache_dir: Directory for caching downloaded tiles
        layer_name: WMTS layer name (for {layer} URL template substitution)

    Returns:
        A downloader instance

    Raises:
        PipelineError: If the source type is not supported
    """
    if source.type == "geotiff":
        return GeoTIFFDownloader(cache_dir)
    if source.type == "wmts":
        if not source.url_template and not source.urls:
            raise PipelineError(
                f"WMTS source '{source.id}' missing required 'url_template' or 'urls'"
            )
        # Use first url_template or first URL from list
        url_template = source.url_template or source.urls[0]
        return WMTSDownloader(
            source_id=source.id,
            url_template=url_template,
            cache_dir=cache_dir,
            max_workers=source.max_threads,
            delay_ms=source.rate_limit_ms,
            layer_name=layer_name,
            crs=source.crs,
            urls=source.urls if source.urls else None,
        )
    raise PipelineError(
        f"Unknown source type '{source.type}' for source '{source.id}'. "
        f"Supported types: geotiff, wmts"
    )


def get_exporter(layer: LayerConfig, output_dir: Path) -> GarminImgExporter:
    """Return the correct exporter for the given layer config.

    Args:
        layer: Layer configuration
        output_dir: Directory for output files

    Returns:
        An exporter instance

    Raises:
        PipelineError: If the exporter type is not supported
    """
    if layer.exporter == "garmin-img":
        return GarminImgExporter()
    if layer.exporter == "garmin_img":
        return GarminImgExporter()
    raise PipelineError(
        f"Unknown exporter '{layer.exporter}' for layer '{layer.id}'. "
        f"Supported exporters: garmin-img"
    )


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------


def resolve_source(
    layer: LayerConfig,
    sources: dict[str, SourceConfig],
) -> SourceConfig:
    """Find the source config matching a layer's source reference.

    Args:
        layer: Layer configuration with a ``source`` field
        sources: Dictionary of loaded source configs

    Returns:
        The matching SourceConfig

    Raises:
        PipelineError: If the source is not found
    """
    if layer.source in sources:
        return sources[layer.source]
    available = ", ".join(sorted(sources.keys())) if sources else "(none)"
    raise PipelineError(
        f"Layer '{layer.id}' references unknown source '{layer.source}'. "
        f"Available sources: {available}"
    )


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

# Type alias for the progress callback
ProgressCallback = Callable[[str, str], None]

# Type alias for export progress callback (stage, current, total)
ExportProgressCallback = Callable[[str, int, int], None]


async def build_layer(
    layer: LayerConfig,
    sources: dict[str, SourceConfig],
    cache_dir: Path,
    output_dir: Path,
    *,
    no_download: bool = False,
    force: bool = False,
    bounds_override: dict[str, float] | None = None,
    zoom_override: list[int] | None = None,
    quality: int | None = None,
    progress_callback: ProgressCallback | None = None,
    export_progress_callback: ExportProgressCallback | None = None,
    checkpoint: bool = True,
    warmup_only: bool = False,
) -> list[Path]:
    """Orchestrate download → batch process → export for a single layer.

    Uses the fast pipeline: downloads tiles to cache, computes tile
    metadata (no JPEG data in memory), then streams JPEG data to
    Garmin IMG via the two-pass streaming writer.

    Args:
        layer: Layer configuration
        sources: Dictionary of source configurations
        cache_dir: Directory for caching downloaded tiles
        output_dir: Directory for output files
        no_download: If True, skip the download stage
        force: If True, overwrite existing output files
        bounds_override: Override the layer bounds
        zoom_override: Override the layer zoom levels
        quality: JPEG quality for tile encoding, or None for passthrough (no re-encoding)
        progress_callback: Called with (stage_id, description) at each stage
        export_progress_callback: Called with (stage, current, total) for export progress
        checkpoint: If True, write checkpoint after each zoom level for resume support
        warmup_only: If True, download and process tiles but skip IMG export

    Returns:
        List of paths to output files (may be multiple if >4GB split)

    Raises:
        PipelineError: If source resolution fails
        DownloadError: If the download stage fails
        ProcessingError: If the processing stage fails
        ExportError: If the export stage fails
    """
    # Resolve source
    source = resolve_source(layer, sources)

    # Apply overrides to a copy of the layer config
    effective_layer = _apply_overrides(layer, bounds_override, zoom_override)

    # --- Checkpoint: detect and resume ---
    cp_data: CheckpointData | None = None
    if checkpoint:
        cp_data = read_checkpoint(cache_dir, effective_layer.id)
        if cp_data is not None:
            # Validate that the checkpoint matches current config
            completed = set(cp_data.completed_zoom_levels)
            requested = set(effective_layer.zoom_levels)
            if completed <= requested:
                skipped = completed & requested
                if skipped:
                    logger.info(
                        "Resuming build for layer '%s': zoom levels %s already completed",
                        effective_layer.id,
                        sorted(skipped),
                    )
            else:
                # Checkpoint has zooms not in current request — stale, discard
                logger.warning(
                    "Stale checkpoint for layer '%s' (extra zooms), starting fresh",
                    effective_layer.id,
                )
                cp_data = None

    # Determine remaining zoom levels
    if cp_data is not None:
        completed_zooms = set(cp_data.completed_zoom_levels)
        remaining_zooms = [
            z for z in effective_layer.zoom_levels if z not in completed_zooms
        ]
    else:
        remaining_zooms = list(effective_layer.zoom_levels)
        # Create initial checkpoint
        if checkpoint:
            cp_data = CheckpointData(
                layer_id=effective_layer.id,
                completed_zoom_levels=[],
                remaining_zoom_levels=list(effective_layer.zoom_levels),
            )
            write_checkpoint(cache_dir, cp_data)

    # Determine source CRS
    source_crs: str | None
    if source.crs:
        source_crs = source.crs
    elif source.type == "wmts":
        source_crs = "EPSG:3857"
    else:
        source_crs = None

    # --- Download stage ---
    downloader: BaseDownloader | None = None
    if not no_download:
        if progress_callback:
            progress_callback("download", "Downloading tiles...")
        try:
            downloader = get_downloader(
                source, cache_dir, layer_name=effective_layer.wmts_layer or ""
            )
            if isinstance(downloader, GeoTIFFDownloader):
                downloader.run(source, effective_layer)
            elif isinstance(downloader, WMTSDownloader):
                bounds = effective_layer.bounds
                if not bounds:
                    raise DownloadError(
                        source.id,
                        "WMTS download requires bounds on the layer",
                    )
                bbox = (
                    bounds["west"],
                    bounds["south"],
                    bounds["east"],
                    bounds["north"],
                )
                for zoom in remaining_zooms:
                    paths = downloader.download_grid(bbox, zoom)
                    downloaded_count = len(paths)
                    expected = len(downloader._bbox_to_tile_indices(bbox, zoom))
                    if downloaded_count < expected and progress_callback:
                        progress_callback(
                            "download",
                            f"Warning: zoom {zoom} — only {downloaded_count}/{expected} tiles available",
                        )
        except PipelineError:
            raise
        except Exception as e:
            raise DownloadError(source.id, str(e), cause=e) from e
    else:
        logger.info("Skipping download stage (--no-download)")

    # --- Process stage: compute tile metadata from cache ---
    if progress_callback:
        progress_callback("process", "Computing tile metadata from cache...")

    # Get the downloader for cache path resolution (create if not set)
    if downloader is None:
        try:
            downloader = get_downloader(
                source, cache_dir, layer_name=effective_layer.wmts_layer or ""
            )
        except PipelineError:
            raise
        except Exception as e:
            raise ProcessingError(layer.id, str(e), cause=e) from e

    # Compute tile metadata for each zoom level (no JPEG data loaded)
    tile_metadata: dict[int, list] = {}
    try:
        for zoom in remaining_zooms:
            tile_coords = _compute_tile_coords(effective_layer, zoom)

            if tile_coords:
                metadata = compute_tile_metadata(
                    tile_coords,
                    zoom,
                    source_crs,
                    downloader,
                )
                tile_metadata[zoom] = metadata
            else:
                tile_metadata[zoom] = []
                logger.debug(f"No tile coordinates for zoom level {zoom}")

            # Write checkpoint after each zoom level
            if checkpoint and cp_data is not None:
                mark_zoom_complete(
                    cache_dir, cp_data, zoom, len(tile_metadata.get(zoom, []))
                )
    except PipelineError:
        raise
    except Exception as e:
        raise ProcessingError(layer.id, str(e), cause=e) from e

    total_tiles = sum(len(t) for t in tile_metadata.values())
    if total_tiles == 0:
        raise ProcessingError(layer.id, "No tiles available for processing")

    logger.info(
        "Computed metadata for %d tiles across %d zoom levels",
        total_tiles,
        len(tile_metadata),
    )

    # Warmup mode: stop after metadata computation, skip export
    if warmup_only:
        logger.info(
            "Warmup complete for layer '%s': %d tiles cached", layer.id, total_tiles
        )
        # Delete checkpoint since we're not building an IMG
        if checkpoint:
            delete_checkpoint(cache_dir, effective_layer.id)
        return []

    # --- Export stage: streaming write to IMG ---
    if progress_callback:
        from .exporters.garmin_img_writer import _get_worker_count

        workers = _get_worker_count()
        if workers > 1:
            progress_callback(
                "export", f"Exporting to Garmin IMG ({workers}x parallel)..."
            )
        else:
            progress_callback("export", "Exporting to Garmin IMG...")

    output_paths: list[Path]
    try:
        exporter = get_exporter(effective_layer, output_dir)
        output_file = output_dir / effective_layer.output

        # Check for existing output file
        if output_file.exists():
            if force:
                output_file.unlink()
            else:
                raise ExportError(
                    layer.id,
                    f"Output file already exists: {output_file}. "
                    f"Use --force to overwrite.",
                )

        output_paths = exporter.export_from_metadata(
            tile_metadata,
            effective_layer,
            output_file,
            source_crs=source_crs or "EPSG:3857",
            quality=quality,
            progress_callback=export_progress_callback,
        )
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(layer.id, str(e), cause=e) from e

    logger.info(
        f"Build complete for layer '{layer.id}': {len(output_paths)} file(s) produced"
    )

    # Delete checkpoint on successful completion
    if checkpoint:
        delete_checkpoint(cache_dir, effective_layer.id)

    return output_paths


def _compute_tile_coords(layer: LayerConfig, zoom: int) -> list[tuple[int, int]]:
    """Compute tile grid coordinates for a zoom level within the layer bounds.

    Uses Web Mercator tile math to determine which (x, y) tiles cover
    the layer's geographic bounds at the given zoom level.

    Args:
        layer: Layer configuration with bounds
        zoom: Zoom level

    Returns:
        List of (x, y) tile coordinates
    """
    bounds = layer.bounds
    if not bounds:
        return []

    n = 2**zoom
    west = bounds["west"]
    east = bounds["east"]
    north = bounds["north"]
    south = bounds["south"]

    def lon_to_x(lon: float) -> int:
        return max(0, min(int((lon + 180.0) / 360.0 * n), n - 1))

    def lat_to_y(lat: float) -> int:
        lat_rad = math.radians(lat)
        return max(
            0,
            min(
                int(
                    (
                        1.0
                        - math.log(
                            max(math.tan(lat_rad), 1e-10)
                            + 1.0 / max(math.cos(lat_rad), 1e-10)
                        )
                        / math.pi
                    )
                    / 2.0
                    * n
                ),
                n - 1,
            ),
        )

    x_min = lon_to_x(west)
    x_max = lon_to_x(east)
    y_min = lat_to_y(north)
    y_max = lat_to_y(south)

    coords = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            coords.append((x, y))
    return coords


def _apply_overrides(
    layer: LayerConfig,
    bounds_override: dict[str, float] | None,
    zoom_override: list[int] | None,
) -> LayerConfig:
    """Apply CLI overrides to a layer config, returning a new copy."""
    import dataclasses

    kwargs = {}
    if bounds_override is not None:
        kwargs["bounds"] = bounds_override
    if zoom_override is not None:
        kwargs["zoom_levels"] = zoom_override
    if not kwargs:
        return layer
    return dataclasses.replace(layer, **kwargs)


def _collect_cached_tiles(
    cache_dir: Path,
    source: SourceConfig,
    layer: LayerConfig,
) -> list[Path]:
    """Collect already-cached tiles for no-download mode."""
    tiles: list[Path] = []
    if cache_dir.exists():
        source_cache = cache_dir / source.id
        if source_cache.exists():
            tiles = sorted(
                p
                for p in source_cache.rglob("*")
                if p.is_file()
                and p.suffix.lstrip(".") in ("tif", "tiff", "jpeg", "jpg", "png")
            )
    if not tiles:
        logger.warning(
            f"No cached tiles found in {cache_dir / source.id}. Processing may fail."
        )
    else:
        logger.info(f"Found {len(tiles)} cached tile(s)")
    return tiles
