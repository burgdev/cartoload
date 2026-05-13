"""GeoTIFF path resolution: collects GeoTIFF files from local paths and remote URLs."""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

logger = logging.getLogger(__name__)


def collect_geotiff_files(
    urls: list[str],
    cache_dir: Path,
    config_dir: Path | None = None,
) -> list[Path]:
    """Resolve a list of URLs/paths into a list of GeoTIFF file paths.

    Each entry in ``urls`` can be:
    - A local directory path (relative to config_dir or absolute) — scanned recursively
    - A local file path (relative to config_dir or absolute) — validated and returned
    - An HTTP/HTTPS URL — downloaded to cache_dir

    Args:
        urls: List of URL/path strings from source config
        cache_dir: Directory for caching remote downloads
        config_dir: Base directory for resolving relative paths (source config file dir)

    Returns:
        List of absolute paths to GeoTIFF files

    Raises:
        ValueError: If a local path does not exist
        FileNotFoundError: If no GeoTIFF files are found
    """
    files: list[Path] = []

    for entry in urls:
        if entry.startswith(("http://", "https://")):
            files.extend(_collect_remote(entry, cache_dir))
        else:
            files.extend(_collect_local(entry, config_dir))

    if not files:
        raise FileNotFoundError(f"No GeoTIFF files found from urls: {urls}")

    logger.info("Collected %d GeoTIFF file(s)", len(files))
    return files


def _resolve_path(raw: str, config_dir: Path | None) -> Path:
    """Resolve a path string relative to the config file directory."""
    p = Path(raw)
    if p.is_absolute():
        return p
    if config_dir is not None:
        return (config_dir / p).resolve()
    return p.resolve()


def _collect_local(raw_path: str, config_dir: Path | None) -> list[Path]:
    """Collect GeoTIFF files from a local path (file or directory)."""
    path = _resolve_path(raw_path, config_dir)

    if not path.exists():
        raise ValueError(f"GeoTIFF path does not exist: {path}")

    if path.is_dir():
        tif_files = sorted(
            p
            for p in path.rglob("*")
            if p.is_file() and p.suffix.lstrip(".") in ("tif", "tiff")
        )
        if not tif_files:
            logger.warning("No GeoTIFF files found in directory: %s", path)
        return tif_files

    if path.is_file():
        if path.suffix.lstrip(".") not in ("tif", "tiff"):
            logger.warning(
                "File does not have .tif/.tiff extension, including anyway: %s", path
            )
        return [path]

    return []


def _collect_remote(url: str, cache_dir: Path) -> list[Path]:
    """Download a remote GeoTIFF URL to cache and return the cached path."""
    # Derive filename from URL
    filename = url.rsplit("/", 1)[-1]
    if not filename:
        filename = "downloaded.tif"
    if not filename.endswith((".tif", ".tiff")):
        filename += ".tif"

    cache_path = cache_dir / filename

    if cache_path.exists() and cache_path.stat().st_size > 0:
        logger.debug("Using cached file: %s", cache_path.name)
        return [cache_path]

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading %s", url)
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception(f"Failed to download {url}: {e}") from e

    total_size = response.headers.get("Content-Length")

    with Progress(
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
    ) as progress:
        task_id = progress.add_task(
            "download",
            filename=cache_path.name,
            total=int(total_size) if total_size else None,
        )
        with open(cache_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    progress.update(task_id, advance=len(chunk))

    logger.info(
        "Downloaded %s (%s bytes)", cache_path.name, f"{cache_path.stat().st_size:,}"
    )
    return [cache_path]
