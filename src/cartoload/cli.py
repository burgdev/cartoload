from __future__ import annotations

import asyncio
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


def _parse_bounds(value: str | None) -> dict[str, float] | None:
    """Parse a 'west,south,east,north' bounds string into a dict."""
    if value is None:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise click.BadParameter(
            f"Bounds must be 'west,south,east,north', got '{value}'"
        )
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError:
        raise click.BadParameter(f"Bounds values must be numeric, got '{value}'")
    return {"west": west, "south": south, "east": east, "north": north}


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


@main.command()
@click.option(
    "--sources",
    multiple=True,
    type=click.Path(exists=True),
    help="Source config file(s) (repeatable)",
)
@click.option(
    "--layers",
    multiple=True,
    type=click.Path(exists=True),
    help="Layer config file(s) (repeatable)",
)
@click.option("--layer", help="Layer ID to build (required)")
@click.option("--exporter", help="Override exporter: garmin-img")
@click.option("--bounds", help='Override bounding box: "west,south,east,north"')
@click.option("--zoom", help="Override zoom levels: 10,12,14")
@click.option("--output-dir", default="./output", help="Default: ./output")
@click.option("--cache-dir", default="./cache", help="Default: ./cache")
@click.option("--no-download", is_flag=True, help="Use existing cache only")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing output files")
@click.option(
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
    bounds: str | None,
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

        # Apply overrides
        bounds_dict = _parse_bounds(bounds)
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
                    bounds_override=bounds_dict,
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
    "--sources",
    multiple=True,
    type=click.Path(exists=True),
    help="Source config file(s) (repeatable)",
)
@click.option(
    "--layers",
    multiple=True,
    type=click.Path(exists=True),
    help="Layer config file(s) (repeatable)",
)
@click.option("--layer", help="Layer ID to download (required)")
@click.option("--bounds", help='Override bounding box: "west,south,east,north"')
@click.option("--zoom", help="Override zoom levels: 10,12,14")
@click.option("--cache-dir", default="./cache", help="Default: ./cache")
def download(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
    layer: str | None,
    bounds: str | None,
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

        # Apply overrides
        bounds_dict = _parse_bounds(bounds)
        zoom_list = _parse_zoom(zoom)
        import dataclasses

        if bounds_dict:
            layer_config = dataclasses.replace(layer_config, bounds=bounds_dict)
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
    "--output-dir", default=None, help="Output directory (default: same as input)"
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
    "--sources",
    multiple=True,
    type=click.Path(exists=True),
    help="Source config file(s) (repeatable)",
)
@click.option(
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
