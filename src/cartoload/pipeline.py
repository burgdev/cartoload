"""Pipeline orchestration: wires config → downloader → processor → exporter.

This module provides the public API for building targets. The core
implementation lives in ``processor.pipeline.build_target()``.
This module re-exports exceptions and provides backward-compatible
adapter functions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import LayerConfig, SourceConfig, TargetConfig, TargetLayerEntry
from .template import check_unresolved, resolve_templates
from .utils import ExportProgressCallback, ProgressCallback

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
# Source resolution
# ---------------------------------------------------------------------------


def resolve_source_config(
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
# Factory functions (retained for backward compatibility with CLI/tests)
# ---------------------------------------------------------------------------


def get_exporter(
    layer_or_target: LayerConfig | TargetConfig | str, output_dir: Path
) -> "GarminImgExporter":  # noqa: F821
    """Return the correct exporter for the given config.

    Args:
        layer_or_target: LayerConfig, TargetConfig, or exporter name string
        output_dir: Directory for output files

    Returns:
        An exporter instance

    Raises:
        PipelineError: If the exporter type is not supported
    """
    from .exporters.garmin_img import GarminImgExporter

    if isinstance(layer_or_target, str):
        exporter_name = layer_or_target
    else:
        exporter_name = getattr(layer_or_target, "exporter", None)

    if exporter_name in ("garmin-img", "garmin_img"):
        return GarminImgExporter()
    raise PipelineError(
        f"Unknown exporter '{exporter_name}'. Supported exporters: garmin-img"
    )


def get_downloader(
    source: SourceConfig,
    cache_dir: Path,
    *,
    source_args: dict[str, str] | None = None,
    display_name: str = "",
) -> "WmtsDownloader":  # noqa: F821
    """Return a WMTS downloader for the given source config.

    This function is retained for backward compatibility with the CLI's
    cache warmup and direct WMTS download features.

    Args:
        source: Source configuration (type must be 'wmts')
        cache_dir: Directory for caching downloaded tiles
        source_args: Layer-level variable overrides for template resolution.
        display_name: Name shown in download progress bars.

    Returns:
        A WmtsDownloader instance

    Raises:
        PipelineError: If the source type is not 'wmts'
    """
    from .source.wmts import WmtsDownloader

    if source.type != "wmts":
        raise PipelineError(
            f"get_downloader only supports 'wmts' sources, "
            f"got '{source.type}' for source '{source.id}'."
        )

    if not source.urls:
        raise PipelineError(f"WMTS source '{source.id}' missing required 'urls'")

    variables: dict[str, str] = dict(source.defaults)
    if source_args:
        variables.update(source_args)

    resolved_urls = resolve_templates(source.urls, variables) if source.urls else []

    _PER_TILE_VARS = {"x", "y", "z", "zoom"}
    for u in resolved_urls:
        unres = check_unresolved(u)
        unknown = [v for v in unres if v not in _PER_TILE_VARS]
        if unknown:
            raise PipelineError(
                f"Source '{source.id}' URL has unresolved variables "
                f"with no default: {unknown}. "
                f"Define them in source 'defaults' or layer 'source_args'."
            )

    tile_format = variables.get("extension", "jpeg")
    layer_name = variables.get("layer", "")
    effective_template = resolved_urls[0] if resolved_urls else ""

    return WmtsDownloader(
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


# ---------------------------------------------------------------------------
# Tile coordinate computation (used by tests and build summary)
# ---------------------------------------------------------------------------


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
    from cartoload.tile_math import bounds_to_tile_coords

    bounds = layer.bounds
    if not bounds:
        return []

    return bounds_to_tile_coords(
        bounds["west"], bounds["south"], bounds["east"], bounds["north"], zoom
    )


# ---------------------------------------------------------------------------
# Main entry point: build_layer → build_target adapter
# ---------------------------------------------------------------------------


async def build_layer(
    layer: LayerConfig,
    sources: dict[str, SourceConfig],
    cache_dir: Path,
    output_dir: Path,
    *,
    no_download: bool = False,
    offline: bool = False,
    update: bool = False,
    max_age_days: int | None = None,
    force: bool = False,
    bounds_override: dict[str, float] | None = None,
    zoom_override: list[int] | None = None,
    quality: int | None = None,
    qtables: tuple[list[int], list[int]] | None = None,
    progress_callback: ProgressCallback | None = None,
    export_progress_callback: ExportProgressCallback | None = None,
    checkpoint: bool = True,
    warmup_only: bool = False,
    preview: bool = False,
    preview_tiles: int = 9,
) -> list[Path]:
    """Orchestrate download → process → export for a single layer.

    This is a backward-compatible adapter that converts a ``LayerConfig``
    into a ``TargetConfig`` and delegates to the unified
    ``build_target()`` pipeline.

    For new code, prefer calling ``build_target()`` directly with a
    ``TargetConfig``.

    Args:
        layer: Layer configuration (must have exporter and output set,
            or be a composite layer with layers defined)
        sources: Dictionary of source configurations
        cache_dir: Directory for caching downloaded tiles
        output_dir: Directory for output files
        no_download: If True, skip the download stage
        force: If True, overwrite existing output files
        bounds_override: Override the layer bounds
        zoom_override: Override the layer zoom levels
        quality: JPEG quality for tile encoding
        progress_callback: Called with (stage_id, description) at each stage
        export_progress_callback: Called with (stage, current, total)
        checkpoint: If True, write checkpoints for resume support
        warmup_only: If True, download and process but skip export
        preview: If True, generate preview images
        preview_tiles: Max tiles per zoom level in preview mosaics

    Returns:
        List of paths to output files
    """
    from .processor.pipeline import build_target

    # Convert LayerConfig → TargetConfig
    target = _layer_to_target(layer)
    layers: dict[str, LayerConfig] = {layer.id: layer}

    return await build_target(
        target,
        layers,
        sources,
        cache_dir,
        output_dir,
        no_download=no_download,
        offline=offline,
        update=update,
        max_age_days=max_age_days,
        force=force,
        bounds_override=bounds_override,
        zoom_override=zoom_override,
        quality=quality,
        qtables=qtables,
        progress_callback=progress_callback,
        export_progress_callback=export_progress_callback,
        checkpoint=checkpoint,
        warmup_only=warmup_only,
        preview=preview,
        preview_tiles=preview_tiles,
    )


def _layer_to_target(layer: LayerConfig) -> TargetConfig:
    """Convert a LayerConfig into a TargetConfig for the unified pipeline.

    Handles both single-layer and composite (multi-layer) configs.
    """
    # Check if this is a composite layer (has sub-layers)
    layers_attr = getattr(layer, "layers", None)
    if layers_attr:
        # Composite: use the sub-layers directly
        target_layers = layers_attr
    else:
        # Single layer: create one TargetLayerEntry from the layer
        target_layers = [
            TargetLayerEntry(
                name=layer.name,
                source=layer.source,
                format=getattr(layer, "format", "wmts"),
                zoom_levels=layer.zoom_levels,
                source_args=layer.source_args,
                asset_filter=getattr(layer, "asset_filter", None),
                rules=getattr(layer, "rules", None),
                style=getattr(layer, "style", None),
                garmin_types=getattr(layer, "garmin_types", None),
            )
        ]

    # Get output and exporter from the layer (backward compat)
    output = getattr(layer, "output", f"{layer.id}.img")
    exporter = getattr(layer, "exporter", "garmin_img")

    return TargetConfig(
        id=layer.id,
        name=layer.name,
        output=output,
        exporter=exporter,
        layers=target_layers,
        zoom_levels=layer.zoom_levels,
        bounds=layer.bounds,
        config_dir=getattr(layer, "config_dir", None),
    )


def __getattr__(name: str):
    """Lazy re-export from pipeline to avoid circular imports."""
    if name == "build_target":
        from .processor.pipeline import build_target

        return build_target
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
