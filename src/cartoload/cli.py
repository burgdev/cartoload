from __future__ import annotations

import asyncio
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .cli_analyze import analyze
from .config import load_config
from .pipeline import (
    DownloadError,
    ExportError,
    PipelineError,
    ProcessingError,
    build_layer,
    get_downloader,
    resolve_source,
)
from .processor.checkpoint import delete_checkpoint
from .processor.build_summary import (
    compute_build_summary,
    format_build_summary,
)
from .downloader.stac import STACDownloader
from .downloader.wmts import WMTSDownloader

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


def _human_size(size: int) -> str:
    """Format a byte count as a human-readable string."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{formatted} {unit}"
        value /= 1024
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{formatted} TB"


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
def main() -> None:
    """cartoload — convert geodata into GPS device maps."""


main.add_command(analyze)


@main.command()
@click.option(
    "-S",
    "--sources",
    multiple=True,
    type=click.Path(exists=True),
    help="Source config file(s) (repeatable)",
)
@click.option(
    "-L",
    "--layers",
    multiple=True,
    type=click.Path(exists=True),
    help="Layer config file(s) (repeatable)",
)
@click.option("-l", "--layer", help="Layer ID to build (required)")
@click.option("-e", "--exporter", help="Override exporter: garmin-img")
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
@click.option("-o", "--output-dir", default="./output", help="Default: ./output")
@click.option("-c", "--cache-dir", default="./cache", help="Default: ./cache")
@click.option("--no-download", is_flag=True, help="Use existing cache only")
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
    "--executor",
    "executor_mode",
    default=None,
    type=click.Choice(["process", "thread"], case_sensitive=False),
    help="Parallel executor mode: 'process' (default, fastest) or 'thread' (less memory)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show detailed tracebacks on errors",
)
def build(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
    layer: str | None,
    exporter: str | None,
    bbox: tuple[float, ...] | None,
    lng: float | None,
    lat: float | None,
    width: float | None,
    height: float | None,
    zoom: str | None,
    output_dir: str,
    cache_dir: str,
    no_download: bool,
    force: bool,
    dry_run: bool,
    cache_warmup: bool,
    preview: bool,
    preview_tiles: int,
    preview_center: tuple[float, ...] | None,
    quality: int | None,
    executor_mode: str | None,
    verbose: bool,
) -> None:
    """Build one or more layers into output files."""
    if not layer:
        raise click.ClickException("--layer is required")

    # Apply executor mode to environment (read by garmin_img_writer._get_executor_mode)
    if executor_mode is not None:
        os.environ["CARTOLOAD_EXECUTOR"] = executor_mode

    try:
        # Load config
        config = load_config(list(sources), list(layers))

        # Resolve layer
        if layer not in config.layers:
            available = ", ".join(sorted(config.layers.keys())) or "(none)"
            raise click.ClickException(
                f"Layer '{layer}' not found. Available layers: {available}"
            )
        layer_config = config.layers[layer]

        # Resolve extent override
        extent = _resolve_extent(bbox, lng, lat, width, height)
        if extent is not None:
            _validate_extent_within_layer(extent, layer_config.bounds)

        zoom_list = _parse_zoom(zoom)

        # Apply overrides to layer_config early (before build summary)
        import dataclasses

        if extent is not None:
            layer_config = dataclasses.replace(layer_config, bounds=extent)
        if zoom_list is not None:
            layer_config = dataclasses.replace(layer_config, zoom_levels=zoom_list)
        if exporter:
            layer_config = dataclasses.replace(layer_config, exporter=exporter)

        # Create paths (don't mkdir yet — dry-run shouldn't create dirs)
        out_dir = Path(output_dir)
        cache = Path(cache_dir)

        # Compute and display build summary
        source = resolve_source(layer_config, config.sources)
        try:
            dl = get_downloader(source, cache, source_args=layer_config.source_args)
            summary = compute_build_summary(layer_config, dl, quality=quality)
            if summary.total_tiles > 0:
                click.echo(
                    format_build_summary(
                        summary, fast_build=summary.all_cached and no_download
                    )
                )
                click.echo()
        except Exception:
            # Summary is best-effort; don't block the build if it fails
            pass

        # Dry run: show plan and exit without creating any files
        if dry_run:
            click.echo("Dry run — no files will be created.")
            return

        # Now create directories (only after dry-run check)
        # Warmup only needs cache dir, not output dir
        cache.mkdir(parents=True, exist_ok=True)
        if not cache_warmup:
            out_dir.mkdir(parents=True, exist_ok=True)

        # Discard checkpoint when --force is used
        if force:
            delete_checkpoint(cache, layer)

        # Progress callback
        def on_progress(stage: str, description: str) -> None:
            click.echo(f"{description}")

        # Rich progress bar for export stage
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=None,
            transient=False,
        )

        with progress:
            extract_task = None
            encode_task = None

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
                    # Per-zoom processing progress: "processing" or "processing:18"
                    parts = stage.split(":", 1)
                    zoom_label = f" (zoom {parts[1]})" if len(parts) > 1 else ""
                    task_key = f"process_{parts[1] if len(parts) > 1 else 'default'}"
                    if not hasattr(on_export_progress, "_tasks"):
                        on_export_progress._tasks = {}  # type: ignore[attr-defined]
                    tasks_dict = on_export_progress._tasks  # type: ignore[attr-defined]
                    if task_key not in tasks_dict:
                        tasks_dict[task_key] = progress.add_task(
                            f"Processing tiles{zoom_label}", total=total
                        )
                    progress.update(tasks_dict[task_key], completed=current)
                elif stage.startswith("writing"):
                    # Per-zoom writing progress: "writing" or "writing:15"
                    parts = stage.split(":", 1)
                    zoom_label = f" (zoom {parts[1]})" if len(parts) > 1 else ""
                    task_key = f"write_{parts[1] if len(parts) > 1 else 'default'}"
                    if not hasattr(on_export_progress, "_tasks"):
                        on_export_progress._tasks = {}  # type: ignore[attr-defined]
                    tasks_dict = on_export_progress._tasks  # type: ignore[attr-defined]
                    if task_key not in tasks_dict:
                        tasks_dict[task_key] = progress.add_task(
                            f"Writing tiles{zoom_label}", total=total
                        )
                    progress.update(tasks_dict[task_key], completed=current)

            # Run pipeline
            output_paths = asyncio.run(
                build_layer(
                    layer_config,
                    config.sources,
                    cache,
                    out_dir,
                    no_download=no_download,
                    force=force,
                    bounds_override=extent,
                    zoom_override=zoom_list,
                    quality=quality,
                    progress_callback=on_progress,
                    export_progress_callback=on_export_progress,
                    warmup_only=cache_warmup,
                    preview=preview,
                    preview_tiles=preview_tiles,
                )
            )

        # Summary
        if cache_warmup:
            click.echo("Cache warmup complete. Tiles are cached and ready for build.")
        else:
            for path in output_paths:
                size = path.stat().st_size
                click.echo(f"Output: {path} ({_human_size(size)})")

        # Generate previews if requested (WMTS cache-based previews;
        # GeoTIFF/STAC/composite previews are already handled in the pipeline)
        if preview:
            try:
                from .processor.preview import generate_previews

                dl = get_downloader(source, cache, source_args=layer_config.source_args)
                if isinstance(dl, WMTSDownloader):
                    preview_paths = generate_previews(
                        layer_config,
                        dl,
                        out_dir,
                        max_tiles_per_zoom=preview_tiles,
                        quality=quality or 85,
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
    "-S",
    "--sources",
    multiple=True,
    type=click.Path(exists=True),
    help="Source config file(s) (repeatable)",
)
@click.option(
    "-L",
    "--layers",
    multiple=True,
    type=click.Path(exists=True),
    help="Layer config file(s) (repeatable)",
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
@click.option("-c", "--cache-dir", default="./cache", help="Default: ./cache")
def download(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
    layer: str | None,
    bbox: tuple[float, ...] | None,
    lng: float | None,
    lat: float | None,
    width: float | None,
    height: float | None,
    zoom: str | None,
    cache_dir: str,
) -> None:
    """Download source data only (no build)."""
    if not layer:
        raise click.ClickException("--layer is required")

    try:
        config = load_config(list(sources), list(layers))

        if layer not in config.layers:
            available = ", ".join(sorted(config.layers.keys())) or "(none)"
            raise click.ClickException(
                f"Layer '{layer}' not found. Available layers: {available}"
            )
        layer_config = config.layers[layer]

        # Resolve source
        source = resolve_source(layer_config, config.sources)

        # Resolve extent override
        extent = _resolve_extent(bbox, lng, lat, width, height)
        if extent is not None:
            _validate_extent_within_layer(extent, layer_config.bounds)

        zoom_list = _parse_zoom(zoom)
        import dataclasses

        if extent:
            layer_config = dataclasses.replace(layer_config, bounds=extent)
        if zoom_list:
            layer_config = dataclasses.replace(layer_config, zoom_levels=zoom_list)

        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)

        click.echo("Downloading tiles...")

        downloader = get_downloader(source, cache, source_args=layer_config.source_args)
        if isinstance(downloader, STACDownloader):
            downloaded = downloader.run(source, layer_config)
        elif isinstance(downloader, WMTSDownloader):
            bounds: dict[str, float] | None = layer_config.bounds
            if not bounds:
                raise click.ClickException("WMTS download requires bounds on the layer")
            bbox = (
                bounds["west"],
                bounds["south"],
                bounds["east"],
                bounds["north"],
            )
            downloaded: list[Path] = []
            for zoom_level in layer_config.zoom_levels:
                paths = downloader.download_grid(bbox, zoom_level)
                downloaded.extend(paths)
        else:
            downloaded = asyncio.run(
                downloader.download(
                    layer_config.zoom_levels,
                    layer_config.bounds or {},
                )
            )

        # Summary
        total_size = sum(f.stat().st_size for f in downloaded) if downloaded else 0
        click.echo(
            f"Downloaded {len(downloaded)} file(s), "
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
    "-S",
    "--sources",
    multiple=True,
    type=click.Path(exists=True),
    help="Source config file(s) (repeatable)",
)
@click.option(
    "-L",
    "--layers",
    multiple=True,
    type=click.Path(exists=True),
    help="Layer config file(s) (repeatable)",
)
def list_layers(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
) -> None:
    """List all layers from the provided config files."""
    if not sources and not layers:
        click.echo(
            "No config files provided.",
            err=True,
        )
        click.echo(
            "Usage: cartoload list --sources path/to/sources.yaml --layers path/to/layers.yaml",
            err=True,
        )
        sys.exit(1)

    try:
        config = load_config(list(sources), list(layers))
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except ValueError as e:
        raise click.ClickException(str(e))

    if not config.layers:
        click.echo("No layers defined in config files.")
        return

    click.echo(f"Found {len(config.layers)} layer(s):\n")

    for layer_id, layer in config.layers.items():
        source = config.sources.get(layer.source)
        source_type = source.type if source else "unknown"
        zoom_str = ",".join(str(z) for z in layer.zoom_levels)

        click.echo(f"  {layer_id}")
        click.echo(f"    Name: {layer.name}")
        click.echo(f"    Source: {layer.source} ({source_type})")
        click.echo(f"    Zoom levels: {zoom_str}")
        click.echo(f"    Exporter: {layer.exporter}")
        click.echo(f"    Output: {layer.output}")
        if layer.description:
            click.echo(f"    Description: {layer.description}")
        click.echo()


# ---------------------------------------------------------------------------
# Cache management commands
# ---------------------------------------------------------------------------


@main.group()
@click.option("-c", "--cache-dir", default="./cache", help="Default: ./cache")
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
    import shutil

    for d in dirs_to_remove:
        shutil.rmtree(d)
        click.echo(f"Removed: {d.name}")

    click.echo(f"Freed: {_human_size(total_size)}")
