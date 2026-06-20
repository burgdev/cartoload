"""Unified pipeline: one entry point for all target builds.

Replaces the old dispatch in `build_layer()` that branched into
`build_composite_layer`, `build_geotiff_layer`, `build_gpkg_layer`,
and inline WMTS handling. The unified pipeline treats single-layer targets
as the degenerate case of composite (1 provider, no compositing needed).

Lifecycle per provider:
  1. download()  — fetch data via Source
  2. prepare()   — pre-warp, build index, rasterize, etc.
  3. to_raster() — produce RGBA tiles on demand

The export stage uses either:
  - Fast path: 1 provider → use provider's raw bytes directly (no RGBA round-trip)
  - Composite path: N providers → per-tile RGBA compositing, re-encode to JPEG
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from PIL import Image

from cartoload.config import (
    LayerConfig,
    SourceConfig,
    TargetConfig,
    TargetLayerEntry,
)
from cartoload.source.base import resolve_source
from cartoload.processor.checkpoint import (
    CheckpointData,
    delete_checkpoint,
    read_checkpoint,
    write_checkpoint,
)
from cartoload.processor.base import make_processor
from cartoload.processor.wmts.processor import WmtsProcessor
from ..utils import human_size as _human_size
from ..utils import ExportProgressCallback, ProgressCallback
from cartoload.tile_math import bounds_to_tile_coords as _bounds_to_tile_coords

if TYPE_CHECKING:
    from cartoload.processor.base import LayerProcessor

logger = logging.getLogger(__name__)


# Import domain exceptions from pipeline module.
# This is safe because pipeline.py uses lazy imports to avoid circular deps.
from cartoload.pipeline import (  # noqa: E402
    DownloadError,
    ExportError,
    PipelineError,
    ProcessingError,
    resolve_source_config as _resolve_layer_source,
)

# Re-export for convenience
__all__ = [
    "PipelineError",
    "DownloadError",
    "ProcessingError",
    "ExportError",
    "build_target",
]


# ---------------------------------------------------------------------------
# Target layer resolution
# ---------------------------------------------------------------------------


def _resolve_target_entry(
    entry: TargetLayerEntry,
    layers: dict[str, LayerConfig],
    target: TargetConfig,
) -> LayerConfig:
    """Resolve a TargetLayerEntry into a concrete LayerConfig.

    If the entry is a ref (``entry.ref`` is set), look up the referenced
    layer definition and merge entry-level overrides (source_args, opacity,
    zoom_levels, style) on top.

    If the entry is inline (has ``source`` and ``format``), build a
    LayerConfig directly from the entry.
    """
    if entry.ref:
        if entry.ref not in layers:
            raise PipelineError(
                f"Target '{target.id}' references unknown layer '{entry.ref}'. "
                f"Available layers: {', '.join(sorted(layers.keys())) or '(none)'}"
            )
        base = layers[entry.ref]
        # Merge entry overrides onto the base layer
        overrides: dict = {}
        if entry.source_args:
            # Merge source_args: entry overrides base
            merged_args = dict(base.source_args)
            merged_args.update(entry.source_args)
            overrides["source_args"] = merged_args
        if entry.zoom_levels:
            overrides["zoom_levels"] = entry.zoom_levels
        if entry.format:
            overrides["format"] = entry.format
        if entry.source:
            overrides["source"] = entry.source
        if entry.rules is not None:
            overrides["rules"] = entry.rules
        if entry.style is not None:
            overrides["style"] = entry.style
        if entry.garmin_types is not None:
            overrides["garmin_types"] = entry.garmin_types
        if entry.asset_filter is not None:
            overrides["asset_filter"] = entry.asset_filter
        if not overrides:
            return base
        return replace(base, **overrides)
    else:
        # Inline entry — build a LayerConfig from the entry fields
        if not entry.source or not entry.format:
            raise PipelineError(
                f"Target '{target.id}' has an inline layer entry without "
                f"'source' or 'format'. Set both, or use 'ref' to reference "
                f"a layer definition."
            )
        return LayerConfig(
            id=f"{target.id}__{entry.name or entry.source}",
            name=entry.name or entry.source,
            source=entry.source,
            format=entry.format,
            source_args=entry.source_args,
            zoom_levels=entry.zoom_levels,
            bounds=target.bounds,
            rules=entry.rules,
            style=entry.style,
            garmin_types=entry.garmin_types,
            asset_filter=entry.asset_filter,
        )


def _resolve_target_layers(
    target: TargetConfig,
    layers: dict[str, LayerConfig],
) -> list[tuple[TargetLayerEntry, LayerConfig]]:
    """Resolve all layer entries in a target.

    Returns a list of (original_entry, resolved_LayerConfig) pairs.
    """
    if not target.layers:
        raise PipelineError(
            f"Target '{target.id}' has no layers defined. "
            f"Add at least one layer entry (ref or inline)."
        )
    result = []
    for entry in target.layers:
        lc = _resolve_target_entry(entry, layers, target)
        result.append((entry, lc))
    return result


# ---------------------------------------------------------------------------
# Metadata computation
# ---------------------------------------------------------------------------


def _compute_tile_coords(bounds: dict[str, float], zoom: int) -> list[tuple[int, int]]:
    """Compute tile grid coordinates for a zoom level within given bounds."""
    return _bounds_to_tile_coords(
        bounds["west"], bounds["south"], bounds["east"], bounds["north"], zoom
    )


def _compute_target_metadata(
    target: TargetConfig,
    zoom_levels: list[int],
) -> dict[int, list[tuple[int, int]]]:
    """Compute tile coordinates for each zoom level of the target.

    Returns a dict mapping zoom level to list of (x, y) tile coords.
    """
    bounds = target.bounds
    if not bounds:
        raise ProcessingError(target.id, "Target has no bounds defined")

    tile_coords: dict[int, list[tuple[int, int]]] = {}
    for zoom in zoom_levels:
        coords = _compute_tile_coords(bounds, zoom)
        tile_coords[zoom] = coords
        logger.debug("Target '%s' zoom %d: %d tiles", target.id, zoom, len(coords))
    return tile_coords


# ---------------------------------------------------------------------------
# Tile processors for export
# ---------------------------------------------------------------------------


def _make_single_provider_processor(
    provider: LayerProcessor,
):
    """Create a tile processor callable for the fast (single-provider) path.

    The processor uses the provider's to_raster() to get an Image, then
    encodes to JPEG at quality 95 (intermediate step). The target quality
    is applied only during the final IMG write step.

    Returns a callable with the signature:
        (source_path, x, y, zoom, source_crs, quality) -> (jpeg_bytes, bounds) | None
    """
    from cartoload.tile_math import ProcessedTile, compute_bounds_4326
    from ..utils import encode_jpeg

    def single_processor(
        source_path: Path | None,
        x: int,
        y: int,
        zoom: int,
        crs: str,
        jpeg_quality: int | None,
    ) -> ProcessedTile | None:
        img = provider.to_raster(x, y, zoom)
        if img is None:
            return None

        # Convert to JPEG at high quality (95) — target quality applied later
        jpeg_bytes = encode_jpeg(img, quality=95)
        bounds = compute_bounds_4326(x, y, zoom)
        return (jpeg_bytes, bounds)

    return single_processor


def _make_composite_processor(
    providers: list[tuple[TargetLayerEntry, LayerProcessor, LayerConfig]],
):
    """Create a tile processor callable for the composite (multi-provider) path.

    For each tile coordinate, reads RGBA images from all providers,
    composites them using painter's algorithm, and encodes to JPEG
    at quality 95 (intermediate step). The target quality is applied
    only during the final IMG write step.

    Returns a callable with the signature:
        (source_path, x, y, zoom, source_crs, quality) -> (jpeg_bytes, bounds) | None
    """
    from cartoload.exporters.garmin_img_writer import ProcessedTile
    from cartoload.processor.compositor import (
        composite_tiles,
        encode_composite_to_jpeg,
        resolve_opacity,
    )
    from cartoload.tile_math import compute_bounds_4326

    def composite_processor(
        source_path: Path | None,
        x: int,
        y: int,
        zoom: int,
        crs: str,
        jpeg_quality: int | None,
    ) -> ProcessedTile | None:
        images: list[tuple[Image.Image, float]] = []

        for entry, provider, lc in providers:
            # Skip providers that don't cover this zoom level
            if zoom not in lc.zoom_levels:
                continue

            rgba = provider.to_raster(x, y, zoom)
            if rgba is None:
                continue

            # Normalize to 256x256
            if rgba.size != (256, 256):
                rgba = rgba.resize((256, 256), Image.Resampling.BILINEAR)

            opacity = resolve_opacity(entry, zoom)
            images.append((rgba, opacity))

        if not images:
            return None

        # Composite all layers
        composited = composite_tiles(images)

        # Encode to JPEG at high quality (95) — target quality applied later
        jpeg_bytes = encode_composite_to_jpeg(composited)

        bounds = compute_bounds_4326(x, y, zoom)
        return (jpeg_bytes, bounds)

    return composite_processor


# ---------------------------------------------------------------------------
# Tile fallback
# ---------------------------------------------------------------------------


def _find_fallback_tile(
    providers: list[tuple[TargetLayerEntry, LayerProcessor, LayerConfig]],
    x: int,
    y: int,
    zoom: int,
) -> Image.Image | None:
    """Try to find a fallback tile by upscaling from a lower zoom level.

    Walks zoom levels from (zoom-1) down to 0, checking if any provider
    can produce a tile that covers the requested area.
    """
    for fallback_zoom in range(zoom - 1, -1, -1):
        # Compute the parent tile coordinates
        scale = 2 ** (zoom - fallback_zoom)
        fx = x // scale
        fy = y // scale

        for _entry, provider, lc in providers:
            if fallback_zoom not in lc.zoom_levels:
                continue
            img = provider.to_raster(fx, fy, fallback_zoom)
            if img is not None:
                # Crop to the relevant quadrant
                quadrant_x = (x % scale) * (256 // scale)
                quadrant_y = (y % scale) * (256 // scale)
                quad_size = 256 // scale
                cropped = img.crop(
                    (
                        quadrant_x,
                        quadrant_y,
                        quadrant_x + quad_size,
                        quadrant_y + quad_size,
                    )
                )
                return cropped.resize((256, 256), Image.Resampling.BILINEAR)
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def build_target(
    target: TargetConfig,
    layers: dict[str, LayerConfig],
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
    fast: bool = False,
) -> list[Path]:
    """Build a target: download → prepare → metadata → export.

    This is the single unified entry point that handles all source types
    and formats. Single-layer targets use a fast path; multi-layer targets
    use per-tile RGBA compositing.

    Args:
        target: Build target configuration
        layers: Dictionary of layer definitions
        sources: Dictionary of source configurations
        cache_dir: Directory for caching downloaded data
        output_dir: Directory for output files
        no_download: If True, skip the download stage
        offline: If True, only use cached data
        update: If True, check freshness via HTTP HEAD (ETag/Last-Modified)
        max_age_days: If set, skip freshness check if downloaded < N days ago
        force: If True, overwrite existing output files
        bounds_override: Override the target bounds
        zoom_override: Override the target zoom levels
        quality: JPEG quality for tile encoding
        qtables: Custom quantization tables (luma, chroma) in zigzag order, or None
        progress_callback: Called with (stage_id, description) at each stage
        export_progress_callback: Called with (stage, current, total) for export progress
        checkpoint: If True, write checkpoint after each zoom level
        warmup_only: If True, download and process but skip IMG export
        preview: If True, generate preview images after export
        preview_tiles: Max tiles per zoom level in preview mosaics

    Returns:
        List of paths to output files
    """
    from cartoload.exporters.garmin_img import GarminImgExporter
    from cartoload.exporters.garmin_img_model import TileMetadata as ExportTileMetadata
    from cartoload.exporters.garmin_img_writer import _get_worker_count
    from cartoload.tile_math import compute_bounds_4326

    # Apply overrides
    effective_target = _apply_target_overrides(target, bounds_override, zoom_override)

    # --- Resolve target layers ---
    resolved = _resolve_target_layers(effective_target, layers)

    # Resolve zoom_levels from referenced layers if target omits them
    if not effective_target.zoom_levels:
        all_zooms = set()
        for _entry, lc in resolved:
            all_zooms.update(lc.zoom_levels)
        effective_target.zoom_levels = sorted(all_zooms)

    # Resolve bounds from referenced layers if target omits them
    if not effective_target.bounds:
        layer_bounds = [lc.bounds for _entry, lc in resolved if lc.bounds]
        if layer_bounds:
            effective_target.bounds = {
                "west": min(b["west"] for b in layer_bounds),
                "south": min(b["south"] for b in layer_bounds),
                "east": max(b["east"] for b in layer_bounds),
                "north": max(b["north"] for b in layer_bounds),
            }

    # --- Create providers ---
    providers: list[tuple[TargetLayerEntry, LayerProcessor, LayerConfig]] = []
    for entry, lc in resolved:
        # Resolve source
        source_config = _resolve_layer_source(lc, sources)
        # Create source instance
        source_cls = resolve_source(source_config.type)
        source_instance = source_cls()
        # Create provider
        provider = make_processor(
            lc.format, source_instance, source_config, lc, cache_dir
        )
        providers.append((entry, provider, lc))

    # --- Stage 1: Download ---
    if not no_download:
        for idx, (entry, provider, _lc) in enumerate(providers):
            lc = resolved[idx][1]
            display_name = entry.name or lc.source
            if progress_callback:
                progress_callback(
                    "download",
                    f"Layer {idx + 1}/{len(providers)}: downloading {display_name}...",
                )
            try:
                provider.download(
                    offline=offline, update=update, max_age_days=max_age_days
                )
            except Exception as e:
                source_id = lc.source
                raise DownloadError(source_id, str(e), cause=e) from e

            # Pre-fetch WMTS tiles with progress bars (download_grid() shows
            # per-zoom Rich progress). Without this, tiles are fetched one at
            # a time during export with no visible progress.
            if (
                isinstance(provider, WmtsProcessor)
                and provider.downloader is not None
                and lc.bounds
            ):
                bbox = (
                    lc.bounds["west"],
                    lc.bounds["south"],
                    lc.bounds["east"],
                    lc.bounds["north"],
                )
                for zoom in lc.zoom_levels:
                    provider.downloader.download_grid(bbox, zoom)
    else:
        logger.info("Skipping download stage (--no-download)")

    # --- Stage 2: Prepare ---
    for idx, (entry, provider, _lc) in enumerate(providers):
        lc = resolved[idx][1]
        display_name = entry.name or lc.source
        if progress_callback:
            progress_callback(
                "process",
                f"Layer {idx + 1}/{len(providers)}: preparing {display_name}...",
            )
        try:
            provider.prepare()
        except Exception as e:
            raise ProcessingError(lc.id, str(e), cause=e) from e

    # --- Stage 3: Compute tile metadata ---
    if progress_callback:
        progress_callback("process", "Computing tile metadata...")

    # Merge zoom levels from target and all providers
    zoom_levels = effective_target.zoom_levels
    if not zoom_levels:
        # Collect from all resolved layers
        zoom_set: set[int] = set()
        for _entry, lc in resolved:
            zoom_set.update(lc.zoom_levels)
        zoom_levels = sorted(zoom_set)
        if not zoom_levels:
            raise ProcessingError(
                effective_target.id,
                "No zoom levels defined on target or any of its layers",
            )

    # --- Checkpoint: detect and resume ---
    cp_data: CheckpointData | None = None
    if checkpoint:
        cp_data = read_checkpoint(cache_dir, effective_target.id)
        if cp_data is not None:
            completed = set(cp_data.completed_zoom_levels)
            requested = set(zoom_levels)
            if completed <= requested:
                skipped = completed & requested
                if skipped:
                    logger.info(
                        "Resuming build for target '%s': zoom levels %s already completed",
                        effective_target.id,
                        sorted(skipped),
                    )
            else:
                logger.warning(
                    "Stale checkpoint for target '%s' (extra zooms), starting fresh",
                    effective_target.id,
                )
                cp_data = None

    # Determine remaining zoom levels
    if cp_data is not None:
        completed_zooms = set(cp_data.completed_zoom_levels)
        remaining_zooms = [z for z in zoom_levels if z not in completed_zooms]
    else:
        remaining_zooms = list(zoom_levels)
        if checkpoint:
            cp_data = CheckpointData(
                layer_id=effective_target.id,
                completed_zoom_levels=[],
                remaining_zoom_levels=list(zoom_levels),
            )
            write_checkpoint(cache_dir, cp_data)

    tile_coords = _compute_target_metadata(effective_target, remaining_zooms)

    # Build tile metadata for the streaming writer (only remaining zooms)
    tile_metadata: dict[int, list[ExportTileMetadata]] = {}
    for zoom in remaining_zooms:
        coords = tile_coords.get(zoom, [])
        metadata = []
        for x, y in coords:
            lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(x, y, zoom)
            # Estimate jpeg_size — will be refined by sampling if composite
            jpeg_size = 50_000  # ~50KB default estimate
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
                    source_path=None,  # Not used in unified pipeline
                )
            )
        tile_metadata[zoom] = metadata

    total_tiles = sum(len(t) for t in tile_metadata.values())
    if total_tiles == 0:
        raise ProcessingError(effective_target.id, "No tiles available for processing")

    logger.info(
        "Computed metadata for %d tiles across %d zoom levels for target '%s'",
        total_tiles,
        len(tile_metadata),
        effective_target.id,
    )

    # Warmup mode: stop after metadata computation
    if warmup_only:
        logger.info(
            "Warmup complete for target '%s': %d tiles",
            effective_target.id,
            total_tiles,
        )
        # Delete checkpoint since we're not building an IMG
        if checkpoint:
            delete_checkpoint(cache_dir, effective_target.id)
        return []

    # --- Stage 4: Export ---
    if progress_callback:
        workers = _get_worker_count()
        if workers > 1:
            progress_callback(
                "export",
                f"Exporting to Garmin IMG ({workers}x parallel)...",
            )
        else:
            progress_callback("export", "Exporting to Garmin IMG...")

    # Select fast path or composite path
    if len(providers) == 1:
        # Fast path: single provider, no compositing
        _entry, provider, _lc = providers[0]
        tile_processor = _make_single_provider_processor(provider)
    else:
        # Composite path: multiple providers
        tile_processor = _make_composite_processor(providers)

    # Refine jpeg_size estimates by sampling a few tiles
    _refine_jpeg_sizes(
        tile_metadata,
        tile_processor,
        quality=quality or 85,
        qtables=qtables,
        fast=fast,
    )

    # Report tile count and estimated output size
    estimated_jpeg_total = sum(
        t.jpeg_size for tiles in tile_metadata.values() for t in tiles
    )
    # JPEG data is ~85% of total GMP size; add overhead for headers/RGN2/LBL
    estimated_total = estimated_jpeg_total / 0.85 if estimated_jpeg_total > 0 else 0
    if progress_callback:
        size_str = _human_size(estimated_total)
        progress_callback(
            "export",
            f"  {total_tiles:,} tiles, estimated output: ~{size_str}",
        )

    # Determine effective CRS
    source_crs = "EPSG:4326"  # All providers output in 4326

    output_paths: list[Path]
    try:
        exporter = GarminImgExporter()
        output_file = output_dir / effective_target.output

        if output_file.exists():
            if force:
                output_file.unlink()
            else:
                raise ExportError(
                    effective_target.id,
                    f"Output file already exists: {output_file}. "
                    f"Use --force to overwrite.",
                )

        # Build a pseudo layer config for the exporter
        # The exporter needs zoom_levels and bounds
        export_layer = _make_export_layer_config(effective_target, zoom_levels)

        output_paths = exporter.export_from_metadata(
            tile_metadata,
            export_layer,
            output_file,
            source_crs=source_crs,
            quality=quality,
            qtables=qtables,
            progress_callback=export_progress_callback,
            tile_processor_override=tile_processor,
            fast=fast,
        )
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(effective_target.id, str(e), cause=e) from e

    logger.info(
        "Build complete for target '%s': %d file(s) produced",
        effective_target.id,
        len(output_paths),
    )

    # Delete checkpoint on successful completion
    if checkpoint:
        delete_checkpoint(cache_dir, effective_target.id)

    # Generate previews if requested
    if preview and tile_metadata:
        from cartoload.processor.preview import generate_previews_from_processor

        try:
            if progress_callback:
                progress_callback("preview", "Generating preview images...")
            export_layer = _make_export_layer_config(effective_target, zoom_levels)
            preview_paths = generate_previews_from_processor(
                export_layer,
                tile_metadata,
                tile_processor,
                source_crs,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_target_overrides(
    target: TargetConfig,
    bounds_override: dict[str, float] | None,
    zoom_override: list[int] | None,
) -> TargetConfig:
    """Apply CLI overrides to a target config, returning a new copy."""
    kwargs: dict = {}
    if bounds_override is not None:
        kwargs["bounds"] = bounds_override
    if zoom_override is not None:
        kwargs["zoom_levels"] = zoom_override
    if not kwargs:
        return target
    return replace(target, **kwargs)


def _make_export_layer_config(
    target: TargetConfig,
    zoom_levels: list[int],
) -> LayerConfig:
    """Create a minimal LayerConfig for the exporter.

    The exporter needs zoom_levels, bounds, output, exporter, and name/id.
    We create a LayerConfig that satisfies these requirements.
    """
    return LayerConfig(
        id=target.id,
        name=target.name or target.id,
        source="",  # Not used by exporter
        format="",  # Not used by exporter
        zoom_levels=zoom_levels,
        bounds=target.bounds,
        config_dir=target.config_dir,
    )


def _refine_jpeg_sizes(
    tile_metadata: dict[int, list],
    tile_processor: Callable,
    max_samples_per_zoom: int = 20,
    *,
    quality: int = 85,
    qtables: tuple[list[int], list[int]] | None = None,
    fast: bool = False,
) -> None:
    """Sample tiles through the processor and update jpeg_size estimates.

    Processes tiles per zoom level, measures actual JPEG output sizes,
    and updates the jpeg_size in tile metadata for accurate layout planning.

    The tile processor produces quality-95 intermediate JPEGs. If the target
    quality differs, samples are re-encoded at the target quality so the
    stored jpeg_size reflects the actual output size.
    """
    import random

    from cartoload.exporters.garmin_img_model import TileMetadata as ExportTileMetadata
    from cartoload.exporters.garmin_img_writer import _reencode_jpeg

    needs_reencode = quality < 95

    for zoom, tiles in tile_metadata.items():
        if not tiles:
            continue

        candidates = [t for t in tiles if isinstance(t, ExportTileMetadata)]
        if not candidates:
            continue

        sample_tiles = random.sample(
            candidates, min(max_samples_per_zoom, len(candidates))
        )

        samples: list[int] = []
        for tile in sample_tiles:
            result = tile_processor(
                tile.source_path,
                tile.x,
                tile.y,
                tile.zoom,
                "EPSG:4326",
                quality,
            )
            if result is not None:
                jpeg_bytes = result[0]
                if needs_reencode:
                    jpeg_bytes = _reencode_jpeg(jpeg_bytes, quality, qtables, fast=fast)
                samples.append(len(jpeg_bytes))

        if not samples:
            continue

        samples.sort()
        median_size = samples[len(samples) // 2]
        for tile in tiles:
            if isinstance(tile, ExportTileMetadata):
                tile.jpeg_size = median_size

        logger.debug(
            "Target jpeg_size for zoom %d: %d bytes (from %d samples, quality=%d)",
            zoom,
            median_size,
            len(samples),
            quality,
        )
