"""Pipeline orchestration: wires config → downloader → processor → exporter."""

from __future__ import annotations

import logging
import io
import math
from pathlib import Path
from typing import Callable

from PIL import Image

from .config import CompositeSubLayer, LayerConfig, SourceConfig
from .downloader.base import BaseDownloader
from .downloader.stac import STACDownloader
from .downloader.wmts import WMTSDownloader
from .downloader.wmts import _url_cache_key
from .exporters.garmin_img import GarminImgExporter
from .processor.geotiff_collector import collect_geotiff_files
from .processor.geotiff_index import GeoTIFFIndex
from .processor.geotiff_tile_reader import (
    read_tile_from_geotiff,
    read_tile_from_warped_geotiff,
)
from .processor.checkpoint import (
    CheckpointData,
    delete_checkpoint,
    mark_zoom_complete,
    read_checkpoint,
    write_checkpoint,
)
from .processor.compositor import (
    composite_tiles,
    encode_composite_to_jpeg,
    find_fallback_tile,
    load_tile_as_rgba,
    resolve_opacity,
)
from .processor.rasterio_warp import warp_tile_to_rgba
from .processor.tile_metadata import compute_tile_metadata
from .template import check_unresolved, expand, resolve_templates

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


def _resolve_wmts_urls(
    source: SourceConfig,
    source_args: dict[str, str] | None = None,
) -> str:
    """Resolve config-level variables in WMTS URL templates.

    Merges source.defaults with source_args, expands all URL templates,
    and returns the effective (first) URL template with config vars resolved.

    Returns:
        The resolved URL template string (per-tile vars like ${x} remain).
    """
    variables: dict[str, str] = dict(source.defaults)
    if source_args:
        variables.update(source_args)

    if source.url_template:
        return expand(source.url_template, variables)

    if source.urls:
        resolved = resolve_templates(source.urls, variables)
        return resolved[0] if resolved else ""

    return ""


def get_downloader(
    source: SourceConfig,
    cache_dir: Path,
    *,
    source_args: dict[str, str] | None = None,
    display_name: str = "",
) -> WMTSDownloader:
    """Return the correct downloader for the given source type.

    Args:
        source: Source configuration
        cache_dir: Directory for caching downloaded tiles
        source_args: Layer-level variable overrides for template resolution.
            Common keys: 'layer' (WMTS layer name), 'extension' (tile format).
        display_name: Name shown in download progress bars. Defaults to
            source_args['layer'] or source.id.

    Returns:
        A downloader instance

    Raises:
        PipelineError: If the source type is not supported
    """
    if source.type == "wmts":
        if not source.url_template and not source.urls:
            raise PipelineError(
                f"WMTS source '{source.id}' missing required 'url_template' or 'urls'"
            )

        # Merge variables: source defaults → layer source_args
        variables: dict[str, str] = dict(source.defaults)
        if source_args:
            variables.update(source_args)

        # Resolve all URL templates
        resolved_urls: list[str] = []
        if source.urls:
            resolved_urls = resolve_templates(source.urls, variables)
        if source.url_template:
            resolved = expand(source.url_template, variables)
            if resolved not in resolved_urls:
                resolved_urls.insert(0, resolved)

        # Per-tile variables resolved at download time — not an error
        _PER_TILE_VARS = {"x", "y", "z", "zoom"}

        for u in resolved_urls:
            unres = check_unresolved(u)
            # Filter out known per-tile variables
            unknown = [v for v in unres if v not in _PER_TILE_VARS]
            if unknown:
                raise PipelineError(
                    f"Source '{source.id}' URL has unresolved variables "
                    f"with no default: {unknown}. "
                    f"Define them in source 'defaults' or layer 'source_args'."
                )

        # Derive tile format and layer name from variables
        tile_format = variables.get("extension", "jpeg")
        layer_name = variables.get("layer", "")

        effective_template = resolved_urls[0] if resolved_urls else ""
        return WMTSDownloader(
            source_id=source.id,
            url_template=effective_template,
            cache_dir=cache_dir,
            max_workers=source.max_threads,
            delay_ms=source.rate_limit_ms,
            tile_format=tile_format,
            layer_name=layer_name,
            crs=source.crs,
            urls=resolved_urls[1:] if len(resolved_urls) > 1 else None,
            display_name=display_name or layer_name or source.id,
        )
    raise PipelineError(
        f"Unknown source type '{source.type}' for source '{source.id}'. "
        f"Supported types: wmts"
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
    preview: bool = False,
    preview_tiles: int = 9,
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
        preview: If True, generate preview images after export
        preview_tiles: Max tiles per zoom level in preview mosaics

    Returns:
        List of paths to output files (may be multiple if >4GB split)

    Raises:
        PipelineError: If source resolution fails
        DownloadError: If the download stage fails
        ProcessingError: If the processing stage fails
        ExportError: If the export stage fails
    """
    # Composite layers use a separate pipeline
    effective_layer = _apply_overrides(layer, bounds_override, zoom_override)
    if effective_layer.is_composite():
        return await build_composite_layer(
            effective_layer,
            sources,
            cache_dir,
            output_dir,
            no_download=no_download,
            force=force,
            progress_callback=progress_callback,
            export_progress_callback=export_progress_callback,
            preview=preview,
            preview_tiles=preview_tiles,
        )

    # Resolve source
    source = resolve_source(layer, sources)

    # STAC and GeoTIFF sources use a separate pipeline
    if source.type in ("stac", "geotiff"):
        return await build_geotiff_layer(
            effective_layer,
            source,
            cache_dir,
            output_dir,
            no_download=no_download,
            force=force,
            quality=quality,
            progress_callback=progress_callback,
            export_progress_callback=export_progress_callback,
            checkpoint=checkpoint,
            warmup_only=warmup_only,
            preview=preview,
            preview_tiles=preview_tiles,
        )

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
                source,
                cache_dir,
                source_args=effective_layer.source_args,
            )
            if isinstance(downloader, WMTSDownloader):
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
                source,
                cache_dir,
                source_args=effective_layer.source_args,
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


# ---------------------------------------------------------------------------
# GeoTIFF / STAC layer pipeline
# ---------------------------------------------------------------------------


async def build_geotiff_layer(
    layer: LayerConfig,
    source: SourceConfig,
    cache_dir: Path,
    output_dir: Path,
    *,
    no_download: bool = False,
    force: bool = False,
    quality: int | None = None,
    progress_callback: ProgressCallback | None = None,
    export_progress_callback: ExportProgressCallback | None = None,
    checkpoint: bool = True,
    warmup_only: bool = False,
    preview: bool = False,
    preview_tiles: int = 9,
) -> list[Path]:
    """Build a layer from GeoTIFF files (STAC download or local path source).

    For ``stac`` sources: resolves the URL template, runs the STAC downloader
    to fetch GeoTIFF assets, then builds a spatial index.

    For ``geotiff`` sources: resolves local/remote paths via
    ``collect_geotiff_files``, then builds a spatial index.

    In both cases, the spatial index is used to look up which GeoTIFF covers
    each (x, y, zoom) tile, and a tile_processor_override reads pixel windows
    on-the-fly and feeds JPEG bytes into the existing streaming export pipeline.

    Args:
        layer: Layer configuration
        source: Source configuration (type must be 'stac' or 'geotiff')
        cache_dir: Directory for caching downloaded files
        output_dir: Directory for output files
        no_download: If True, skip the download stage
        force: If True, overwrite existing output files
        quality: JPEG quality for tile encoding
        progress_callback: Called with (stage_id, description) at each stage
        export_progress_callback: Called with (stage, current, total) for export progress
        checkpoint: If True, write checkpoint after each zoom level
        warmup_only: If True, download and index but skip IMG export

    Returns:
        List of paths to output files
    """
    from .exporters.garmin_img_model import TileMetadata as ExportTileMetadata
    from .exporters.garmin_img_writer import _get_worker_count
    from .processor.rasterio_warp import compute_bounds_4326

    # --- Collect GeoTIFF files ---
    geotiff_paths: list[Path]
    collection_id: str = ""

    if source.type == "stac":
        # Resolve URL template with source defaults + layer source_args
        variables: dict[str, str] = dict(source.defaults)
        if layer.source_args:
            variables.update(layer.source_args)

        collection_id = variables.get("layer", "")
        resolved_urls = resolve_templates(source.urls, variables) if source.urls else []
        resolved_url = resolved_urls[0] if resolved_urls else ""

        if not resolved_url:
            raise PipelineError(f"STAC source '{source.id}' has no resolved URL")

        if not collection_id:
            raise PipelineError(
                f"STAC source '{source.id}' requires a 'layer' variable "
                f"(collection ID) — set in source.defaults or layer source_args"
            )

        if not no_download:
            if progress_callback:
                progress_callback(
                    "download", f"Downloading GeoTIFFs from STAC '{collection_id}'..."
                )
            try:
                downloader = STACDownloader(cache_dir)
                # Layer asset_filter overrides source asset_filter
                effective_filter = layer.asset_filter or source.asset_filter
                geotiff_paths = downloader.run(
                    source,
                    layer,
                    resolved_url,
                    collection_id,
                    asset_filter=effective_filter,
                )
            except Exception as e:
                raise DownloadError(source.id, str(e), cause=e) from e
        else:
            logger.info("Skipping STAC download (--no-download)")
            # Reconstruct cache paths from previous download
            stac_dl = STACDownloader(cache_dir)
            # Layer asset_filter overrides source asset_filter
            effective_filter = layer.asset_filter or source.asset_filter
            geotiff_paths = []
            cache_subdir = stac_dl._get_cache_path(
                source.id, resolved_url, "", effective_filter
            ).parent
            if cache_subdir.exists():
                geotiff_paths = sorted(
                    p
                    for p in cache_subdir.rglob("*")
                    if p.is_file() and p.suffix.lstrip(".") in ("tif", "tiff")
                )
            if not geotiff_paths:
                raise DownloadError(
                    source.id,
                    f"No cached GeoTIFFs found for STAC collection '{collection_id}'",
                )
            logger.info("Using %d cached GeoTIFF(s)", len(geotiff_paths))

    elif source.type == "geotiff":
        if not source.urls:
            raise PipelineError(f"GeoTIFF source '{source.id}' requires 'urls'")

        # Determine config_dir for relative path resolution.
        config_dir = Path(source.config_dir) if source.config_dir else None

        if not no_download:
            if progress_callback:
                progress_callback("download", "Collecting GeoTIFF files...")
            try:
                geotiff_paths = collect_geotiff_files(
                    source.urls, cache_dir, config_dir=config_dir
                )
            except Exception as e:
                raise DownloadError(source.id, str(e), cause=e) from e
        else:
            logger.info("Skipping GeoTIFF collection (--no-download)")
            try:
                geotiff_paths = collect_geotiff_files(
                    source.urls, cache_dir, config_dir=config_dir
                )
            except Exception as e:
                raise DownloadError(source.id, str(e), cause=e) from e
    else:
        raise PipelineError(
            f"build_geotiff_layer called with unsupported source type '{source.type}'"
        )

    if not geotiff_paths:
        raise ProcessingError(layer.id, "No GeoTIFF files available for processing")

    # --- Build spatial index ---
    if progress_callback:
        progress_callback("process", "Building GeoTIFF spatial index...")

    try:
        index = GeoTIFFIndex.from_paths(geotiff_paths)
    except Exception as e:
        raise ProcessingError(layer.id, str(e), cause=e) from e

    # Determine effective bounds: layer bounds override, or union of all GeoTIFFs
    if layer.bounds:
        effective_bounds = layer.bounds
    else:
        west, south, east, north = index.total_bounds
        effective_bounds = {"west": west, "south": south, "east": east, "north": north}
        logger.info(
            "Using GeoTIFF union bounds for layer '%s': %s",
            layer.id,
            effective_bounds,
        )

    # --- Pre-warp GeoTIFFs to EPSG:4326 ---
    # Converts source GeoTIFFs (any CRS, possibly paletted) to 3-band RGB
    # in EPSG:4326 once, so per-tile reads don't need CRS transforms or
    # palette expansion. Cached alongside originals.
    prewarped_map: dict[Path, Path] = {}
    mosaic_path: Path | None = None
    try:
        from .processor.geotiff_prewarp import (
            merge_prewarped_geotiffs,
            prewarp_all_geotiffs,
        )

        prewarped_map = prewarp_all_geotiffs(
            geotiff_paths,
            target_crs="EPSG:4326",
            force=False,
            progress_callback=progress_callback,
        )

        # Merge all pre-warped files into a single mosaic so tiles that
        # span multiple source GeoTIFFs can read all data at once.
        prewarped_paths = list(set(prewarped_map.values()))
        if len(prewarped_paths) > 1:
            # Determine cache directory from the first pre-warped file
            mosaic_dir = prewarped_paths[0].parent
            mosaic_path = merge_prewarped_geotiffs(
                prewarped_paths,
                cache_dir=mosaic_dir,
                force=False,
                progress_callback=progress_callback,
            )
        elif len(prewarped_paths) == 1:
            mosaic_path = prewarped_paths[0]

    except Exception as e:
        logger.warning("Pre-warp failed, falling back to per-tile warp: %s", e)

    # --- Compute tile metadata ---
    if progress_callback:
        progress_callback("process", "Computing tile metadata...")

    tile_metadata: dict[int, list[ExportTileMetadata]] = {}
    try:
        for zoom in layer.zoom_levels:
            tile_coords = _compute_tile_coords_from_bounds(effective_bounds, zoom)
            if not tile_coords:
                tile_metadata[zoom] = []
                continue

            metadata = []
            for x, y in tile_coords:
                lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(x, y, zoom)

                if mosaic_path is not None:
                    # With a merged mosaic, all tiles within bounds can
                    # potentially contain data. Use the mosaic as source.
                    geotiff_path = mosaic_path
                else:
                    # Pre-resolve which GeoTIFF covers this tile.
                    # This avoids per-tile spatial index lookups during export.
                    geotiff_path = index.find(lon_min, lat_min, lon_max, lat_max)
                    if geotiff_path is None:
                        continue  # skip tiles with no GeoTIFF coverage

                # Estimate jpeg_size — use a rough estimate for GeoTIFF-sourced tiles
                jpeg_size = 50_000  # ~50KB per tile estimate

                metadata.append(
                    ExportTileMetadata(
                        x=x,
                        y=y,
                        zoom=zoom,
                        lat_min=lat_min,
                        lon_min=lon_min,
                        lat_max=lat_max,
                        lon_max=lon_max,
                        jpeg_size=jpeg_size,
                        source_path=geotiff_path,
                    )
                )

            tile_metadata[zoom] = metadata
    except Exception as e:
        raise ProcessingError(layer.id, str(e), cause=e) from e

    total_tiles = sum(len(t) for t in tile_metadata.values())
    if total_tiles == 0:
        raise ProcessingError(layer.id, "No tiles available for processing")

    logger.info(
        "Computed metadata for %d GeoTIFF-sourced tiles across %d zoom levels",
        total_tiles,
        len(tile_metadata),
    )

    if warmup_only:
        logger.info(
            "Warmup complete for layer '%s': %d tiles indexed", layer.id, total_tiles
        )
        return []

    # --- Export stage: streaming write with GeoTIFF tile processor ---
    if progress_callback:
        workers = _get_worker_count()
        if workers > 1:
            progress_callback(
                "export",
                f"Exporting GeoTIFF layer to Garmin IMG ({workers}x parallel)...",
            )
        else:
            progress_callback("export", "Exporting GeoTIFF layer to Garmin IMG...")

    output_paths: list[Path]
    try:
        exporter = get_exporter(layer, output_dir)
        output_file = output_dir / layer.output

        if output_file.exists():
            if force:
                output_file.unlink()
            else:
                raise ExportError(
                    layer.id,
                    f"Output file already exists: {output_file}. "
                    f"Use --force to overwrite.",
                )

        # Build a GeoTIFF-aware tile processor
        geotiff_processor = _make_geotiff_processor(
            quality, prewarped_map=prewarped_map if mosaic_path is None else None
        )

        output_paths = exporter.export_from_metadata(
            tile_metadata,
            layer,
            output_file,
            source_crs="EPSG:4326",  # GeoTIFF tile reader already warps to 4326
            quality=quality,
            progress_callback=export_progress_callback,
            tile_processor_override=geotiff_processor,
        )
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(layer.id, str(e), cause=e) from e

    logger.info(
        f"GeoTIFF build complete for layer '{layer.id}': "
        f"{len(output_paths)} file(s) produced"
    )

    # Generate previews if requested
    if preview and tile_metadata:
        from .processor.preview import generate_previews_from_processor

        try:
            if progress_callback:
                progress_callback("preview", "Generating preview images...")
            preview_paths = generate_previews_from_processor(
                layer,
                tile_metadata,
                geotiff_processor,
                "EPSG:4326",
                output_dir,
                max_tiles_per_zoom=preview_tiles,
                quality=quality or 85,
            )
            if progress_callback:
                for pp in preview_paths:
                    progress_callback("preview", f"  Preview: {pp}")
        except Exception as e:
            logger.warning("Preview generation failed: %s", e)

    return output_paths


def _compute_tile_coords_from_bounds(
    bounds: dict[str, float], zoom: int
) -> list[tuple[int, int]]:
    """Compute tile grid coordinates for a zoom level within given bounds."""
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


def _make_geotiff_processor(
    quality: int | None = None,
    prewarped_map: dict[Path, Path] | None = None,
):
    """Create a tile processor callable that reads from GeoTIFF files.

    Returns a callable with the signature expected by the streaming writer:
    (source_path, x, y, zoom, source_crs, quality) -> (jpeg_bytes, bounds) | None

    Two modes:
    - Mosaic mode (prewarped_map=None): source_path is a pre-warped EPSG:4326
      mosaic file — always use the fast read path.
    - Per-file mode (prewarped_map provided): source_path is an original file.
      Look up pre-warped version and use fast path, fall back to per-tile warp.
    """
    from .exporters.garmin_img_writer import ProcessedTile

    def geotiff_processor(
        source_path: Path | None,
        x: int,
        y: int,
        zoom: int,
        crs: str,
        jpeg_quality: int | None,
    ) -> ProcessedTile | None:
        """Read a tile window from the pre-resolved GeoTIFF."""
        if source_path is None:
            return None

        effective_quality = quality if quality is not None else jpeg_quality or 85

        # Mosaic mode: source is already a pre-warped EPSG:4326 file
        if prewarped_map is None:
            result = read_tile_from_warped_geotiff(
                source_path, x, y, zoom, quality=effective_quality
            )
            if result is not None:
                return result
            # Fall through to slow path if fast path fails

        # Per-file mode: look up pre-warped version
        if prewarped_map and source_path in prewarped_map:
            warped_path = prewarped_map[source_path]
            if warped_path != source_path:
                result = read_tile_from_warped_geotiff(
                    warped_path, x, y, zoom, quality=effective_quality
                )
                if result is not None:
                    return result
                # Fall through to slow path if fast path fails

        # Original slow path (per-tile warp)
        return read_tile_from_geotiff(
            source_path, x, y, zoom, quality=effective_quality
        )

    return geotiff_processor


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


# ---------------------------------------------------------------------------
# Composite layer pipeline
# ---------------------------------------------------------------------------


def _download_stac_sub_layer(
    sub: CompositeSubLayer,
    source: SourceConfig,
    layer: LayerConfig,
    cache_dir: Path,
    *,
    display_name: str,
    progress_callback: Callable[[str, str], None] | None,
    sub_idx: int,
    sub_total: int,
    no_download: bool = False,
) -> list[Path]:
    """Download GeoTIFFs for a STAC sub-layer within a composite layer.

    Args:
        sub: Sub-layer configuration
        source: Resolved STAC source config
        layer: Parent composite layer (used for bounds)
        cache_dir: Cache directory
        display_name: Name shown in progress
        progress_callback: Progress callback
        sub_idx: Sub-layer index (for progress)
        sub_total: Total number of sub-layers
        no_download: If True, use cached files only

    Returns:
        List of downloaded GeoTIFF paths
    """
    # Resolve collection ID from source_args (layer variable)
    variables: dict[str, str] = dict(source.defaults)
    if sub.source_args:
        variables.update(sub.source_args)

    collection_id = variables.get("layer", "")
    if not collection_id:
        raise PipelineError(
            f"STAC source '{source.id}' in composite layer '{layer.id}' "
            f"requires a 'layer' variable "
            f"(set in source defaults or sub-layer source_args)"
        )

    if not source.urls:
        raise PipelineError(f"STAC source '{source.id}' has no URL configured")

    url = expand(source.urls[0], variables)
    unresolved = check_unresolved(url)
    if unresolved:
        raise PipelineError(
            f"STAC source '{source.id}' URL has unresolved variables: {unresolved}"
        )

    # Resolve asset_filter: sub-layer override takes precedence over source default.
    # None means no override (use source default), {} means explicit "no filter".
    if sub.asset_filter is not None:
        asset_filter = sub.asset_filter if sub.asset_filter else None
    else:
        asset_filter = source.asset_filter

    stac_dl = STACDownloader(cache_dir)

    if not no_download:
        if progress_callback:
            progress_callback(
                "download",
                f"Sub-layer {sub_idx + 1}/{sub_total}: "
                f"downloading GeoTIFFs from STAC '{collection_id}'...",
            )
        return stac_dl.run(
            source,
            layer,
            url,
            collection_id,
            asset_filter=asset_filter,
        )
    else:
        # Use cached files
        # Use cached files — reconstruct cache directory from previous download
        cache_subdir = stac_dl._get_cache_path(source.id, url, "", asset_filter).parent
        if cache_subdir.exists():
            geotiff_paths = sorted(
                p
                for p in cache_subdir.rglob("*")
                if p.is_file() and p.suffix.lstrip(".") in ("tif", "tiff")
            )
            if geotiff_paths:
                logger.info(
                    "Using %d cached GeoTIFF(s) for sub-layer '%s'",
                    len(geotiff_paths),
                    display_name,
                )
                return geotiff_paths
        raise PipelineError(
            f"No cached GeoTIFFs found for STAC sub-layer '{display_name}' "
            f"collection '{collection_id}'. Run without --no-download first."
        )


def _build_stac_sub_layer_mosaic(
    sub: CompositeSubLayer,
    source: SourceConfig,
    layer: LayerConfig,
    cache_dir: Path,
    *,
    no_download: bool = False,
    progress_callback: Callable[[str, str], None] | None = None,
) -> Path | None:
    """Build a pre-warped mosaic for a STAC sub-layer.

    Downloads GeoTIFFs (if needed), pre-warps to EPSG:4326, and merges
    into a single mosaic file. Returns the mosaic path, or None if no
    files are available.

    Args:
        sub: Sub-layer configuration
        source: Resolved STAC source config
        layer: Parent composite layer (used for bounds)
        cache_dir: Cache directory
        no_download: If True, skip downloads
        progress_callback: Progress callback

    Returns:
        Path to the mosaic file, or None
    """
    # Download/collect GeoTIFFs
    geotiff_paths = _download_stac_sub_layer(
        sub,
        source,
        layer,
        cache_dir,
        display_name=sub.name or source.id,
        progress_callback=progress_callback,
        sub_idx=0,
        sub_total=1,
        no_download=no_download,
    )

    if not geotiff_paths:
        return None

    # Pre-warp and merge
    from .processor.geotiff_prewarp import (
        merge_prewarped_geotiffs,
        prewarp_all_geotiffs,
    )

    prewarped_map = prewarp_all_geotiffs(
        geotiff_paths,
        target_crs="EPSG:4326",
        force=False,
        progress_callback=progress_callback,
    )
    prewarped_paths = list(set(prewarped_map.values()))

    if not prewarped_paths:
        return None

    if len(prewarped_paths) == 1:
        return prewarped_paths[0]

    mosaic_dir = prewarped_paths[0].parent
    return merge_prewarped_geotiffs(
        prewarped_paths,
        cache_dir=mosaic_dir,
        force=False,
        progress_callback=progress_callback,
    )


async def build_composite_layer(
    layer: LayerConfig,
    sources: dict[str, SourceConfig],
    cache_dir: Path,
    output_dir: Path,
    *,
    no_download: bool = False,
    force: bool = False,
    progress_callback: ProgressCallback | None = None,
    export_progress_callback: ExportProgressCallback | None = None,
    preview: bool = False,
    preview_tiles: int = 9,
) -> list[Path]:
    """Build a composite layer from multiple sub-layers.

    Downloads tiles from each sub-layer's source, composites them per-tile
    using painter's algorithm, and exports to IMG.

    Args:
        layer: Layer configuration with sub-layers
        sources: Dictionary of source configurations
        cache_dir: Directory for caching downloaded tiles
        output_dir: Directory for output files
        no_download: If True, skip the download stage
        force: If True, overwrite existing output files
        progress_callback: Called with (stage_id, description) at each stage
        export_progress_callback: Called with (stage, current, total) for export progress

    Returns:
        List of paths to output files
    """
    from .exporters.garmin_img_model import TileMetadata as ExportTileMetadata
    from .exporters.garmin_img_writer import _get_worker_count
    from .processor.rasterio_warp import compute_bounds_4326

    assert layer.layers is not None, "Composite layer must have sub-layers"
    sub_layers = layer.layers

    # --- Download stage: download each sub-layer ---
    if not no_download:
        # Build display slugs for each sub-layer: name if set, else source id
        sub_slugs: list[str] = []
        for sub in sub_layers:
            slug = sub.name or sub.source
            sub_slugs.append(slug)

        if progress_callback:
            progress_callback("download", "Downloading composite sub-layer tiles...")
            for slug in sub_slugs:
                progress_callback("download", f"  - {slug}")

        for idx, sub in enumerate(sub_layers):
            sub_source = _resolve_sub_layer_source(sub, sources, layer.id)
            try:
                if sub_source.type == "stac":
                    _download_stac_sub_layer(
                        sub,
                        sub_source,
                        layer,
                        cache_dir,
                        display_name=sub_slugs[idx],
                        progress_callback=progress_callback,
                        sub_idx=idx,
                        sub_total=len(sub_layers),
                        no_download=False,
                    )
                elif sub_source.type == "wmts":
                    downloader = get_downloader(
                        sub_source,
                        cache_dir,
                        source_args=sub.source_args,
                        display_name=sub_slugs[idx],
                    )

                    if isinstance(downloader, WMTSDownloader):
                        bounds = layer.bounds
                        if not bounds:
                            raise DownloadError(
                                sub_source.id,
                                "WMTS download requires bounds on the composite layer",
                            )
                        bbox = (
                            bounds["west"],
                            bounds["south"],
                            bounds["east"],
                            bounds["north"],
                        )
                        for zoom in sub.zoom_levels:
                            paths = downloader.download_grid(bbox, zoom)
                            if progress_callback:
                                dl_count = len(paths)
                                expected = len(
                                    downloader._bbox_to_tile_indices(bbox, zoom)
                                )
                                if dl_count < expected:
                                    progress_callback(
                                        "download",
                                        f"Sub-layer {idx + 1}/{len(sub_layers)} "
                                        f"zoom {zoom}: "
                                        f"{dl_count}/{expected} tiles available",
                                    )
                else:
                    raise PipelineError(
                        f"Composite sub-layer source type '{sub_source.type}' "
                        f"is not supported. Supported types: wmts, stac"
                    )
            except PipelineError:
                raise
            except Exception as e:
                raise DownloadError(
                    sub_source.id,
                    f"Sub-layer {idx} download failed: {e}",
                    cause=e,
                ) from e
    else:
        logger.info("Skipping download stage (--no-download)")

    # --- Build GeoTIFF mosaics for STAC sub-layers ---
    # Maps sub-layer index -> pre-warped mosaic Path (only for STAC sub-layers)
    stac_mosaics: dict[int, Path] = {}
    for idx, sub in enumerate(sub_layers):
        sub_source = _resolve_sub_layer_source(sub, sources, layer.id)
        if sub_source.type != "stac":
            continue

        try:
            mosaic = _build_stac_sub_layer_mosaic(
                sub,
                sub_source,
                layer,
                cache_dir,
                no_download=no_download,
                progress_callback=progress_callback,
            )
            if mosaic is not None:
                stac_mosaics[idx] = mosaic
                logger.info(
                    "Sub-layer '%s' mosaic: %s",
                    sub.name or sub_source.id,
                    mosaic,
                )
        except Exception as e:
            logger.warning(
                "Failed to build mosaic for STAC sub-layer '%s': %s. "
                "Tiles from this sub-layer will be missing.",
                sub.name or sub_source.id,
                e,
            )

    # --- Compute tile metadata for the composite layer ---
    if progress_callback:
        progress_callback("process", "Computing composite tile metadata...")

    # Determine source CRS (assume all sub-layers use the same CRS as the
    # first sub-layer's source — they must share the same tile grid)
    first_sub = sub_layers[0]
    first_source = _resolve_sub_layer_source(first_sub, sources, layer.id)
    source_crs: str | None
    if first_source.crs:
        source_crs = first_source.crs
    elif first_source.type == "wmts":
        source_crs = "EPSG:3857"
    else:
        source_crs = None

    # Compute tile metadata using the composite layer's zoom levels and bounds.
    # For jpeg_size estimation, we use the first sub-layer's cached tile sizes
    # as a rough estimate (composited tiles will differ but this is good enough
    # for layout planning).
    tile_metadata: dict[int, list[ExportTileMetadata]] = {}
    try:
        for zoom in layer.zoom_levels:
            tile_coords = _compute_tile_coords(layer, zoom)
            if not tile_coords:
                tile_metadata[zoom] = []
                continue

            metadata = []
            for x, y in tile_coords:
                lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(x, y, zoom)

                # Estimate jpeg_size from the first sub-layer that covers this zoom
                jpeg_size = _estimate_composite_tile_size(
                    sub_layers, sources, cache_dir, x, y, zoom
                )

                # source_path points to the first sub-layer's tile (for the writer
                # to have a reference, even though we override the tile_processor)
                source_path = _sub_layer_cache_path(
                    first_sub, sources, cache_dir, x, y, zoom
                )

                metadata.append(
                    ExportTileMetadata(
                        x=x,
                        y=y,
                        zoom=zoom,
                        lat_min=lat_min,
                        lon_min=lon_min,
                        lat_max=lat_max,
                        lon_max=lon_max,
                        jpeg_size=jpeg_size,
                        source_path=source_path,
                    )
                )

            tile_metadata[zoom] = metadata
    except Exception as e:
        raise ProcessingError(layer.id, str(e), cause=e) from e

    total_tiles = sum(len(t) for t in tile_metadata.values())
    if total_tiles == 0:
        raise ProcessingError(layer.id, "No tiles available for composite layer")

    logger.info(
        "Computed metadata for %d composite tiles across %d zoom levels",
        total_tiles,
        len(tile_metadata),
    )

    # --- Export stage: compositing + streaming write to IMG ---
    if progress_callback:
        workers = _get_worker_count()
        if workers > 1:
            progress_callback(
                "export", f"Exporting composite to Garmin IMG ({workers}x parallel)..."
            )
        else:
            progress_callback("export", "Exporting composite to Garmin IMG...")

    output_paths: list[Path]
    try:
        exporter = get_exporter(layer, output_dir)
        output_file = output_dir / layer.output

        if output_file.exists():
            if force:
                output_file.unlink()
            else:
                raise ExportError(
                    layer.id,
                    f"Output file already exists: {output_file}. "
                    f"Use --force to overwrite.",
                )

        # Build a composite-aware tile processor
        composite_processor = _make_composite_processor(
            sub_layers,
            sources,
            cache_dir,
            source_crs or "EPSG:3857",
            stac_mosaics=stac_mosaics,
        )

        output_paths = exporter.export_from_metadata(
            tile_metadata,
            layer,
            output_file,
            source_crs=source_crs or "EPSG:3857",
            quality=None,  # quality applied inside the composite processor
            progress_callback=export_progress_callback,
            tile_processor_override=composite_processor,
        )
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(layer.id, str(e), cause=e) from e

    logger.info(
        f"Composite build complete for layer '{layer.id}': "
        f"{len(output_paths)} file(s) produced"
    )

    # Generate previews if requested
    if preview and tile_metadata:
        from .processor.preview import generate_previews_from_processor

        try:
            if progress_callback:
                progress_callback("preview", "Generating preview images...")
            preview_paths = generate_previews_from_processor(
                layer,
                tile_metadata,
                composite_processor,
                source_crs or "EPSG:3857",
                output_dir,
                max_tiles_per_zoom=preview_tiles,
            )
            if progress_callback:
                for pp in preview_paths:
                    progress_callback("preview", f"  Preview: {pp}")
        except Exception as e:
            logger.warning("Preview generation failed: %s", e)

    return output_paths


def _resolve_sub_layer_source(
    sub: CompositeSubLayer, sources: dict[str, SourceConfig], layer_id: str
) -> SourceConfig:
    """Resolve a sub-layer's source reference."""
    if sub.source in sources:
        return sources[sub.source]
    available = ", ".join(sorted(sources.keys())) if sources else "(none)"
    raise PipelineError(
        f"Layer '{layer_id}' sub-layer references unknown source '{sub.source}'. "
        f"Available sources: {available}"
    )


def _sub_layer_cache_path(
    sub: CompositeSubLayer,
    sources: dict[str, SourceConfig],
    cache_dir: Path,
    x: int,
    y: int,
    zoom: int,
) -> Path | None:
    """Resolve the cache path for a sub-layer tile.

    Computes the same cache key as the WMTSDownloader by resolving
    the source's URL template with the sub-layer's source_args.
    """
    if not sub.source or sub.source not in sources:
        return None
    source = sources[sub.source]
    base = cache_dir / source.id
    # Compute cache key from resolved URL (same as downloader does)
    resolved_url = _resolve_wmts_urls(source, sub.source_args)
    if resolved_url:
        cache_key = _url_cache_key(resolved_url)
        base = base / cache_key
    return base / str(zoom) / str(x) / f"{y}.{sub.extension}"


def _estimate_composite_tile_size(
    sub_layers: list[CompositeSubLayer],
    sources: dict[str, SourceConfig],
    cache_dir: Path,
    x: int,
    y: int,
    zoom: int,
) -> int:
    """Estimate composite tile JPEG size from cached sub-layer tiles.

    Uses the sum of sub-layer tile sizes as a rough upper bound.
    Falls back to 0 if no tiles are found.
    """
    import os

    total = 0
    for sub in sub_layers:
        if zoom not in sub.zoom_levels:
            continue
        path = _sub_layer_cache_path(sub, sources, cache_dir, x, y, zoom)
        if path is not None and path.exists():
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
    # The composited tile will typically be smaller than the sum,
    # but we use the sum as a conservative estimate for layout planning.
    return total if total > 0 else 0


def _make_composite_processor(
    sub_layers: list[CompositeSubLayer],
    sources: dict[str, SourceConfig],
    cache_dir: Path,
    source_crs: str,
    stac_mosaics: dict[int, Path] | None = None,
):
    """Create a tile processor callable that composites sub-layers.

    Returns a callable with the signature expected by the streaming writer:
    (source_path, x, y, zoom, source_crs, quality) -> (jpeg_bytes, bounds) | None
    """
    from .exporters.garmin_img_writer import ProcessedTile
    from .processor.rasterio_warp import compute_bounds_4326

    _stac_mosaics = stac_mosaics or {}

    def composite_processor(
        source_path: Path,
        x: int,
        y: int,
        zoom: int,
        crs: str,
        quality: int,
    ) -> ProcessedTile | None:
        """Load all sub-layer tiles for (x, y, zoom), composite, return JPEG."""
        images: list[tuple] = []

        for idx, sub in enumerate(sub_layers):
            # Skip sub-layers that don't cover this zoom level
            if zoom not in sub.zoom_levels:
                continue

            rgba = None

            # STAC sub-layer: read from pre-warped mosaic
            if idx in _stac_mosaics:
                mosaic_path = _stac_mosaics[idx]
                result = read_tile_from_warped_geotiff(
                    mosaic_path, x, y, zoom, quality=quality
                )
                if result is not None:
                    jpeg_bytes, _bounds = result
                    rgba = Image.open(io.BytesIO(jpeg_bytes))
            else:
                # WMTS sub-layer: load from cached tile
                tile_path = _sub_layer_cache_path(sub, sources, cache_dir, x, y, zoom)

                if tile_path is not None and tile_path.exists():
                    # Load and reproject if needed
                    if source_crs != "EPSG:4326":
                        result = warp_tile_to_rgba(
                            tile_path, x, y, zoom, source_crs, "EPSG:4326"
                        )
                        if result is not None:
                            rgba = result[0]
                    else:
                        rgba = load_tile_as_rgba(tile_path)

                # Try fallback if tile is unavailable
                if rgba is None:
                    # Compute cache key from resolved URL (same as downloader)
                    fb_cache_key = ""
                    if sub.source and sub.source in sources:
                        resolved_url = _resolve_wmts_urls(
                            sources[sub.source], sub.source_args
                        )
                        if resolved_url:
                            fb_cache_key = _url_cache_key(resolved_url)
                    rgba = find_fallback_tile(
                        sub,
                        x,
                        y,
                        zoom,
                        cache_dir,
                        sub.source,
                        cache_key=fb_cache_key,
                    )

            if rgba is not None:
                opacity = resolve_opacity(sub, zoom)
                images.append((rgba, opacity))

        if not images:
            return None

        # Composite all sub-layers
        composited = composite_tiles(images)

        # Encode to JPEG
        jpeg_bytes = encode_composite_to_jpeg(composited, quality=quality or 85)

        bounds = compute_bounds_4326(x, y, zoom)
        return (jpeg_bytes, bounds)

    return composite_processor
