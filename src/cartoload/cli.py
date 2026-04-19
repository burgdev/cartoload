from __future__ import annotations

import click


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
@click.option(
    "--layer", multiple=True, help="Layer ID to build (repeatable; default: all)"
)
@click.option("--exporter", help="Override exporter: garmin_img | garmin_img_vec")
@click.option("--bounds", help='Override bounding box: "west,east,south,north"')
@click.option("--zoom", help="Override zoom levels: 10,12,14")
@click.option("--output-dir", default="./output", help="Default: ./output")
@click.option("--cache-dir", default="./cache", help="Default: ./cache")
@click.option("--no-download", is_flag=True, help="Use existing cache only")
@click.option(
    "--quality",
    default=85,
    type=click.IntRange(1, 100),
    help="JPEG quality 1-100 (default: 85)",
)
def build(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
    layer: tuple[str, ...],
    exporter: str | None,
    bounds: str | None,
    zoom: str | None,
    output_dir: str,
    cache_dir: str,
    no_download: bool,
    quality: int,
) -> None:
    """Build one or more layers into output files."""
    click.echo("Build command not yet implemented.")


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
@click.option(
    "--layer", multiple=True, help="Layer ID to download (repeatable; default: all)"
)
@click.option("--cache-dir", default="./cache", help="Default: ./cache")
def download(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
    layer: tuple[str, ...],
    cache_dir: str,
) -> None:
    """Download source data only (no build)."""
    click.echo("Download command not yet implemented.")


@main.command()
@click.argument("img_file", type=click.Path(exists=True))
@click.option("--output-dir", default="./output", help="Default: ./output")
def split(img_file: str, output_dir: str) -> None:
    """Split an oversized .img into region files."""
    click.echo("Split command not yet implemented.")


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
def list_layers(
    sources: tuple[str, ...],
    layers: tuple[str, ...],
) -> None:
    """List all layers from the provided config files."""
    click.echo("List command not yet implemented.")
