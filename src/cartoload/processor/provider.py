"""LayerProvider abstraction for processing geodata into tiles.

A LayerProvider handles *how to process* a specific data format into
raster tiles for compositing. Each provider implements:

1. ``download()`` — delegate to a Source to fetch raw data
2. ``prepare()`` — pre-process downloaded data (warp, rasterize, etc.)
3. ``to_raster(x, y, z)`` — return an RGBA tile for compositing

Three built-in providers:
- ``GeotiffProvider``: read tiles from GeoTIFF files (STAC or local)
- ``GpkgProvider``: rasterize vector features from GeoPackage files
- ``WmtsProvider``: fetch and load tiles from WMTS services

Providers are registered in ``PROVIDER_REGISTRY`` and created via
``make_provider()``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from cartoload.config import LayerConfig, SourceConfig
    from cartoload.downloader.source import Source

logger = logging.getLogger(__name__)


class LayerProvider(ABC):
    """Abstract base class for layer data processors.

    A provider takes raw downloaded data and produces raster tiles
    suitable for compositing or direct export.

    Lifecycle:
    1. ``download()`` — fetch raw data via the Source
    2. ``prepare()`` — pre-process (warp, rasterize, build VRT)
    3. ``to_raster(x, y, z)`` — produce RGBA tiles on demand
    """

    def __init__(
        self,
        source: Source,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ):
        self.source = source
        self.source_config = source_config
        self.layer_config = layer_config
        self.cache_dir = cache_dir

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions this provider can handle (e.g. ['.tif', '.tiff'])."""

    @abstractmethod
    def download(
        self,
        *,
        offline: bool = False,
        update: bool = False,
        max_age_days: int | None = None,
    ) -> list[Path]:
        """Download raw data via the source.

        Args:
            offline: If True, only use cached data
            update: If True, check freshness via HTTP HEAD (ETag/Last-Modified)
            max_age_days: If set, skip freshness check if downloaded < N days ago

        Returns:
            List of paths to downloaded files.
        """

    @abstractmethod
    def prepare(self) -> None:
        """Pre-process downloaded data.

        Called after download(). Performs format-specific preparation:
        - GeotiffProvider: pre-warp to EPSG:4326, build VRT
        - GpkgProvider: rasterize features to PNG tiles
        - WmtsProvider: no-op (tiles are fetched on demand)
        """

    @abstractmethod
    def to_raster(self, x: int, y: int, z: int) -> Image.Image | None:
        """Return an RGBA tile for position (x, y, z).

        Returns:
            PIL Image in RGBA mode, or None if no data at this position.
        """


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDER_TYPES: dict[str, type[LayerProvider]] = {}


def register_provider(name: str, cls: type[LayerProvider]) -> None:
    """Register a provider implementation by format name."""
    if name in _PROVIDER_TYPES:
        logger.warning("Provider '%s' already registered, overwriting", name)
    _PROVIDER_TYPES[name] = cls


def make_provider(
    format_name: str,
    source: Source,
    source_config: SourceConfig,
    layer_config: LayerConfig,
    cache_dir: Path,
) -> LayerProvider:
    """Create a provider instance for the given format.

    Args:
        format_name: Data format (``geotiff``, ``gpkg``, ``wmts``)
        source: Source instance for downloading
        source_config: Source configuration
        layer_config: Layer configuration
        cache_dir: Root cache directory

    Returns:
        Configured LayerProvider instance

    Raises:
        ValueError: If the format is not registered
    """
    cls = _PROVIDER_TYPES.get(format_name)
    if cls is None:
        available = ", ".join(sorted(_PROVIDER_TYPES.keys()))
        raise ValueError(
            f"Unknown provider format '{format_name}'. Available providers: {available}"
        )
    return cls(source, source_config, layer_config, cache_dir)


def get_provider_registry() -> dict[str, type[LayerProvider]]:
    """Return a copy of the provider registry (for inspection/testing)."""
    return dict(_PROVIDER_TYPES)


# Auto-import built-in provider implementations so their register_provider()
# calls execute when this module is imported.
from . import geotiff_provider as _geotiff_provider  # noqa: E402, F401
from . import gpkg_provider as _gpkg_provider  # noqa: E402, F401
from . import wmts_provider as _wmts_provider  # noqa: E402, F401
