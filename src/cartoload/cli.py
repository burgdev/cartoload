from __future__ import annotations

import asyncio
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

import click
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from . import __version__
from .analysis.cli import analyze
from .config import (
    load_config,
    resolve_settings,
    LayerConfig,
    TargetConfig,
    TargetLayerEntry,
)
from .pipeline import (
    DownloadError,
    ExportError,
    PipelineError,
    ProcessingError,
    build_target,
    get_downloader,
    resolve_source_config,
)
from .utils import human_size as _human_size
from .processor.checkpoint import delete_checkpoint
from .processor.summary import (
    compute_build_summary,
    format_build_summary,
)
from .source.stac.downloader import STACDownloader
from .source.wmts import WmtsDownloader

FOUR_GB = 4_294_967_296


def _parse_bbox(value: tuple[float, ...] | None) -> dict[str, float] | None:
    """Parse a --bbox tuple of 4 floats into a bounds dict."""
    if value is None:
        return None
    if len(value) != 4:
        raise click.BadParameter(
            f"Bbox requires exactly 4 values (W S E N), got {len(value)}"
        )
    west, south, east, north = value
    return {"west": west, "south": south, "east": east, "north": north}


def _compute_bounds_from_center(
    lng: float, lat: float, width_km: float, height_km: float
) -> dict[str, float]:
    """Convert center point + km dimensions to a bounds dict."""
    lat_delta = height_km / 111.32 / 2
    lng_delta = width_km / (111.32 * math.cos(math.radians(lat))) / 2
    return {
        "west": lng - lng_delta,
        "east": lng + lng_delta,
        "south": lat - lat_delta,
        "north": lat + lat_delta,
    }


def _resolve_extent(
    bbox: tuple[float, ...] | None,
    lng: float | None,
    lat: float | None,
    width: float | None,
    height: float | None,
) -> dict[str, float] | None:
    """Resolve extent from --bbox or --lng/--lat/--width/--height, validating mutual exclusivity."""
    has_bbox = bbox is not None
    has_center = (
        lng is not None or lat is not None or width is not None or height is not None
    )

    if has_bbox and has_center:
        raise click.BadParameter(
            "Cannot use --bbox and --lng/--lat/--width/--height together. "
            "Use one or the other."
        )

    if has_bbox:
        return _parse_bbox(bbox)

    if has_center:
        if lng is None or lat is None:
            raise click.BadParameter(
                "--lng and --lat are required when using center+dimensions mode"
            )
        if width is None or height is None:
            raise click.BadParameter(
                "--width and --height are required when using center+dimensions mode"
            )
        return _compute_bounds_from_center(lng, lat, width, height)

    return None


def _validate_extent_within_layer(
    extent: dict[str, float], layer_bounds: dict[str, float] | None
) -> None:
    """Validate that the requested extent fits within the layer's configured bounds."""
    if layer_bounds is None:
        return
    if (
        extent["west"] < layer_bounds["west"]
        or extent["south"] < layer_bounds["south"]
        or extent["east"] > layer_bounds["east"]
        or extent["north"] > layer_bounds["north"]
    ):
        raise click.BadParameter(
            f"Requested extent ({extent['west']:.4f}, {extent['south']:.4f}, "
            f"{extent['east']:.4f}, {extent['north']:.4f}) exceeds layer bounds "
            f"({layer_bounds['west']:.4f}, {layer_bounds['south']:.4f}, "
            f"{layer_bounds['east']:.4f}, {layer_bounds['north']:.4f})"
        )


def _parse_zoom(value: str | None) -> list[int] | None:
    """Parse a comma-separated zoom levels string into a list."""
    if value is None:
        return None
    try:
        return [int(z.strip()) for z in value.split(",")]
    except ValueError:
        raise click.BadParameter(f"Zoom levels must be integers, got '{value}'")


def _handle_pipeline_error(error: PipelineError, *, verbose: bool = False) -> None:
    """Convert a PipelineError to a Click exception."""
    msg = str(error)
    if error.__cause__ is not None:
        if verbose:
            from rich.console import Console
            from rich.traceback import Traceback

            console = Console(stderr=True)
            tb = Traceback.from_exception(
                type(error.__cause__),
                error.__cause__,
                error.__cause__.__traceback__,
            )
            console.print(tb)
        else:
            msg += "\n  Use -v for full traceback."
    raise click.ClickException(msg)


def _handle_unexpected_error(error: Exception) -> None:
    """Handle unexpected exceptions with a brief message."""
    raise click.ClickException(
        f"Unexpected error: {error}\n"
        f"Please report this issue at https://github.com/burgdev/cartoload/issues"
    )


@click.group()
@click.version_option(version=__version__, prog_name="cartoload")
def main() -> None:
    """cartoload — convert geodata into GPS device maps."""


main.add_command(analyze)


@main.command()
@click.option(
    "-c",
    "--config",
    "config_files",
    multiple=True,
    type=click.Path(exists=True),
    help="Config file(s) (repeatable)",
)
@click.option("-l", "--layer", help="Layer ID to build (required)")
@click.option(
    "-b", "--bbox", nargs=4, type=float, help="Override bounding box: W S E N"
)
@click.option(
    "-x",
    "--lng",
    type=float,
    help="Center longitude for extent (use with --lat/--width/--height)",
)
@click.option(
    "-y",
    "--lat",
    type=float,
    help="Center latitude for extent (use with --lng/--width/--height)",
)
@click.option(
    "-W",
    "--width",
    type=float,
    help="Extent width in km (use with --lng/--lat/--height)",
)
@click.option(
    "-H",
    "--height",
    type=float,
    help="Extent height in km (use with --lng/--lat/--width)",
)
@click.option("-z", "--zoom", help="Override zoom levels: 10,12,14")
@click.option("-o", "--output-dir", default=None, help="Default: ./output")
@click.option("-C", "--cache-dir", default=None, help="Default: ./cache")
@click.option("--no-download", is_flag=True, help="Use existing cache only")
@click.option(
    "--offline", is_flag=True, help="Skip freshness checks, use cached files as-is"
)
@click.option(
    "--update", "do_update", is_flag=True, help="Check cache freshness via HTTP HEAD"
)
@click.option(
    "--ago",
    type=int,
    default=None,
    help="Only update if cached file is older than N days",
)
@click.option("-f", "--force", is_flag=True, help="Overwrite existing output files")
@click.option("--dry-run", is_flag=True, help="Show build plan without executing")
@click.option(
    "--cache-warmup", is_flag=True, help="Download and cache tiles only, skip IMG build"
)
@click.option("--preview", is_flag=True, help="Generate preview images after build")
@click.option(
    "-P",
    "--preview-tiles",
    type=int,
    default=9,
    help="Max tiles per preview mosaic (default: 9)",
)
@click.option(
    "--preview-center",
    nargs=2,
    type=float,
    help="Override preview center: LNG LAT",
)
@click.option(
    "-q",
    "--quality",
    default=None,
    type=click.IntRange(1, 100),
    help="JPEG quality 1-100 (default: passthrough, no re-encoding)",
)
@click.option(
    "--qtables",
    "qtables_preset",
    default=None,
    type=click.Choice(["raster", "default"], case_sensitive=False),
    help="Custom quantization tables: 'raster' (map-optimized) or 'default' (standard)",
)
@click.option(
    "--executor",
    "executor_mode",
    default=None,
    type=click.Choice(["process", "thread"], case_sensitive=False),
    help="Parallel executor mode: 'process' (default, fastest) or 'thread' (less memory)",
)
@click.option(
    "--fast",
    "fast_build",
    is_flag=True,
    help="Fast build: skip mirror-padding and cjpeg trellis optimization (larger output)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show detailed tracebacks on errors",
)
def build(
    config_files: tuple[str, ...],
    layer: str | None,
    bbox: tuple[float, ...] | None,
    lng: float | None,
    lat: float | None,
    width: float | None,
    height: float | None,
    zoom: str | None,
    output_dir: str | None,
    cache_dir: str | None,
    no_download: bool,
    offline: bool,
    do_update: bool,
    ago: int | None,
    force: bool,
    dry_run: bool,
    cache_warmup: bool,
    preview: bool,
    preview_tiles: int,
    preview_center: tuple[float, ...] | None,
    quality: int | None,
    qtables_preset: str | None,
    executor_mode: str | None,
    fast_build: bool,
    verbose: bool,
) -> None:
    """Build one or more layers into output files."""
    if not layer:
        raise click.ClickException("--layer is required (specify a target or layer ID)")

    # Apply executor mode to environment (read by garmin_img_writer._get_executor_mode)
    if executor_mode is not None:
        os.environ["CARTOLOAD_EXECUTOR"] = executor_mode

    try:
        # Load config
        config = load_config(list(config_files))

        # Resolve settings: env vars override config, CLI flags override env vars
        resolved = resolve_settings(config.settings)
        effective_output_dir = output_dir or cast(
            str, resolved.get("output_dir", "./output")
        )
        effective_cache_dir = cache_dir or cast(
            str, resolved.get("cache_dir", "./cache")
        )
        effective_quality: int | None = quality or cast(
            int | None, resolved.get("quality")
        )
        effective_executor: str | None = executor_mode or cast(
            str | None, resolved.get("executor")
        )

        # Resolve custom quantization tables from preset name + quality
        # CLI --qtables takes precedence over config jpeg_qtables
        effective_qtables_preset = qtables_preset or resolved.get("jpeg_qtables")
        effective_qtables = None
        if effective_qtables_preset and effective_qtables_preset != "default":
            from cartoload.exporters.garmin_img_writer import get_qtables

            if effective_quality is None:
                raise click.ClickException(
                    "--qtables requires --quality to be set (quality determines "
                    "the compression level of the custom tables)"
                )
            effective_qtables = get_qtables(
                str(effective_qtables_preset), int(effective_quality)
            )
        if effective_executor is not None:
            os.environ["CARTOLOAD_EXECUTOR"] = effective_executor

        # --ago implies --update
        effective_update = do_update or (ago is not None)
        effective_max_age = ago

        # Resolve the -l argument: try targets first, then layers
        target_config: TargetConfig | None = None
        layer_config = None

        if layer in config.targets:
            target_config = config.targets[layer]
        elif layer in config.layers:
            # Auto-wrap a layer definition as a single-layer target
            lc = config.layers[layer]
            target_config = TargetConfig(
                id=lc.id,
                name=lc.name,
                output=f"{lc.id}.img",
                exporter="garmin_img",
                layers=[
                    TargetLayerEntry(
                        name=lc.name,
                        source=lc.source,
                        format=lc.format,
                        zoom_levels=lc.zoom_levels,
                        source_args=lc.source_args,
                        asset_filter=lc.asset_filter,
                        rules=lc.rules,
                        style=lc.style,
                        garmin_types=lc.garmin_types,
                    )
                ],
                zoom_levels=lc.zoom_levels,
                bounds=lc.bounds,
                config_dir=lc.config_dir,
            )
            layer_config = lc
        else:
            available_targets = ", ".join(sorted(config.targets.keys())) or "(none)"
            available_layers = ", ".join(sorted(config.layers.keys())) or "(none)"
            raise click.ClickException(
                f"'{layer}' not found in targets or layers.\n"
                f"  Available targets: {available_targets}\n"
                f"  Available layers: {available_layers}"
            )

        # Resolve extent override
        extent = _resolve_extent(bbox, lng, lat, width, height)
        if extent is not None:
            _validate_extent_within_layer(extent, target_config.bounds)

        zoom_list = _parse_zoom(zoom)

        # Create paths (don't mkdir yet — dry-run shouldn't create dirs)
        out_dir = Path(effective_output_dir)
        cache = Path(effective_cache_dir)

        # Compute and display build summary (best-effort)
        if layer_config is not None:
            try:
                source = resolve_source_config(layer_config, config.sources)
                dl = get_downloader(source, cache, source_args=layer_config.source_args)
                summary = compute_build_summary(
                    layer_config, dl, quality=effective_quality
                )
                if summary.total_tiles > 0:
                    click.echo(
                        format_build_summary(
                            summary, fast_build=summary.all_cached and no_download
                        )
                    )
                    click.echo()
            except Exception:
                pass

        # Dry run: show plan and exit without creating any files
        if dry_run:
            click.echo("Dry run — no files will be created.")
            return

        # Now create directories (only after dry-run check)
        cache.mkdir(parents=True, exist_ok=True)
        if not cache_warmup:
            out_dir.mkdir(parents=True, exist_ok=True)

        # Discard checkpoint when --force is used
        if force:
            delete_checkpoint(cache, layer)

        # Rich progress bar for export stage
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TextColumn("ETA "),
            TimeRemainingColumn(compact=True, elapsed_when_finished=True),
            console=None,
            transient=False,
        )

        # Use Rich's console for all output to avoid double-printing
        # when progress bars refresh
        rich_console = progress.console

        # Route Python logging through Rich so log messages don't corrupt
        # the progress bar display
        import logging

        log_level = logging.INFO if verbose else logging.WARNING
        rich_handler = RichHandler(
            console=rich_console,
            level=log_level,
            show_time=False,
            show_path=False,
            markup=True,
        )
        root_logger = logging.getLogger()
        root_logger.addHandler(rich_handler)
        root_logger.setLevel(log_level)

        def on_progress(stage: str, description: str) -> None:
            rich_console.print(description)

        with progress:
            extract_task = None
            encode_task = None

            _progress_tasks: dict[str, TaskID] = {}

            def on_export_progress(stage: str, current: int, total: int) -> None:
                nonlocal extract_task, encode_task
                if stage == "extracting":
                    if extract_task is None:
                        extract_task = progress.add_task(
                            "Extracting tiles", total=total
                        )
                    progress.update(extract_task, completed=current)
                elif stage == "encoding":
                    if encode_task is None:
                        encode_task = progress.add_task("Encoding tiles", total=total)
                    progress.update(encode_task, completed=current)
                elif stage.startswith("processing"):
                    parts = stage.split(":", 1)
                    zoom_label = f" (zoom {parts[1]})" if len(parts) > 1 else ""
                    task_key = f"process_{parts[1] if len(parts) > 1 else 'default'}"
                    if task_key not in _progress_tasks:
                        _progress_tasks[task_key] = progress.add_task(
                            f"Processing tiles{zoom_label}", total=total
                        )
                    progress.update(_progress_tasks[task_key], completed=current)
                elif stage.startswith("writing"):
                    parts = stage.split(":", 1)
                    zoom_label = f" (zoom {parts[1]})" if len(parts) > 1 else ""
                    task_key = f"write_{parts[1] if len(parts) > 1 else 'default'}"
                    if task_key not in _progress_tasks:
                        _progress_tasks[task_key] = progress.add_task(
                            f"Writing tiles{zoom_label}", total=total
                        )
                    progress.update(_progress_tasks[task_key], completed=current)

            # Run the unified pipeline
            output_paths = asyncio.run(
                build_target(
                    target_config,
                    config.layers,
                    config.sources,
                    cache,
                    out_dir,
                    no_download=no_download,
                    offline=offline,
                    update=effective_update,
                    max_age_days=effective_max_age,
                    force=force,
                    bounds_override=extent,
                    zoom_override=zoom_list,
                    quality=effective_quality,
                    qtables=effective_qtables,
                    progress_callback=on_progress,
                    export_progress_callback=on_export_progress,
                    warmup_only=cache_warmup,
                    preview=preview,
                    preview_tiles=preview_tiles,
                    fast=fast_build,
                )
            )

        # Summary
        root_logger.removeHandler(rich_handler)

        if cache_warmup:
            click.echo("Cache warmup complete. Tiles are cached and ready for build.")
        else:
            for path in output_paths:
                size = path.stat().st_size
                click.echo(f"Output: {path} ({_human_size(size)})")

        # Generate previews if requested
        if preview and layer_config is not None:
            try:
                from .processor.preview import generate_previews

                source = resolve_source_config(layer_config, config.sources)
                dl = get_downloader(source, cache, source_args=layer_config.source_args)
                if isinstance(dl, WmtsDownloader):
                    preview_paths = generate_previews(
                        layer_config,
                        dl,
                        out_dir,
                        max_tiles_per_zoom=preview_tiles,
                        quality=effective_quality or 85,
                    )
                    for pp in preview_paths:
                        click.echo(f"Preview: {pp}")
                    if not preview_paths:
                        click.echo("No previews generated (no cached tiles available)")
            except PipelineError:
                # Source doesn't support WMTS downloader — previews were
                # already generated by the pipeline (GeoTIFF/STAC/composite)
                pass
            except Exception as e:
                click.echo(f"Preview generation failed: {e}", err=True)

    except click.ClickException:
        raise
    except (PipelineError, DownloadError, ProcessingError, ExportError) as e:
        _handle_pipeline_error(e, verbose=verbose)
    except Exception as e:
        _handle_unexpected_error(e)


@main.command()
@click.option(
    "-c",
    "--config",
    "config_files",
    multiple=True,
    type=click.Path(exists=True),
    help="Config file(s) (repeatable)",
)
@click.option("-l", "--layer", help="Layer ID to download (required)")
@click.option(
    "-b", "--bbox", nargs=4, type=float, help="Override bounding box: W S E N"
)
@click.option(
    "-x",
    "--lng",
    type=float,
    help="Center longitude for extent (use with --lat/--width/--height)",
)
@click.option(
    "-y",
    "--lat",
    type=float,
    help="Center latitude for extent (use with --lng/--width/--height)",
)
@click.option(
    "-W",
    "--width",
    type=float,
    help="Extent width in km (use with --lng/--lat/--height)",
)
@click.option(
    "-H",
    "--height",
    type=float,
    help="Extent height in km (use with --lng/--lat/--width)",
)
@click.option("-z", "--zoom", help="Override zoom levels: 10,12,14")
@click.option("-C", "--cache-dir", default=None, help="Default: ./cache")
def download(
    config_files: tuple[str, ...],
    layer: str | None,
    bbox: tuple[float, ...] | None,
    lng: float | None,
    lat: float | None,
    width: float | None,
    height: float | None,
    zoom: str | None,
    cache_dir: str | None,
) -> None:
    """Download source data only (no build)."""
    if not layer:
        raise click.ClickException("--layer is required")

    try:
        config = load_config(list(config_files))

        # Resolve settings
        resolved = resolve_settings(config.settings)
        effective_cache_dir = cache_dir or cast(
            str, resolved.get("cache_dir", "./cache")
        )

        # Resolve -l against targets and layers (matching build behavior)
        layers_to_download: list[tuple[str, LayerConfig]] = []

        if layer in config.targets:
            # Download all layers referenced by this target
            target = config.targets[layer]
            for entry in target.layers:
                if entry.ref and entry.ref in config.layers:
                    layers_to_download.append((entry.ref, config.layers[entry.ref]))
                elif entry.source:
                    # Inline entry — create LayerConfig
                    lc = LayerConfig(
                        id=entry.name or entry.source,
                        name=entry.name or entry.source,
                        source=entry.source,
                        format=entry.format,
                        zoom_levels=entry.zoom_levels or target.zoom_levels,
                        bounds=target.bounds,
                        source_args=entry.source_args,
                    )
                    layers_to_download.append((lc.id, lc))
        elif layer in config.layers:
            layers_to_download.append((layer, config.layers[layer]))
        else:
            available_targets = ", ".join(sorted(config.targets.keys())) or "(none)"
            available_layers = ", ".join(sorted(config.layers.keys())) or "(none)"
            raise click.ClickException(
                f"'{layer}' not found in targets or layers.\n"
                f"  Available targets: {available_targets}\n"
                f"  Available layers: {available_layers}"
            )

        # Resolve extent override
        extent = _resolve_extent(bbox, lng, lat, width, height)
        zoom_list = _parse_zoom(zoom)

        cache = Path(effective_cache_dir)
        cache.mkdir(parents=True, exist_ok=True)

        import dataclasses

        total_downloaded: list[Path] = []

        for layer_id, layer_config in layers_to_download:
            if extent is not None:
                _validate_extent_within_layer(extent, layer_config.bounds)

            lc = layer_config
            if extent:
                lc = dataclasses.replace(lc, bounds=extent)
            if zoom_list:
                lc = dataclasses.replace(lc, zoom_levels=zoom_list)

            click.echo(f"Downloading tiles for '{layer_id}'...")

            source = resolve_source_config(lc, config.sources)
            downloader = get_downloader(source, cache, source_args=lc.source_args)
            if isinstance(downloader, STACDownloader):
                from cartoload.template import expand

                resolved_url = expand(
                    source.urls[0] if source.urls else "",
                    {**source.defaults, **lc.source_args},
                )
                collection_id = lc.source_args.get("layer", "")
                downloaded = downloader.run(source, lc, resolved_url, collection_id)
            elif isinstance(downloader, WmtsDownloader):
                bounds: dict[str, float] | None = lc.bounds
                if not bounds:
                    raise click.ClickException(
                        "WMTS download requires bounds on the layer"
                    )
                dl_bbox = (
                    bounds["west"],
                    bounds["south"],
                    bounds["east"],
                    bounds["north"],
                )
                downloaded: list[Path] = []
                for zoom_level in lc.zoom_levels:
                    paths = downloader.download_grid(dl_bbox, zoom_level)
                    downloaded.extend(paths)
            else:
                downloaded = asyncio.run(
                    downloader.download(
                        lc.zoom_levels,
                        lc.bounds or {},
                    )
                )

            total_downloaded.extend(downloaded)

        # Summary
        total_size = (
            sum(f.stat().st_size for f in total_downloaded) if total_downloaded else 0
        )
        click.echo(
            f"Downloaded {len(total_downloaded)} file(s), "
            f"total cache size: {_human_size(total_size)}"
        )

    except click.ClickException:
        raise
    except PipelineError as e:
        _handle_pipeline_error(e)
    except Exception as e:
        _handle_unexpected_error(e)


@main.command()
@click.argument("img_file", type=click.Path())
@click.option(
    "-o", "--output-dir", default=None, help="Output directory (default: same as input)"
)
def split(img_file: str, output_dir: str | None) -> None:
    """Split an oversized .img into region files."""
    input_path = Path(img_file)

    # Validate file exists
    if not input_path.exists():
        raise click.ClickException(f"File not found: {input_path}")

    # Check file size
    file_size = input_path.stat().st_size
    if file_size <= FOUR_GB:
        click.echo(
            f"File is {_human_size(file_size)}, under the 4 GB limit. "
            f"Splitting is not needed."
        )
        return

    click.echo(f"File is {_human_size(file_size)}, exceeds 4 GB limit. Splitting...")

    # Check for gmt
    if not shutil.which("gmt"):
        raise click.ClickException(
            "GMapTool (gmt) not found on PATH.\n"
            "Install it from http://www.gmaptool.eu/ or use the cartoload Docker image."
        )

    # Determine output directory
    out_dir = Path(output_dir) if output_dir else input_path.parent

    try:
        result = subprocess.run(
            ["gmt", "-i", str(input_path)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(out_dir),
        )
        if result.returncode != 0:
            raise click.ClickException(
                f"gmt failed with exit code {result.returncode}:\n{result.stderr}"
            )
        click.echo(f"Split complete. Output in {out_dir}")
    except subprocess.TimeoutExpired:
        raise click.ClickException("gmt timed out after 300 seconds")
    except click.ClickException:
        raise
    except Exception as e:
        _handle_unexpected_error(e)


@main.command("list")
@click.option(
    "-c",
    "--config",
    "config_files",
    multiple=True,
    type=click.Path(exists=True),
    help="Config file(s) (repeatable)",
)
def list_layers(
    config_files: tuple[str, ...],
) -> None:
    """List all layers from the provided config files."""
    if not config_files:
        raise click.ClickException(
            "No config files provided. Usage: cartoload list -c path/to/config.yaml"
        )

    try:
        config = load_config(list(config_files))
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except ValueError as e:
        raise click.ClickException(str(e))

    if not config.layers and not config.targets:
        click.echo("No layers or targets defined in config files.")
        return

    # List targets
    if config.targets:
        click.echo(f"Targets ({len(config.targets)}):\n")
        for tid, target in config.targets.items():
            zoom_str = ",".join(str(z) for z in target.zoom_levels)
            layer_names = ", ".join(
                entry.name or entry.ref or entry.source for entry in target.layers
            )
            click.echo(f"  {tid}")
            click.echo(f"    Name: {target.name}")
            click.echo(f"    Layers: {layer_names}")
            click.echo(f"    Output: {target.output}")
            click.echo(f"    Zoom levels: {zoom_str}")
            if target.description:
                click.echo(f"    Description: {target.description}")
            click.echo()

    # List layer definitions
    if config.layers:
        click.echo(f"Layer definitions ({len(config.layers)}):\n")
        for layer_id, layer in config.layers.items():
            source = config.sources.get(layer.source)
            source_type = source.type if source else "unknown"
            zoom_str = ",".join(str(z) for z in layer.zoom_levels)

            click.echo(f"  {layer_id}")
            click.echo(f"    Name: {layer.name}")
            click.echo(f"    Source: {layer.source} ({source_type})")
            click.echo(f"    Format: {layer.format}")
            click.echo(f"    Zoom levels: {zoom_str}")
            if layer.description:
                click.echo(f"    Description: {layer.description}")
            click.echo()


# ---------------------------------------------------------------------------
# Cache management commands
# ---------------------------------------------------------------------------


@main.group()
@click.option("-C", "--cache-dir", default="./cache", help="Default: ./cache")
@click.pass_context
def cache(ctx: click.Context, cache_dir: str) -> None:
    """Inspect and manage the tile cache."""
    ctx.ensure_object(dict)
    ctx.obj["cache_dir"] = Path(cache_dir)


@cache.command("status")
@click.pass_context
def cache_status(ctx: click.Context) -> None:
    """Report cache size and tile counts per source."""
    cache_dir: Path = ctx.obj["cache_dir"]

    if not cache_dir.exists():
        click.echo(f"Cache directory does not exist: {cache_dir}")
        return

    # Discover source directories
    source_dirs = sorted(
        d for d in cache_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )

    if not source_dirs:
        click.echo("Cache is empty.")
        return

    total_size = 0
    total_tiles = 0

    for source_dir in source_dirs:
        name = source_dir.name

        # Count tiles and size
        tile_count = 0
        tile_size = 0
        tile_extensions = {".jpeg", ".jpg", ".png", ".tif", ".tiff"}
        for f in source_dir.rglob("*"):
            if f.is_file() and f.suffix in tile_extensions:
                tile_count += 1
                tile_size += f.stat().st_size

        total_size += tile_size
        total_tiles += tile_count

        click.echo(f"  {name}")
        click.echo(f"    Tiles: {tile_count}")
        click.echo(f"    Size:  {_human_size(tile_size)}")
        click.echo()

    click.echo(f"Total: {total_tiles} tiles, {_human_size(total_size)}")


@cache.command("clean")
@click.option("--source", help="Clean only a specific source's cache")
@click.option("-f", "--force", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def cache_clean(ctx: click.Context, source: str | None, force: bool) -> None:
    """Remove cached tiles."""
    cache_dir: Path = ctx.obj["cache_dir"]

    if not cache_dir.exists():
        click.echo(f"Cache directory does not exist: {cache_dir}")
        return

    # Find directories to remove
    dirs_to_remove: list[Path] = []

    if source:
        source_dir = cache_dir / source
        if source_dir.exists():
            dirs_to_remove.append(source_dir)
    else:
        dirs_to_remove = sorted(
            d for d in cache_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

    if not dirs_to_remove:
        click.echo("Nothing to clean.")
        return

    # Calculate total size
    total_size = 0
    for d in dirs_to_remove:
        for f in d.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size

    # Confirm
    if not force:
        dir_names = ", ".join(d.name for d in dirs_to_remove)
        click.echo(f"Will remove: {dir_names}")
        click.echo(f"Total size: {_human_size(total_size)}")
        if not click.confirm("Continue?"):
            click.echo("Aborted.")
            return

    # Remove
    for d in dirs_to_remove:
        shutil.rmtree(d)
        click.echo(f"Removed: {d.name}")

    click.echo(f"Freed: {_human_size(total_size)}")


# ---------------------------------------------------------------------------
# Watermark commands
# ---------------------------------------------------------------------------

_ENV_KEY = "CARTOLOAD_WATERMARK_KEY"


def _resolve_key(key: str | None, key_file: str | None) -> str:
    """Resolve watermark key from --key, --key-file, or env var."""
    if key:
        return key
    if key_file:
        return Path(key_file).read_text().strip()
    env_key = os.environ.get(_ENV_KEY)
    if env_key:
        return env_key
    raise click.ClickException(
        f"No key provided. Use --key, --key-file, or set {_ENV_KEY} env var."
    )


@main.group()
def watermark() -> None:
    """Read and write forensic watermarks in Garmin IMG files."""


@watermark.command("write")
@click.argument("img_file", type=click.Path(exists=True))
@click.argument("payload")
@click.option("--key", default=None, help="Encryption key")
@click.option(
    "--key-file", default=None, type=click.Path(exists=True), help="Read key from file"
)
@click.option("--header", default=None, help="Cleartext header string (e.g. order=ID)")
def watermark_write(
    img_file: str,
    payload: str,
    key: str | None,
    key_file: str | None,
    header: str | None,
) -> None:
    """Write a watermark string into a Garmin IMG file."""
    from cartoload.watermark import write_watermark

    resolved_key = _resolve_key(key, key_file)
    try:
        write_watermark(img_file, payload, resolved_key, header=header)
        click.echo("Watermark written.")
    except ValueError as e:
        raise click.ClickException(str(e)) from e


@watermark.command("read")
@click.argument("img_file", type=click.Path(exists=True))
@click.option("--key", default=None, help="Encryption key")
@click.option(
    "--key-file", default=None, type=click.Path(exists=True), help="Read key from file"
)
def watermark_read(img_file: str, key: str | None, key_file: str | None) -> None:
    """Read and print the watermark from a Garmin IMG file."""
    from cartoload.watermark import read_watermark, read_watermark_header

    # Read cleartext header first (no key needed)
    header = read_watermark_header(img_file)

    # Try to resolve key for encrypted payload
    has_key = key is not None or key_file is not None or os.environ.get(_ENV_KEY)
    if has_key:
        resolved_key = _resolve_key(key, key_file)
        result = read_watermark(img_file, resolved_key)
        if result.payload is None and header is None:
            click.echo("No watermark found.")
        else:
            if header is not None:
                click.echo(f"Header:  {header}")
            if result.payload is not None:
                click.echo(f"Payload: {result.payload}")
            elif header is not None:
                click.echo("Payload: (no encrypted watermark found)")
    else:
        # No key — show header only
        if header is not None:
            click.echo(f"Header:  {header}")
            click.echo("Payload: (key required to decrypt)")
        else:
            click.echo("No watermark found.")


@watermark.command("read-header")
@click.argument("img_file", type=click.Path(exists=True))
def watermark_read_header(img_file: str) -> None:
    """Read the cleartext header from a Garmin IMG file (no key required)."""
    from cartoload.watermark import read_watermark_header

    header = read_watermark_header(img_file)
    if header is None:
        click.echo("No cleartext header found.")
    else:
        click.echo(header)
