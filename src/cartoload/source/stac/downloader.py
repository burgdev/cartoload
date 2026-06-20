from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from cartoload.source.cache_key import migrate_cache_key, url_to_cache_key
from cartoload.source.stac.query import query_stac_collection

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

    def __init__(
        self,
        cache_dir: str | Path,
        max_workers: int = 6,
        *,
        offline: bool = False,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._max_workers = max_workers
        self._offline = offline

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
        if source_config.type != "geotiff":
            raise ValueError(
                f"STACDownloader requires source type 'geotiff', "
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

        # Phase 1: check cache/freshness for all items (sequential — fast HEAD requests)
        to_download: list[tuple[str, str, int | None, Path]] = []
        for item_id, asset_url, expected_size in items:
            cache_path = self._get_cache_path(
                source_config.id, resolved_url, item_id, asset_filter
            )

            if self._is_cached(cache_path, expected_size):
                if not self._offline:
                    freshness = self._check_freshness(asset_url, cache_path)
                    if freshness is False:
                        logger.info("Re-downloading stale file: %s", cache_path.name)
                        to_download.append(
                            (item_id, asset_url, expected_size, cache_path)
                        )
                        continue
                logger.debug("Skipping cached file: %s", cache_path.name)
                downloaded_files.append(cache_path)
                skipped_count += 1
                continue

            to_download.append((item_id, asset_url, expected_size, cache_path))

        # Phase 2: download in parallel
        if to_download:
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
                transient=True,
            ) as progress:
                with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                    future_to_item = {
                        executor.submit(
                            self._download_item,
                            asset_url,
                            cache_path,
                            expected_size,
                            progress,
                        ): (item_id, cache_path)
                        for item_id, asset_url, expected_size, cache_path in to_download
                    }
                    for future in as_completed(future_to_item):
                        item_id, cache_path = future_to_item[future]
                        try:
                            future.result()
                            downloaded_files.append(cache_path)
                        except Exception as e:
                            logger.error(
                                "Failed to download STAC item '%s': %s", item_id, e
                            )

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

        Args:
            collection_url: STAC collection endpoint URL
            collection_id: Collection identifier (used for logging)
            bbox: Bounding box as [west, south, east, north]
            asset_filter: Optional key-value pairs to match against asset properties

        Returns:
            List of tuples: (item_id, asset_url, expected_size_bytes)
        """
        return query_stac_collection(
            collection_url,
            bbox,
            _find_geotiff_asset,
            asset_filter=asset_filter,
            collection_id=collection_id,
            asset_label="GeoTIFF",
        )

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

    def _download_item(
        self,
        asset_url: str,
        cache_path: Path,
        expected_size: int | None,
        progress: Progress,
    ) -> None:
        """Download a single STAC item and write metadata.

        Used as a worker callable for ThreadPoolExecutor.
        """
        self.download(asset_url, cache_path, expected_size, progress)
        self._write_metadata(cache_path, asset_url)

    def _get_cache_path(
        self,
        source_id: str,
        collection_url: str,
        item_id: str,
        asset_filter: dict[str, str] | None = None,
    ) -> Path:
        """Generate cache file path for a STAC item.

        Uses the same human-readable cache-key strategy as WMTS:
        url_to_cache_key produces a filesystem-safe directory name from
        the URL path, with the asset filter appended as extra.
        """
        safe_item_id = item_id.replace("/", "_").replace("\\", "_")
        # Build extra string from asset filter
        extra = ""
        if asset_filter:
            extra = ",".join(f"{k}={v}" for k, v in sorted(asset_filter.items()))
        cache_key = url_to_cache_key(collection_url, extra=extra)
        base = self.cache_dir / source_id
        migrate_cache_key(base, cache_key)
        return base / cache_key / f"{safe_item_id}.tif"

    def _is_cached(self, cache_path: Path, expected_size: int | None) -> bool:
        """Check if a file is already cached and valid.

        Checks for the original .tif file first. If the original was cleaned
        up after pre-warping, checks for the _4326.tif warped version and
        the .json metadata sidecar.
        """
        if cache_path.exists():
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

            # Require metadata sidecar — without it the download was incomplete
            # (e.g. aborted before _write_metadata ran).
            meta_path = cache_path.parent / f"{cache_path.stem}.json"
            if not meta_path.exists():
                logger.debug(
                    "Cached file has no metadata sidecar, will re-download: %s",
                    cache_path.name,
                )
                cache_path.unlink()
                return False

            return True

        # Original may have been cleaned up after pre-warping.
        # Check if the warped version, metadata, and warp completion marker exist.
        warped_path = cache_path.parent / f"{cache_path.stem}_4326.tif"
        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        warp_marker = cache_path.parent / f"{cache_path.stem}_4326.json"
        if warped_path.exists() and meta_path.exists() and warp_marker.exists():
            logger.debug(
                "Original cleaned up, using warped cache: %s", warped_path.name
            )
            return True

        return False

    def _check_freshness(self, asset_url: str, cache_path: Path) -> bool | None:
        """Check if a cached STAC item is still fresh via HTTP HEAD.

        Returns:
            True if fresh (no re-download needed)
            False if stale (should re-download)
            None if freshness cannot be determined (fall back to existence check)
        """
        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        if not meta_path.exists():
            return None

        try:
            cached_meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        cached_etag = _strip_etag_quotes(cached_meta.get("etag", ""))
        cached_last_modified = cached_meta.get("last_modified", "")

        try:
            resp = requests.head(asset_url, timeout=10, allow_redirects=True)
        except requests.RequestException:
            logger.debug(
                "HEAD request failed for %s, skipping freshness check", asset_url
            )
            return None

        if resp.status_code == 405:
            logger.debug(
                "HEAD not supported for %s, skipping freshness check", asset_url
            )
            return None

        if not resp.ok:
            logger.debug(
                "HEAD returned %d for %s, skipping freshness check",
                resp.status_code,
                asset_url,
            )
            return None

        remote_etag = _strip_etag_quotes(resp.headers.get("ETag", ""))
        remote_last_modified = resp.headers.get("Last-Modified", "")

        if cached_etag and remote_etag:
            if cached_etag == remote_etag:
                logger.debug("ETag match for %s, item is fresh", cache_path.name)
                return True
            else:
                logger.info("ETag mismatch for %s, item is stale", cache_path.name)
                return False

        if cached_last_modified and remote_last_modified:
            if cached_last_modified == remote_last_modified:
                logger.debug(
                    "Last-Modified match for %s, item is fresh", cache_path.name
                )
                return True
            else:
                logger.info(
                    "Last-Modified mismatch for %s, item is stale", cache_path.name
                )
                return False

        # No comparable headers — can't determine freshness
        return None

    def _write_metadata(self, cache_path: Path, asset_url: str) -> None:
        """Write metadata JSON sidecar with ETag/Last-Modified from a HEAD request."""
        from datetime import datetime, timezone

        meta: dict = {
            "item_id": cache_path.stem,
            "url": asset_url,
            "download_date": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = requests.head(asset_url, timeout=10, allow_redirects=True)
            if resp.ok:
                meta["etag"] = _strip_etag_quotes(resp.headers.get("ETag", ""))
                meta["last_modified"] = resp.headers.get("Last-Modified", "")
            else:
                logger.debug(
                    "HEAD returned %d, storing metadata without cache headers",
                    resp.status_code,
                )
        except requests.RequestException:
            logger.debug(
                "HEAD failed for %s, storing metadata without cache headers", asset_url
            )

        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        logger.debug("Wrote metadata: %s", meta_path.name)


def _strip_etag_quotes(etag: str) -> str:
    """Strip surrounding double quotes from an ETag value.

    HTTP ETags are often quoted (e.g. ``"abc123"``).  Stripping the
    quotes ensures consistent storage and comparison regardless of
    whether the server includes them.
    """
    if etag.startswith('"') and etag.endswith('"'):
        return etag[1:-1]
    return etag


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
