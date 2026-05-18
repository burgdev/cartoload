"""StacSource — download data from STAC collection endpoints.

Handles both GeoTIFF and GPKG formats. The layer's ``format`` field
determines which asset type to look for and how to process the download.

For ``format: geotiff``, downloads .tif files directly.
For ``format: gpkg``, downloads .gpkg.zip files, extracts the GeoPackage,
and caches the result.
"""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
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

from cartoload.downloader.cache_key import url_to_cache_key
from cartoload.downloader.source import Source, register_source
from cartoload.downloader.stac_query import query_stac_collection
from cartoload.template import expand

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Asset finding: GeoTIFF
# ---------------------------------------------------------------------------

_GEOTIFF_MEDIA_TYPES = {
    "image/tiff",
    "image/tiff; application=geotiff",
    "image/tiff; application=geotiff; profile=cloud-optimized",
    "application/geo+tiff",
}
_GEOTIFF_ASSET_KEYS = ["geotiff", "data", "image", "cog"]

# ---------------------------------------------------------------------------
# Asset finding: GPKG
# ---------------------------------------------------------------------------

_GPKG_MEDIA_TYPES = {
    "application/x.geopackage+zip",
    "application/geopackage+zip",
}
_GPKG_ASSET_KEYS = ["gpkg", "geopackage", "data"]


def _find_geotiff_asset(
    assets: dict,
    asset_filter: dict[str, str] | None = None,
) -> str | None:
    """Find the best GeoTIFF asset from a STAC item's assets dict."""
    candidates: list[tuple[str, dict]] = []

    for key in _GEOTIFF_ASSET_KEYS:
        if key in assets:
            candidates.append((key, assets[key]))

    if not candidates:
        for key, asset in assets.items():
            media_type = asset.get("type", "")
            if media_type in _GEOTIFF_MEDIA_TYPES:
                candidates.append((key, asset))

    if not candidates:
        for key, asset in assets.items():
            href = asset.get("href", "")
            if href and href.rsplit(".", 1)[-1].lower() in ("tif", "tiff"):
                candidates.append((key, asset))

    return _apply_filter(candidates, asset_filter)


def _find_gpkg_asset(
    assets: dict,
    asset_filter: dict[str, str] | None = None,
) -> str | None:
    """Find the best GPKG asset from a STAC item's assets dict."""
    candidates: list[tuple[str, dict]] = []

    for key in _GPKG_ASSET_KEYS:
        if key in assets:
            candidates.append((key, assets[key]))

    if not candidates:
        for key, asset in assets.items():
            media_type = asset.get("type", "")
            if media_type in _GPKG_MEDIA_TYPES:
                candidates.append((key, asset))

    if not candidates:
        for key, asset in assets.items():
            href = asset.get("href", "")
            if href and href.lower().endswith(".gpkg.zip"):
                candidates.append((key, asset))

    return _apply_filter(candidates, asset_filter)


def _apply_filter(
    candidates: list[tuple[str, dict]],
    asset_filter: dict[str, str] | None = None,
) -> str | None:
    """Apply asset_filter to candidates and return the href, or None."""
    if not candidates:
        return None

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
            f"Multiple assets found ({asset_keys}) but no "
            f"asset_filter configured. Add an 'asset_filter' to select one."
        )

    return candidates[0][1].get("href")


# ---------------------------------------------------------------------------
# Asset finder lookup by format
# ---------------------------------------------------------------------------

_ASSET_FINDERS = {
    "geotiff": _find_geotiff_asset,
    "gpkg": _find_gpkg_asset,
}


# ---------------------------------------------------------------------------
# StacSource implementation
# ---------------------------------------------------------------------------


def _strip_etag_quotes(etag: str) -> str:
    if etag.startswith('"') and etag.endswith('"'):
        return etag[1:-1]
    return etag


class StacSource(Source):
    """Download data from STAC collection endpoints.

    Handles both GeoTIFF and GPKG formats. The layer's ``format`` field
    determines which asset finder to use.
    """

    def __init__(self, max_workers: int = 6):
        self._max_workers = max_workers

    @classmethod
    def can_handle(cls, source_config: SourceConfig) -> bool:
        return source_config.type == "stac"

    def download(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
        *,
        offline: bool = False,
        update: bool = False,
        max_age_days: int | None = None,
    ) -> list[Path]:
        if not layer_config.bounds:
            raise ValueError(
                f"Layer '{layer_config.id}' missing required 'bounds' for STAC download"
            )

        fmt = layer_config.format or "geotiff"
        asset_finder = _ASSET_FINDERS.get(fmt)
        if asset_finder is None:
            raise ValueError(
                f"StacSource does not support format '{fmt}'. "
                f"Supported formats: {', '.join(sorted(_ASSET_FINDERS.keys()))}"
            )

        bbox = [
            layer_config.bounds["west"],
            layer_config.bounds["south"],
            layer_config.bounds["east"],
            layer_config.bounds["north"],
        ]

        # Resolve the collection URL by substituting template variables
        resolved_url = self._resolve_url(source_config, layer_config)
        collection_id = layer_config.source_args.get("layer", "")

        # Merge asset_filter: layer config overrides source defaults
        asset_filter = (
            layer_config.asset_filter
            if layer_config.asset_filter is not None
            else source_config.asset_filter
        )

        logger.info(
            "Downloading %s for layer '%s' from collection '%s'",
            fmt.upper(),
            layer_config.id,
            collection_id,
        )

        items = query_stac_collection(
            resolved_url,
            bbox,
            asset_finder,
            asset_filter=asset_filter,
            collection_id=collection_id,
            asset_label=fmt.upper(),
        )

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

        # Phase 1: check cache/freshness
        to_download: list[tuple[str, str, int | None, Path]] = []
        for item_id, asset_url, expected_size in items:
            item_cache_dir = self._get_cache_dir(
                source_config.id, resolved_url, item_id, asset_filter
            )
            cache_path = item_cache_dir / f"{item_id}.{self._file_extension(fmt)}"

            if self._is_item_cached(cache_path, expected_size, fmt):
                should_check = update or max_age_days is not None

                if should_check and not offline:
                    # Age-based check: skip if file is recent enough
                    if max_age_days is not None:
                        if not self._is_older_than(cache_path, max_age_days):
                            logger.debug(
                                "Skipping cached file (age < %d days): %s",
                                max_age_days,
                                cache_path.name,
                            )
                            downloaded_files.append(cache_path)
                            skipped_count += 1
                            continue

                    # ETag/Last-Modified freshness check
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
                            item_id,
                            asset_url,
                            cache_path,
                            expected_size,
                            progress,
                            fmt,
                            layer_config.source_args.get("item_filter"),
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

    def is_cached(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> bool:
        """Check if at least one item from the collection is cached."""
        if not layer_config.bounds:
            return False

        fmt = layer_config.format or "geotiff"
        resolved_url = self._resolve_url(source_config, layer_config)
        asset_filter = (
            layer_config.asset_filter
            if layer_config.asset_filter is not None
            else source_config.asset_filter
        )

        # Check if any items exist in cache by looking at the collection cache dir
        cache_key = self._collection_cache_key(
            source_config.id, resolved_url, asset_filter
        )
        collection_dir = cache_dir / source_config.id / cache_key
        if not collection_dir.exists():
            return False

        # Check for any cached items (directories with both data file and metadata)
        ext = self._file_extension(fmt)
        for item_dir in collection_dir.iterdir():
            if item_dir.is_dir():
                data_files = list(item_dir.glob(f"*.{ext}"))
                meta_files = list(item_dir.glob("*.json"))
                if data_files and meta_files:
                    return True

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_url(source_config: SourceConfig, layer_config: LayerConfig) -> str:
        """Resolve the collection URL by substituting template variables."""
        if not source_config.urls:
            raise ValueError(f"Source '{source_config.id}' has no URLs configured")

        template = source_config.urls[0]
        variables = {
            **source_config.defaults,
            **layer_config.source_args,
        }
        return expand(template, variables)

    @staticmethod
    def _file_extension(fmt: str) -> str:
        return "gpkg" if fmt == "gpkg" else "tif"

    def _get_cache_dir(
        self,
        source_id: str,
        collection_url: str,
        item_id: str,
        asset_filter: dict[str, str] | None = None,
    ) -> Path:
        """Generate cache directory for a STAC item (NOT including filename)."""
        safe_item_id = item_id.replace("/", "_").replace("\\", "_")
        cache_key = self._collection_cache_key(source_id, collection_url, asset_filter)
        return Path("cache") / source_id / cache_key / safe_item_id

    @staticmethod
    def _collection_cache_key(
        source_id: str,
        collection_url: str,
        asset_filter: dict[str, str] | None = None,
    ) -> str:
        """Generate a cache key for a STAC collection."""
        extra = ""
        if asset_filter:
            extra = ",".join(f"{k}={v}" for k, v in sorted(asset_filter.items()))
        return url_to_cache_key(collection_url, extra=extra)

    def _is_item_cached(
        self, cache_path: Path, expected_size: int | None, fmt: str
    ) -> bool:
        """Check if a single STAC item is cached and valid."""
        if cache_path.exists() and cache_path.stat().st_size > 0:
            meta_path = cache_path.parent / f"{cache_path.stem}.json"
            if not meta_path.exists():
                return False
            if expected_size and cache_path.stat().st_size < expected_size:
                return False
            return True

        # For GeoTIFF: check if original was cleaned up after warping
        if fmt == "geotiff":
            warped_path = cache_path.parent / f"{cache_path.stem}_4326.tif"
            meta_path = cache_path.parent / f"{cache_path.stem}.json"
            warp_marker = cache_path.parent / f"{cache_path.stem}_4326.json"
            if warped_path.exists() and meta_path.exists() and warp_marker.exists():
                return True

        return False

    @staticmethod
    def _is_older_than(cache_path: Path, max_age_days: int) -> bool:
        """Check if a cached file is older than ``max_age_days`` days.

        Reads the ``download_date`` from the metadata JSON sidecar and
        compares it with ``now - max_age_days``. Returns ``True`` if
        the file is older, ``False`` if it is recent enough or if the
        metadata cannot be read.
        """
        from datetime import datetime, timedelta, timezone

        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        if not meta_path.exists():
            return True  # No metadata → treat as old

        try:
            meta = json.loads(meta_path.read_text())
            date_str = meta.get("download_date", "")
            if not date_str:
                return True
            download_date = datetime.fromisoformat(date_str)
            if download_date.tzinfo is None:
                download_date = download_date.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            return download_date < cutoff
        except (json.JSONDecodeError, OSError, ValueError):
            return True

    def _check_freshness(self, asset_url: str, cache_path: Path) -> bool | None:
        """Check freshness via HTTP HEAD ETag/Last-Modified comparison."""
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

    def _download_item(
        self,
        item_id: str,
        asset_url: str,
        cache_path: Path,
        expected_size: int | None,
        progress: Progress,
        fmt: str,
        item_filter: str | None = None,
    ) -> None:
        """Download a single STAC item and write metadata."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "gpkg":
            zip_path = cache_path.parent / f"{item_id}.zip"
            self._download_file(asset_url, zip_path, expected_size, progress)
            extracted = self._extract_gpkg_from_zip(
                zip_path, cache_path.parent, item_filter
            )
            # Rename to canonical name if different
            if extracted != cache_path:
                if cache_path.exists():
                    cache_path.unlink()
                extracted.rename(cache_path)
        else:
            self._download_file(asset_url, cache_path, expected_size, progress)

        self._write_metadata(cache_path, asset_url)

    @staticmethod
    def _download_file(
        url: str,
        dest_path: Path,
        expected_size: int | None = None,
        progress: Progress | None = None,
    ) -> None:
        """Download a file from a URL to a local path."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to download {url}: {e}") from e

        content_length = response.headers.get("Content-Length")
        total = int(content_length) if content_length else expected_size
        chunk_size = 1024 * 1024  # 1 MB

        task_id = None
        if progress:
            task_id = progress.add_task(
                "download", filename=dest_path.name, total=total
            )

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, advance=len(chunk))

        logger.debug("Downloaded %s", dest_path.name)

    @staticmethod
    def _extract_gpkg_from_zip(
        zip_path: Path,
        dest_dir: Path,
        item_filter: str | None = None,
    ) -> Path:
        """Extract a .gpkg file from a zip archive."""
        import re

        with zipfile.ZipFile(zip_path, "r") as zf:
            gpkg_names = [n for n in zf.namelist() if n.lower().endswith(".gpkg")]

            if not gpkg_names:
                raise ValueError(
                    f"No .gpkg file found in archive {zip_path.name}. "
                    f"Archive contents: {zf.namelist()[:20]}"
                )

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

            gpkg_name = gpkg_names[0]
            gpkg_basename = Path(gpkg_name).name
            target_path = dest_dir / gpkg_basename

            if target_path.exists():
                logger.debug("Extracted GPKG already exists: %s", target_path)
                return target_path

            with zf.open(gpkg_name) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

            logger.info("Extracted %s from %s", gpkg_basename, zip_path.name)
            return target_path

    @staticmethod
    def _write_metadata(cache_path: Path, asset_url: str) -> None:
        """Write metadata JSON sidecar with ETag/Last-Modified."""
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
        except requests.RequestException:
            pass

        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        meta_path.write_text(json.dumps(meta, indent=2))


# Register built-in source
register_source("stac", StacSource)
