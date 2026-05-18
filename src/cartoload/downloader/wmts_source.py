"""WmtsSource — download tiles from WMTS/XYZ tile services.

Wraps the existing ``WMTSDownloader`` class, adapting it to the Source
interface. The WMTS source downloads individual tiles on demand rather
than batch-downloading — so ``download()`` prepares the downloader and
returns the cache directory, while actual tile fetching happens during
tile processing via the ``WmtsProvider``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cartoload.downloader.source import Source, register_source
from cartoload.downloader.wmts import WMTSDownloader
from cartoload.template import expand

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)


class WmtsSource(Source):
    """Download tiles from WMTS/XYZ tile services.

    Uses the ``WMTSDownloader`` internally. The ``download()`` method
    creates and returns a configured downloader instance (stored as
    ``source_instance`` on the returned data) for use by the WmtsProvider.
    """

    def __init__(self):
        self._downloaders: dict[str, WMTSDownloader] = {}

    @classmethod
    def can_handle(cls, source_config: SourceConfig) -> bool:
        return source_config.type == "wmts"

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
        ``WMTSDownloader`` instance for later use.

        Returns:
            List containing the source cache directory path.
        """
        downloader = self._make_downloader(source_config, layer_config, cache_dir)

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
        downloader = self._make_downloader(source_config, layer_config, cache_dir)
        cache_base = downloader.source_cache_dir
        if not cache_base.exists():
            return False
        # Check if there are any tile files in the cache
        for ext in ("jpeg", "jpg", "png"):
            if any(cache_base.rglob(f"*.{ext}")):
                return True
        return False

    def get_downloader(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> WMTSDownloader:
        """Get or create a WMTSDownloader for the given source/layer."""
        key = self._cache_key(source_config, layer_config)
        if key not in self._downloaders:
            self._downloaders[key] = self._make_downloader(
                source_config, layer_config, cache_dir
            )
        return self._downloaders[key]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_downloader(
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> WMTSDownloader:
        """Create a WMTSDownloader from source and layer config."""
        # Resolve URL template by merging source defaults + layer source_args
        variables = {
            **source_config.defaults,
            **layer_config.source_args,
        }
        # Don't expand per-tile variables here — those are for the downloader
        tile_vars = {"x", "y", "z", "zoom"}
        config_variables = {k: v for k, v in variables.items() if k not in tile_vars}

        url_template = expand(source_config.urls[0], config_variables)

        # Determine tile format from source_args
        tile_format = config_variables.get("extension", "jpeg")

        # Layer name for display
        layer_name = config_variables.get("layer", "")

        return WMTSDownloader(
            source_id=source_config.id,
            url_template=url_template,
            cache_dir=cache_dir,
            max_workers=source_config.max_threads,
            delay_ms=source_config.rate_limit_ms,
            tile_format=tile_format,
            layer_name=layer_name,
            crs=source_config.crs,
            urls=source_config.urls[1:] if len(source_config.urls) > 1 else None,
            display_name=layer_config.name,
        )

    @staticmethod
    def _cache_key(source_config: SourceConfig, layer_config: LayerConfig) -> str:
        return f"{source_config.id}:{layer_config.source_args.get('layer', '')}"


# Register built-in source
register_source("wmts", WmtsSource)
