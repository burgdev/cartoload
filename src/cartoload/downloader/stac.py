from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import requests
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

# Media types that indicate a GeoTIFF asset
_GEOTIFF_MEDIA_TYPES = {
    "image/tiff",
    "image/tiff; application=geotiff",
    "image/tiff; application=geotiff; profile=cloud-optimized",
    "application/geo+tiff",
}

# Asset keys to try (in priority order) when looking for GeoTIFF data
_GEOTIFF_ASSET_KEYS = ["geotiff", "data", "image", "cog"]


class STACDownloader:
    """Downloads GeoTIFF assets from STAC API endpoints.

    Queries a STAC collection for items matching a bounding box,
    then downloads GeoTIFF assets to a local cache directory.

    The STAC URL and collection ID are derived from the source config's
    ``urls`` (resolved with ``${layer}`` substitution) and ``source_args.layer``.
    """

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        resolved_url: str,
        collection_id: str,
        asset_filter: dict[str, str] | None = None,
    ) -> list[Path]:
        """Download all GeoTIFF assets for a layer from a STAC source.

        Args:
            source_config: Source configuration (must be type='stac')
            layer_config: Layer configuration with bounds
            resolved_url: Fully resolved STAC collection URL
            collection_id: STAC collection ID (from source_args.layer)
            asset_filter: Optional key-value pairs to match against asset properties

        Returns:
            List of paths to downloaded (or cached) GeoTIFF files
        """
        if source_config.type != "stac":
            raise ValueError(
                f"STACDownloader requires source type 'stac', "
                f"got '{source_config.type}'"
            )

        if not layer_config.bounds:
            raise ValueError(
                f"Layer '{layer_config.id}' missing required 'bounds' for STAC download"
            )

        bbox = [
            layer_config.bounds["west"],
            layer_config.bounds["south"],
            layer_config.bounds["east"],
            layer_config.bounds["north"],
        ]

        logger.info(
            "Downloading GeoTIFFs for layer '%s' from collection '%s'",
            layer_config.id,
            collection_id,
        )

        items = self.query(resolved_url, collection_id, bbox, asset_filter)

        if not items:
            logger.warning(
                "No STAC items found for collection '%s' in bbox %s",
                collection_id,
                bbox,
            )
            return []

        logger.info("Found %d STAC item(s) to download", len(items))

        downloaded_files: list[Path] = []
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
                cache_path = self._get_cache_path(
                    source_config.id, resolved_url, item_id, asset_filter
                )

                if self._is_cached(cache_path, expected_size):
                    logger.debug("Skipping cached file: %s", cache_path.name)
                    downloaded_files.append(cache_path)
                    skipped_count += 1
                    continue

                self.download(asset_url, cache_path, expected_size, progress)
                downloaded_files.append(cache_path)

        logger.info(
            "Download complete: %d total files (%d downloaded, %d cached)",
            len(downloaded_files),
            len(downloaded_files) - skipped_count,
            skipped_count,
        )

        return downloaded_files

    def query(
        self,
        collection_url: str,
        collection_id: str,
        bbox: list[float],
        asset_filter: dict[str, str] | None = None,
    ) -> list[tuple[str, str, int | None]]:
        """Query STAC collection for GeoTIFF items matching a bounding box.

        Works directly with the collection URL (e.g.
        ``https://example.com/api/v1/collections/{id}``) by fetching
        items via the ``/items`` sub-endpoint with a bbox filter.
        No ``pystac_client`` dependency — uses plain HTTP requests.

        Args:
            collection_url: STAC collection endpoint URL
            collection_id: Collection identifier (used for logging)
            bbox: Bounding box as [west, south, east, north]
            asset_filter: Optional key-value pairs to match against asset properties

        Returns:
            List of tuples: (item_id, asset_url, expected_size_bytes)
        """
        items_url = collection_url.rstrip("/") + "/items"
        params: dict[str, str] = {
            "bbox": ",".join(str(v) for v in bbox),
            "limit": "500",
        }

        try:
            response = requests.get(items_url, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to query STAC items at {items_url}: {e}") from e

        data = response.json()
        features = data.get("features", [])

        if not features:
            return []

        results: list[tuple[str, str, int | None]] = []
        for feature in features:
            item_id = feature.get("id", "unknown")
            assets = feature.get("assets", {})

            geotiff_url = _find_geotiff_asset(assets, asset_filter)
            if geotiff_url is None:
                if asset_filter:
                    logger.warning(
                        "No GeoTIFF asset matching filter %s in STAC item '%s', skipping",
                        asset_filter,
                        item_id,
                    )
                else:
                    logger.warning(
                        "No GeoTIFF asset found in STAC item '%s', skipping",
                        item_id,
                    )
                continue

            results.append((item_id, geotiff_url, None))

        return results

    def download(
        self,
        asset_url: str,
        dest_path: Path,
        expected_size: int | None = None,
        progress: Progress | None = None,
    ) -> None:
        """Download a GeoTIFF file from a URL to a local path."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(asset_url, stream=True, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to download {asset_url}: {e}") from e

        content_length = response.headers.get("Content-Length")
        total_size = int(content_length) if content_length else expected_size

        task_id = None
        if progress:
            task_id = progress.add_task(
                "download", filename=dest_path.name, total=total_size
            )

        chunk_size = 1024 * 1024  # 1 MB

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, advance=len(chunk))

        actual_size = dest_path.stat().st_size

        if expected_size and actual_size < expected_size:
            dest_path.unlink()
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

        logger.debug("Downloaded %s (%s bytes)", dest_path.name, f"{actual_size:,}")

    def _get_cache_path(
        self,
        source_id: str,
        collection_url: str,
        item_id: str,
        asset_filter: dict[str, str] | None = None,
    ) -> Path:
        """Generate cache file path for a STAC item.

        Uses the same cache-key strategy as WMTS: a SHA-256 hash of
        the resolved URL (with asset_filter appended) produces a short
        directory name that uniquely identifies this source+filter
        combination.
        """
        safe_item_id = item_id.replace("/", "_").replace("\\", "_")
        # Build the cache key from URL + asset_filter, matching WMTS pattern
        key_input = collection_url
        if asset_filter:
            filter_str = ",".join(f"{k}={v}" for k, v in sorted(asset_filter.items()))
            key_input = f"{key_input}|{filter_str}"
        cache_key = hashlib.sha256(key_input.encode()).hexdigest()[:12]
        base = self.cache_dir / source_id / cache_key
        return base / f"{safe_item_id}.tif"

    def _is_cached(self, cache_path: Path, expected_size: int | None) -> bool:
        """Check if a file is already cached and valid."""
        if not cache_path.exists():
            return False

        actual_size = cache_path.stat().st_size

        if actual_size == 0:
            logger.warning("Cached file is empty, will re-download: %s", cache_path)
            cache_path.unlink()
            return False

        if expected_size and actual_size < expected_size:
            logger.warning(
                "Cached file is incomplete (%d/%d bytes), will re-download: %s",
                actual_size,
                expected_size,
                cache_path,
            )
            cache_path.unlink()
            return False

        return True


def _find_geotiff_asset(
    assets: dict,
    asset_filter: dict[str, str] | None = None,
) -> str | None:
    """Find the best GeoTIFF asset from a STAC item's assets dict.

    Tries known asset keys first, then falls back to checking media types.
    If ``asset_filter`` is provided, only assets matching all filter key-value
    pairs (against asset properties) are considered.

    Returns the asset href, or None if no GeoTIFF asset is found.
    """
    # Collect all GeoTIFF candidates: (key, asset) pairs
    candidates: list[tuple[str, dict]] = []

    # Check known keys
    for key in _GEOTIFF_ASSET_KEYS:
        if key in assets:
            candidates.append((key, assets[key]))

    # If no known keys matched, check by media type
    if not candidates:
        for key, asset in assets.items():
            media_type = asset.get("type", "")
            if media_type in _GEOTIFF_MEDIA_TYPES:
                candidates.append((key, asset))

    # Last resort: check href for .tif/.tiff extension
    if not candidates:
        for key, asset in assets.items():
            href = asset.get("href", "")
            if href and href.rsplit(".", 1)[-1].lower() in ("tif", "tiff"):
                candidates.append((key, asset))

    if not candidates:
        return None

    # Apply asset_filter if provided
    if asset_filter:
        filtered = [
            (key, asset)
            for key, asset in candidates
            if all(str(asset.get(k, "")) == str(v) for k, v in asset_filter.items())
        ]
        if not filtered:
            return None
        candidates = filtered
    elif len(candidates) > 1:
        # Ambiguous: multiple GeoTIFF assets found with no filter
        asset_keys = [key for key, _ in candidates]
        raise ValueError(
            f"Multiple GeoTIFF assets found ({asset_keys}) but no "
            f"asset_filter configured. Add an 'asset_filter' to your "
            f"source defaults or layer source_args to select one."
        )

    return candidates[0][1].get("href")
