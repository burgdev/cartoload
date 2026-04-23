"""Pipeline orchestration: wires config → downloader → processor → exporter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .config import LayerConfig, SourceConfig
from .downloader.geotiff import GeoTIFFDownloader
from .downloader.wmts import WMTSDownloader
from .exporters.garmin_img import GarminImgExporter
from .processor.raster import RasterProcessor

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
        if not source.url_template:
            raise PipelineError(
                f"WMTS source '{source.id}' missing required 'url_template'"
            )
        return WMTSDownloader(
            source_id=source.id,
            url_template=source.url_template,
            cache_dir=cache_dir,
            max_workers=source.max_threads,
            delay_ms=source.rate_limit_ms,
            layer_name=layer_name,
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
    quality: int = 85,
    progress_callback: ProgressCallback | None = None,
    export_progress_callback: ExportProgressCallback | None = None,
) -> list[Path]:
    """Orchestrate download → process → export for a single layer.

    Args:
        layer: Layer configuration
        sources: Dictionary of source configurations
        cache_dir: Directory for caching downloaded tiles
        output_dir: Directory for output files
        no_download: If True, skip the download stage
        bounds_override: Override the layer bounds
        zoom_override: Override the layer zoom levels
        quality: JPEG quality for tile encoding
        progress_callback: Called with (stage_id, description) at each stage

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

    # --- Download stage ---
    downloaded_paths: list[Path] = []
    if not no_download:
        if progress_callback:
            progress_callback("download", "Downloading tiles...")
        try:
            downloader = get_downloader(
                source, cache_dir, layer_name=effective_layer.wmts_layer or ""
            )
            if isinstance(downloader, GeoTIFFDownloader):
                downloaded_paths = downloader.run(source, effective_layer)
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
                for zoom in effective_layer.zoom_levels:
                    paths = downloader.download_grid(bbox, zoom)
                    downloaded_paths.extend(paths)
            else:
                downloaded_paths = await downloader.download(
                    effective_layer.zoom_levels,
                    effective_layer.bounds or {},
                )
        except PipelineError:
            raise
        except Exception as e:
            raise DownloadError(source.id, str(e), cause=e) from e
    else:
        logger.info("Skipping download stage (--no-download)")
        # Collect already-cached tiles
        downloaded_paths = _collect_cached_tiles(cache_dir, source, effective_layer)

    # --- Process stage ---
    if progress_callback:
        progress_callback("process", "Processing raster data...")
    processed_path: Path

    # Check for existing output files
    output_tif = output_dir / f"{layer.id}.tif"
    existing = [
        p for ext in (".tif", ".vrt") if (p := output_tif.with_suffix(ext)).exists()
    ]
    if existing:
        if force:
            for p in existing:
                p.unlink()
        else:
            paths_str = ", ".join(str(p) for p in existing)
            raise ProcessingError(
                layer.id,
                f"Output file(s) already exist: {paths_str}. Use --force to overwrite.",
            )

    # Determine source CRS for georeferencing
    source_crs = "EPSG:3857" if source.type == "wmts" else None

    try:
        processor = RasterProcessor(
            target_crs="EPSG:4326",
            output_path=output_dir / f"{layer.id}.tif",
            source_crs=source_crs,
        )
        if downloaded_paths:
            processed_path = processor.process(downloaded_paths)
        else:
            raise ProcessingError(layer.id, "No tiles available for processing")
    except ProcessingError:
        raise
    except Exception as e:
        raise ProcessingError(layer.id, str(e), cause=e) from e

    # --- Export stage ---
    if progress_callback:
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

        output_paths = exporter.export(
            processed_path,
            effective_layer,
            output_file,
            progress_callback=export_progress_callback,
        )
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(layer.id, str(e), cause=e) from e

    logger.info(
        f"Build complete for layer '{layer.id}': {len(output_paths)} file(s) produced"
    )
    return output_paths


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
