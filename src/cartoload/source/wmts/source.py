"""WmtsSource — download tiles from WMTS/XYZ tile services.

Wraps the existing ``WmtsDownloader`` class, adapting it to the Source
interface. The WMTS source downloads individual tiles on demand rather
than batch-downloading — so ``download()`` prepares the downloader and
returns the cache directory, while actual tile fetching happens during
tile processing via the ``WmtsProcessor``.

Two modes:
  - **Template mode** (default): URL contains ``${x}/${y}/${z}`` placeholders.
    Uses hardcoded Web Mercator tile grid.
  - **Capabilities mode**: ``capabilities_url`` is set or URL is a WMTS
    GetCapabilities endpoint. Fetches and parses the Capabilities XML to
    auto-discover layers, TileMatrixSets, CRS, and URL templates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cartoload.source.cache_key import url_to_cache_key
from cartoload.source.base import Source, register_source
from cartoload.source.wmts.capabilities import (
    WmtsCapabilities,
    parse_capabilities,
    resource_url_to_template,
)
from cartoload.source.wmts.download import WmtsDownloader
from cartoload.template import expand

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)


class WmtsSource(Source):
    """Download tiles from WMTS/XYZ tile services.

    Uses the ``WmtsDownloader`` internally. The ``download()`` method
    creates and returns a configured downloader instance (stored as
    ``source_instance`` on the returned data) for use by the WmtsProcessor.
    """

    def __init__(self):
        self._downloaders: dict[str, WmtsDownloader] = {}
        self._capabilities_cache: dict[str, WmtsCapabilities] = {}

    @classmethod
    def can_handle(cls, source_config: SourceConfig) -> bool:
        return source_config.type in ("wmts", "xyz")

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
        """Create a WMTS downloader for this source/layer combination.

        WMTS downloads tiles on-demand (per tile request), so this doesn't
        download anything immediately. Instead it creates and caches a
        ``WmtsDownloader`` instance for later use.

        Returns:
            List containing the source cache directory path.
        """
        if self._is_capabilities_mode(source_config):
            downloader = self._make_capabilities_downloader(
                source_config, layer_config, cache_dir, offline=offline
            )
        else:
            downloader = self._make_template_downloader(
                source_config, layer_config, cache_dir
            )

        # Store for later retrieval by provider
        key = self._cache_key(source_config, layer_config)
        self._downloaders[key] = downloader

        return [downloader.source_cache_dir]

    def is_cached(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> bool:
        """Check if any tiles are cached for this source/layer combo."""
        if self._is_capabilities_mode(source_config):
            # In Capabilities mode, construct cache dir from resolved params
            layer_id = self._resolve_layer_id(source_config, layer_config)
            cache_base = Path(cache_dir) / source_config.id / layer_id
        else:
            variables = {
                **source_config.defaults,
                **layer_config.source_args,
            }
            config_variables = {
                k: v for k, v in variables.items() if k not in {"x", "y", "z", "zoom"}
            }
            url_template = expand(source_config.urls[0], config_variables)
            cache_base = (
                Path(cache_dir) / source_config.id / url_to_cache_key(url_template)
            )

        if not cache_base.exists():
            return False
        for ext in ("jpeg", "jpg", "png"):
            if any(cache_base.rglob(f"*.{ext}")):
                return True
        return False

    def get_downloader(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> WmtsDownloader:
        """Get or create a WmtsDownloader for the given source/layer."""
        key = self._cache_key(source_config, layer_config)
        if key not in self._downloaders:
            if self._is_capabilities_mode(source_config):
                self._downloaders[key] = self._make_capabilities_downloader(
                    source_config, layer_config, cache_dir
                )
            else:
                self._downloaders[key] = self._make_template_downloader(
                    source_config, layer_config, cache_dir
                )
        return self._downloaders[key]

    # ------------------------------------------------------------------
    # Mode detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_capabilities_mode(source_config: SourceConfig) -> bool:
        """Determine if this source should use Capabilities mode.

        Capabilities mode is triggered when:
        - ``capabilities_url`` is explicitly set, OR
        - The URL looks like a WMTS GetCapabilities endpoint

        Template mode is used when:
        - URLs contain ``${x}/${y}/${z}`` placeholders, OR
        - ``type: xyz`` is used
        """
        if source_config.capabilities_url:
            return True
        if source_config.urls:
            url = source_config.urls[0]
            if _is_capabilities_url(url):
                return True
        return False

    # ------------------------------------------------------------------
    # Template mode (existing behavior)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_template_downloader(
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> WmtsDownloader:
        """Create a WmtsDownloader from URL template config."""
        # Resolve URL template by merging source defaults + layer source_args
        variables = {
            **source_config.defaults,
            **layer_config.source_args,
        }
        # Don't expand per-tile variables here — those are for the downloader
        tile_vars = {"x", "y", "z", "zoom"}
        config_variables = {k: v for k, v in variables.items() if k not in tile_vars}

        url_template = expand(source_config.urls[0], config_variables)

        # Expand additional URLs with the same config variables
        extra_urls = (
            [expand(u, config_variables) for u in source_config.urls[1:]]
            if len(source_config.urls) > 1
            else None
        )

        # Determine tile format from source_args
        tile_format = config_variables.get("extension", "jpeg")

        # Layer name for display
        layer_name = config_variables.get("layer", "")

        return WmtsDownloader(
            source_id=source_config.id,
            url_template=url_template,
            cache_dir=cache_dir,
            max_workers=source_config.max_threads,
            delay_ms=source_config.rate_limit_ms,
            tile_format=tile_format,
            layer_name=layer_name,
            crs=source_config.crs,
            urls=extra_urls,
            display_name=layer_config.name,
        )

    # ------------------------------------------------------------------
    # Capabilities mode (new)
    # ------------------------------------------------------------------

    def _make_capabilities_downloader(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
        *,
        offline: bool = False,
    ) -> WmtsDownloader:
        """Create a WmtsDownloader from WMTS Capabilities.

        Fetches and parses the GetCapabilities XML, resolves the requested
        layer + TileMatrixSet, and constructs a URL template from the
        ResourceURL element.
        """
        capabilities = self._fetch_capabilities(source_config, offline=offline)

        # Resolve layer ID
        layer_id = self._resolve_layer_id(source_config, layer_config)

        # Resolve TileMatrixSet ID
        tms_id = self._resolve_tms_id(source_config, layer_config)

        # Determine tile format
        tile_format = self._resolve_tile_format(source_config, layer_config)

        # Resolve layer → (layer, tms, resource_url)
        wmts_layer, tms, resource_url = capabilities.resolve_layer(
            layer_id, tms_id=tms_id, tile_format=tile_format
        )

        # Convert WMTS ResourceURL template to cartoload format
        url_template = resource_url_to_template(
            resource_url.template, wmts_layer.dimensions
        )

        # Resolve CRS from TileMatrixSet
        crs = source_config.crs
        if crs is None and tms.epsg_code:
            crs = f"EPSG:{tms.epsg_code}"

        logger.info(
            "WMTS Capabilities resolved: layer=%s, TMS=%s, CRS=%s, format=%s",
            layer_id,
            tms.identifier,
            crs,
            tile_format,
        )

        # Determine extension from format
        extension = _format_to_extension(
            resource_url.format or tile_format or "image/jpeg"
        )

        # Build additional URLs from source config
        extra_urls = None
        if source_config.urls:
            # URLs in config are additional endpoints (not the capabilities URL)
            extra_urls = source_config.urls

        return WmtsDownloader(
            source_id=source_config.id,
            url_template=url_template,
            cache_dir=cache_dir,
            max_workers=source_config.max_threads,
            delay_ms=source_config.rate_limit_ms,
            tile_format=extension,
            layer_name=layer_id,
            crs=crs,
            urls=extra_urls,
            display_name=layer_config.name or wmts_layer.title,
        )

    def _fetch_capabilities(
        self,
        source_config: SourceConfig,
        *,
        offline: bool = False,
    ) -> WmtsCapabilities:
        """Fetch and parse the WMTS GetCapabilities document."""
        caps_url = source_config.capabilities_url
        if not caps_url and source_config.urls:
            # Find first URL that is a capabilities URL
            for url in source_config.urls:
                if _is_capabilities_url(url):
                    caps_url = url
                    break
            if not caps_url:
                caps_url = source_config.urls[0]

        assert caps_url is not None, "No capabilities URL available"

        # Use cached capabilities if available
        if caps_url in self._capabilities_cache:
            return self._capabilities_cache[caps_url]

        if offline:
            raise RuntimeError(
                f"Cannot fetch WMTS Capabilities in offline mode: {caps_url}"
            )

        logger.info("Fetching WMTS Capabilities from %s", caps_url)
        import requests

        response = requests.get(caps_url, timeout=30)
        response.raise_for_status()

        capabilities = parse_capabilities(response.text)
        self._capabilities_cache[caps_url] = capabilities
        return capabilities

    @staticmethod
    def _resolve_layer_id(
        source_config: SourceConfig,
        layer_config: LayerConfig,
    ) -> str:
        """Resolve the WMTS layer identifier from config."""
        # Priority: source_args > source.layer > source defaults
        layer_id = layer_config.source_args.get("layer")
        if layer_id:
            return layer_id
        if source_config.layer:
            return source_config.layer
        if source_config.defaults.get("layer"):
            return source_config.defaults["layer"]
        raise ValueError(
            f"No layer identifier specified for WMTS Capabilities source "
            f"'{source_config.id}'. Set 'layer' in the source config or "
            f"'source_args.layer' in the layer config."
        )

    @staticmethod
    def _resolve_tms_id(
        source_config: SourceConfig,
        layer_config: LayerConfig,
    ) -> str | None:
        """Resolve the TileMatrixSet identifier from config."""
        tms_id = layer_config.source_args.get("tile_matrix_set")
        if tms_id:
            return tms_id
        return source_config.tile_matrix_set

    @staticmethod
    def _resolve_tile_format(
        source_config: SourceConfig,
        layer_config: LayerConfig,
    ) -> str | None:
        """Resolve the desired tile format."""
        ext = layer_config.source_args.get("extension")
        if ext:
            return _extension_to_format(ext)
        ext = source_config.defaults.get("extension")
        if ext:
            return _extension_to_format(ext)
        return None  # Let capabilities resolve it

    # ------------------------------------------------------------------
    # Cache key
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(source_config: SourceConfig, layer_config: LayerConfig) -> str:
        return f"{source_config.id}:{layer_config.source_args.get('layer', '')}"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _is_capabilities_url(url: str) -> bool:
    """Check if a URL looks like a WMTS GetCapabilities endpoint."""
    url_lower = url.lower()
    return "wmtscapabilities" in url_lower or (
        "getcapabilities" in url_lower and "wmts" in url_lower
    )


def _format_to_extension(fmt: str) -> str:
    """Convert a MIME type like 'image/jpeg' to a file extension like 'jpeg'."""
    if "/" in fmt:
        return fmt.split("/")[-1]
    return fmt


def _extension_to_format(ext: str) -> str:
    """Convert a file extension like 'jpeg' to a MIME type like 'image/jpeg'."""
    mime_map = {
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "tiff": "image/tiff",
        "tif": "image/tiff",
    }
    return mime_map.get(ext.lower(), f"image/{ext}")


# Register built-in sources
register_source("wmts", WmtsSource)
register_source("xyz", WmtsSource)
