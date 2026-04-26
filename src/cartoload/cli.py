from __future__ import annotations

import asyncio
import math
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
from .downloader.geotiff import GeoTIFFDownloader
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
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size //= 1024
    return f"{size:.1f} TB"


def _handle_pipeline_error(error: PipelineError) -> None:
    """Convert a PipelineError to a Click exception."""
    raise click.ClickException(str(error))


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
@click.option(
    "-q",
    "--quality",
    default=85,
    type=click.IntRange(1, 100),
    help="JPEG quality 1-100 (default: 85)",
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
    quality: int,
) -> None:
    """Build one or more layers into output files."""
    if not layer:
        raise click.ClickException("--layer is required")

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
        if exporter:
            import dataclasses

            layer_config = dataclasses.replace(layer_config, exporter=exporter)

        # Create output dir
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)

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
                )
            )

        # Summary
        for path in output_paths:
            size = path.stat().st_size
            click.echo(f"Output: {path} ({_human_size(size)})")

    except click.ClickException:
        raise
    except (PipelineError, DownloadError, ProcessingError, ExportError) as e:
        _handle_pipeline_error(e)
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

        downloader = get_downloader(
            source, cache, layer_name=layer_config.wmts_layer or ""
        )
        if isinstance(downloader, GeoTIFFDownloader):
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
