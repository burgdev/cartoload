from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from pystac_client import Client
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)


class GeoTIFFDownloader:
    """
    Downloads GeoTIFF files from STAC API endpoints.

    Queries a STAC catalog for items matching a product ID and bounding box,
    then downloads GeoTIFF assets to a local cache directory.
    """

    def __init__(self, cache_dir: str | Path):
        """
        Initialize the GeoTIFF downloader.

        Args:
            cache_dir: Root directory for caching downloaded files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run(self, source_config: SourceConfig, layer_config: LayerConfig) -> list[Path]:
        """
        Download all GeoTIFF files for a layer from a STAC source.

        Args:
            source_config: Source configuration (must be type='geotiff')
            layer_config: Layer configuration with product ID and bounds

        Returns:
            List of paths to downloaded (or cached) GeoTIFF files

        Raises:
            ValueError: If source type is not 'geotiff' or required fields are missing
            Exception: If STAC query or download fails
        """
        # Validate source type
        if source_config.type != "geotiff":
            raise ValueError(
                f"GeoTIFFDownloader requires source type 'geotiff', "
                f"got '{source_config.type}'"
            )

        # Validate required fields
        if not source_config.stac_url:
            raise ValueError(
                f"Source '{source_config.id}' missing required field 'stac_url'"
            )

        if not layer_config.geotiff_product:
            raise ValueError(
                f"Layer '{layer_config.id}' missing required field 'geotiff_product'"
            )

        # Extract bounds (use layer bounds if available, otherwise fail)
        if layer_config.bounds:
            bbox = [
                layer_config.bounds["west"],
                layer_config.bounds["south"],
                layer_config.bounds["east"],
                layer_config.bounds["north"],
            ]
        else:
            raise ValueError(
                f"Layer '{layer_config.id}' missing required 'bounds' for GeoTIFF download"
            )

        logger.info(
            f"Downloading GeoTIFFs for layer '{layer_config.id}' from "
            f"product '{layer_config.geotiff_product}'"
        )

        # Query STAC API
        items = self.query(source_config.stac_url, layer_config.geotiff_product, bbox)

        if not items:
            logger.warning(
                f"No STAC items found for product '{layer_config.geotiff_product}' "
                f"in bbox {bbox}"
            )
            return []

        logger.info(f"Found {len(items)} STAC item(s) to download")

        # Download all items
        downloaded_files = []
        skipped_count = 0

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
            for item_id, asset_url, expected_size in items:
                # Determine cache path
                cache_path = self._get_cache_path(
                    source_config.id, layer_config.geotiff_product, item_id
                )

                # Check if already cached
                if self._is_cached(cache_path, expected_size):
                    logger.debug(f"Skipping cached file: {cache_path.name}")
                    downloaded_files.append(cache_path)
                    skipped_count += 1
                    continue

                # Download
                self.download(asset_url, cache_path, expected_size, progress)
                downloaded_files.append(cache_path)

        logger.info(
            f"Download complete: {len(downloaded_files)} total files "
            f"({len(downloaded_files) - skipped_count} downloaded, {skipped_count} cached)"
        )

        return downloaded_files

    def query(
        self, stac_url: str, product_id: str, bbox: list[float]
    ) -> list[tuple[str, str, int | None]]:
        """
        Query STAC API for GeoTIFF items.

        Args:
            stac_url: STAC API endpoint URL
            product_id: Product/collection identifier
            bbox: Bounding box as [west, south, east, north]

        Returns:
            List of tuples: (item_id, asset_url, expected_size_bytes)

        Raises:
            Exception: If STAC connection or query fails
        """
        try:
            catalog = Client.open(stac_url)
        except Exception as e:
            raise Exception(
                f"Failed to connect to STAC catalog at {stac_url}: {e}"
            ) from e

        try:
            search = catalog.search(collections=[product_id], bbox=bbox)
            items_list = list(search.items())
        except Exception as e:
            raise Exception(
                f"STAC search failed for collection '{product_id}': {e}"
            ) from e

        if not items_list:
            return []

        results = []
        for item in items_list:
            # Find GeoTIFF asset
            geotiff_asset = None

            # Try common asset keys
            for key in ["geotiff", "data", "image", "cog"]:
                if key in item.assets:
                    geotiff_asset = item.assets[key]
                    break

            # Fallback: find any asset with image/tiff media type
            if not geotiff_asset:
                for asset in item.assets.values():
                    if asset.media_type in [
                        "image/tiff",
                        "image/tiff; application=geotiff",
                        "application/geo+tiff",
                    ]:
                        geotiff_asset = asset
                        break

            if not geotiff_asset:
                logger.warning(
                    f"No GeoTIFF asset found in STAC item '{item.id}', skipping"
                )
                continue

            asset_url = geotiff_asset.href
            expected_size = (
                getattr(geotiff_asset.extra_fields, "file:size", None) or None
            )

            results.append((item.id, asset_url, expected_size))

        return results

    def download(
        self,
        asset_url: str,
        dest_path: Path,
        expected_size: int | None = None,
        progress: Progress | None = None,
    ) -> None:
        """
        Download a GeoTIFF file from a URL to a local path.

        Args:
            asset_url: URL of the GeoTIFF asset
            dest_path: Local file path to save the file
            expected_size: Expected file size in bytes (for validation)
            progress: Optional Rich Progress instance for progress bar

        Raises:
            Exception: If download fails or size validation fails
        """
        # Create parent directory
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Start download
        try:
            response = requests.get(asset_url, stream=True, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to download {asset_url}: {e}") from e

        # Get content length
        content_length = response.headers.get("Content-Length")
        total_size = int(content_length) if content_length else expected_size

        # Create progress task if progress bar is provided
        task_id = None
        if progress:
            task_id = progress.add_task(
                "download", filename=dest_path.name, total=total_size
            )

        # Download in chunks
        chunk_size = 1024 * 1024  # 1 MB
        downloaded_size = 0

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, advance=len(chunk))

        # Verify file size
        actual_size = dest_path.stat().st_size

        if expected_size and actual_size != expected_size:
            dest_path.unlink()  # Delete incomplete file
            raise Exception(
                f"Downloaded file size mismatch: expected {expected_size} bytes, "
                f"got {actual_size} bytes. Deleted incomplete file."
            )

        if total_size and actual_size != total_size:
            dest_path.unlink()
            raise Exception(
                f"Downloaded file size mismatch: expected {total_size} bytes, "
                f"got {actual_size} bytes. Deleted incomplete file."
            )

        logger.debug(f"Downloaded {dest_path.name} ({actual_size:,} bytes)")

    def _get_cache_path(self, source_id: str, product_id: str, item_id: str) -> Path:
        """
        Generate cache file path for a STAC item.

        Args:
            source_id: Source configuration ID
            product_id: Product/collection ID
            item_id: STAC item ID

        Returns:
            Path to cache file
        """
        # Sanitize item_id for filesystem
        safe_item_id = item_id.replace("/", "_").replace("\\", "_")

        return self.cache_dir / source_id / product_id / f"{safe_item_id}.tif"

    def _is_cached(self, cache_path: Path, expected_size: int | None) -> bool:
        """
        Check if a file is already cached and valid.

        Args:
            cache_path: Path to cached file
            expected_size: Expected file size in bytes (optional)

        Returns:
            True if file exists and is valid, False otherwise
        """
        if not cache_path.exists():
            return False

        actual_size = cache_path.stat().st_size

        # File must have non-zero size
        if actual_size == 0:
            logger.warning(f"Cached file is empty, will re-download: {cache_path}")
            cache_path.unlink()
            return False

        # If expected size is known, verify it matches
        if expected_size and actual_size < expected_size:
            logger.warning(
                f"Cached file is incomplete ({actual_size}/{expected_size} bytes), "
                f"will re-download: {cache_path}"
            )
            cache_path.unlink()
            return False

        return True
