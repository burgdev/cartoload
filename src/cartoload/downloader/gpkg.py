"""Download GeoPackage files from STAC endpoints.

Queries a STAC collection for items matching a bounding box,
downloads ``.gpkg.zip`` assets, extracts the GeoPackage, and caches
the result for reuse.
"""

from __future__ import annotations

import json
import logging
import zipfile
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

from cartoload.downloader.cache_key import migrate_cache_key, url_to_cache_key
from cartoload.downloader.stac_query import query_stac_collection

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)

# Media types that indicate a GPKG asset
_GPKG_MEDIA_TYPES = {
    "application/x.geopackage+zip",
    "application/geopackage+zip",
}

# Asset keys to try (in priority order) when looking for GPKG data
_GPKG_ASSET_KEYS = ["gpkg", "geopackage", "data"]


def _find_gpkg_asset(
    assets: dict,
    asset_filter: dict[str, str] | None = None,
) -> str | None:
    """Find the best GPKG asset from a STAC item's assets dict.

    Tries known asset keys first, then falls back to checking media types
    and file extensions.  If ``asset_filter`` is provided, only assets
    matching all filter key-value pairs are considered.

    Returns the asset href, or None if no GPKG asset is found.
    """
    candidates: list[tuple[str, dict]] = []

    # Check known keys
    for key in _GPKG_ASSET_KEYS:
        if key in assets:
            candidates.append((key, assets[key]))

    # If no known keys matched, check by media type
    if not candidates:
        for key, asset in assets.items():
            media_type = asset.get("type", "")
            if media_type in _GPKG_MEDIA_TYPES:
                candidates.append((key, asset))

    # Last resort: check href for .gpkg.zip extension
    if not candidates:
        for key, asset in assets.items():
            href = asset.get("href", "")
            if href and href.lower().endswith(".gpkg.zip"):
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
        asset_keys = [key for key, _ in candidates]
        raise ValueError(
            f"Multiple GPKG assets found ({asset_keys}) but no "
            f"asset_filter configured. Add an 'asset_filter' to your "
            f"source defaults or layer source_args to select one."
        )

    return candidates[0][1].get("href")


def _extract_gpkg_from_zip(
    zip_path: Path, dest_dir: Path, item_filter: str | None = None
) -> Path:
    """Extract a .gpkg file from a zip archive.

    If ``item_filter`` is provided (a regex pattern), only .gpkg filenames
    matching the pattern are considered.  Among matching files, the first
    (alphabetically) is extracted.

    Returns the path to the extracted .gpkg file.

    Raises:
        ValueError: If no matching .gpkg file is found in the archive.
    """
    import re

    with zipfile.ZipFile(zip_path, "r") as zf:
        gpkg_names = [n for n in zf.namelist() if n.lower().endswith(".gpkg")]

        if not gpkg_names:
            raise ValueError(
                f"No .gpkg file found in archive {zip_path.name}. "
                f"Archive contents: {zf.namelist()[:20]}"
            )

        # Apply item_filter regex if provided
        if item_filter:
            pattern = re.compile(item_filter)
            filtered = [n for n in gpkg_names if pattern.search(Path(n).name)]
            if not filtered:
                raise ValueError(
                    f"No .gpkg file matching filter '{item_filter}' in archive "
                    f"{zip_path.name}. Available: {[Path(n).name for n in gpkg_names]}"
                )
            gpkg_names = filtered

        if len(gpkg_names) > 1:
            logger.warning(
                "Multiple .gpkg files in %s: %s. Using first: %s",
                zip_path.name,
                [Path(n).name for n in gpkg_names],
                Path(gpkg_names[0]).name,
            )

        # Extract the first .gpkg file (flatten to dest_dir)
        gpkg_name = gpkg_names[0]
        gpkg_basename = Path(gpkg_name).name
        target_path = dest_dir / gpkg_basename

        # Avoid re-extraction if already present
        if target_path.exists():
            logger.debug("Extracted GPKG already exists: %s", target_path)
            return target_path

        with zf.open(gpkg_name) as src, open(target_path, "wb") as dst:
            import shutil

            shutil.copyfileobj(src, dst)

        logger.info("Extracted %s from %s", gpkg_basename, zip_path.name)
        return target_path


def _strip_etag_quotes(etag: str) -> str:
    """Strip surrounding double quotes from an ETag value."""
    if etag.startswith('"') and etag.endswith('"'):
        return etag[1:-1]
    return etag


class GPKGDownloader:
    """Downloads GeoPackage assets from STAC API endpoints.

    Queries a STAC collection for items matching a bounding box,
    downloads ``.gpkg.zip`` assets, extracts the GeoPackage, and
    caches the result alongside a metadata sidecar.
    """

    def __init__(
        self,
        cache_dir: str | Path,
        max_workers: int = 4,
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
        item_filter: str | None = None,
    ) -> list[Path]:
        """Download all GPKG assets for a layer from a STAC source.

        Args:
            source_config: Source configuration (must be type='gpkg')
            layer_config: Layer configuration with bounds
            resolved_url: Fully resolved STAC collection URL
            collection_id: STAC collection ID (from source_args.layer)
            asset_filter: Optional key-value pairs to match against asset properties
            item_filter: Optional regex to select which .gpkg file to extract
                from multi-gpkg archives

        Returns:
            List of paths to extracted .gpkg files
        """
        if source_config.type != "gpkg":
            raise ValueError(
                f"GPKGDownloader requires source type 'gpkg', "
                f"got '{source_config.type}'"
            )

        if not layer_config.bounds:
            raise ValueError(
                f"Layer '{layer_config.id}' missing required 'bounds' for GPKG download"
            )

        bbox = [
            layer_config.bounds["west"],
            layer_config.bounds["south"],
            layer_config.bounds["east"],
            layer_config.bounds["north"],
        ]

        logger.info(
            "Downloading GPKG for layer '%s' from collection '%s'",
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

        gpkg_paths: list[Path] = []

        for item_id, asset_url, _expected_size in items:
            cache_dir = self._get_cache_dir(
                source_config.id, resolved_url, item_id, asset_filter
            )
            zip_path = cache_dir / f"{item_id}.zip"
            gpkg_path_file = cache_dir / f"{item_id}.gpkg"
            meta_path = cache_dir / f"{item_id}.json"

            # Check cache
            if self._is_cached(zip_path, gpkg_path_file, meta_path):
                if not self._offline:
                    freshness = self._check_freshness(asset_url, meta_path)
                    if freshness is False:
                        logger.info("Re-downloading stale GPKG: %s", zip_path.name)
                    else:
                        logger.debug("Using cached GPKG: %s", zip_path.name)
                        gpkg_paths.append(gpkg_path_file)
                        continue
                else:
                    logger.debug("Offline mode, using cached: %s", zip_path.name)
                    gpkg_paths.append(gpkg_path_file)
                    continue

            # Download
            try:
                if not self._offline:
                    self._download(asset_url, zip_path)
                    self._write_metadata(meta_path, asset_url)

                # Extract
                extracted = _extract_gpkg_from_zip(zip_path, cache_dir, item_filter)

                # Rename to canonical name if different
                if extracted != gpkg_path_file:
                    if gpkg_path_file.exists():
                        gpkg_path_file.unlink()
                    extracted.rename(gpkg_path_file)

                gpkg_paths.append(gpkg_path_file)
            except Exception as e:
                logger.error(
                    "Failed to download/extract GPKG item '%s': %s", item_id, e
                )

        logger.info("GPKG download complete: %d file(s)", len(gpkg_paths))
        return gpkg_paths

    def query(
        self,
        collection_url: str,
        collection_id: str,
        bbox: list[float],
        asset_filter: dict[str, str] | None = None,
    ) -> list[tuple[str, str, int | None]]:
        """Query STAC collection for GPKG items matching a bounding box.

        Returns:
            List of tuples: (item_id, asset_url, expected_size_bytes)
        """
        return query_stac_collection(
            collection_url,
            bbox,
            _find_gpkg_asset,
            asset_filter=asset_filter,
            collection_id=collection_id,
            asset_label="GPKG",
        )

    def _download(self, asset_url: str, dest_path: Path) -> None:
        """Download a file from a URL to a local path."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(asset_url, stream=True, timeout=60)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to download {asset_url}: {e}") from e

        total_size = response.headers.get("Content-Length")
        total = int(total_size) if total_size else None

        chunk_size = 1024 * 1024  # 1 MB

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
            task_id = progress.add_task(
                "download", filename=dest_path.name, total=total
            )
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))

        logger.debug("Downloaded %s", dest_path.name)

    def _get_cache_dir(
        self,
        source_id: str,
        collection_url: str,
        item_id: str,
        asset_filter: dict[str, str] | None = None,
    ) -> Path:
        """Generate cache directory for a STAC item."""
        safe_item_id = item_id.replace("/", "_").replace("\\", "_")
        extra = ""
        if asset_filter:
            extra = ",".join(f"{k}={v}" for k, v in sorted(asset_filter.items()))
        cache_key = url_to_cache_key(collection_url, extra=extra)
        base = self.cache_dir / source_id
        migrate_cache_key(base, cache_key)
        return base / cache_key / safe_item_id

    def _is_cached(self, zip_path: Path, gpkg_path: Path, meta_path: Path) -> bool:
        """Check if a GPKG is already cached and valid."""
        if not zip_path.exists() or not gpkg_path.exists():
            return False
        if not meta_path.exists():
            return False
        if zip_path.stat().st_size == 0 or gpkg_path.stat().st_size == 0:
            return False
        return True

    def _check_freshness(self, asset_url: str, meta_path: Path) -> bool | None:
        """Check if a cached GPKG is still fresh via HTTP HEAD.

        Returns True if fresh, False if stale, None if undetermined.
        """
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
            return None

        if resp.status_code == 405 or not resp.ok:
            return None

        remote_etag = _strip_etag_quotes(resp.headers.get("ETag", ""))
        remote_last_modified = resp.headers.get("Last-Modified", "")

        if cached_etag and remote_etag:
            return cached_etag == remote_etag

        if cached_last_modified and remote_last_modified:
            return cached_last_modified == remote_last_modified

        return None

    def _write_metadata(self, meta_path: Path, asset_url: str) -> None:
        """Write metadata JSON sidecar with ETag/Last-Modified."""
        from datetime import datetime, timezone

        meta: dict = {
            "url": asset_url,
            "download_date": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = requests.head(asset_url, timeout=10, allow_redirects=True)
            if resp.ok:
                meta["etag"] = _strip_etag_quotes(resp.headers.get("ETag", ""))
                meta["last_modified"] = resp.headers.get("Last-Modified", "")
        except requests.RequestException:
            pass

        meta_path.write_text(json.dumps(meta, indent=2))
