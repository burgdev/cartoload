"""LayerProcessor abstraction for processing geodata into tiles.

A LayerProcessor handles *how to process* a specific data format into
raster tiles for compositing. Each processor implements:

1. ``download()`` — delegate to a Source to fetch raw data
2. ``prepare()`` — pre-process downloaded data (warp, rasterize, etc.)
3. ``to_raster(x, y, z)`` — return an RGBA tile for compositing

Three built-in processors:
- ``GeotiffProcessor``: read tiles from GeoTIFF files (STAC or local)
- ``GpkgProcessor``: rasterize vector features from GeoPackage files
- ``WmtsProcessor``: fetch and load tiles from WMTS services

Processors are registered in ``_PROCESSOR_TYPES`` and created via
``make_processor()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils import Registry

if TYPE_CHECKING:
    from PIL import Image

    from cartoload.config import LayerConfig, SourceConfig
    from cartoload.source.base import Source


class LayerProcessor(ABC):
    """Abstract base class for layer data processors.

    A processor takes raw downloaded data and produces raster tiles
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
        """File extensions this processor can handle (e.g. ['.tif', '.tiff'])."""

    def download(
        self,
        *,
        offline: bool = False,
        update: bool = False,
        max_age_days: int | None = None,
    ) -> list[Path]:
        """Download raw data via the source.

        The default implementation delegates to ``self.source.download()``
        and stores the result in ``self._downloaded_paths``. Subclasses
        that need custom download logic (e.g. WmtsProcessor) should
        override this method.

        Args:
            offline: If True, only use cached data
            update: If True, check freshness via HTTP HEAD (ETag/Last-Modified)
            max_age_days: If set, skip freshness check if downloaded < N days ago

        Returns:
            List of paths to downloaded files.
        """
        self._downloaded_paths = self.source.download(
            self.source_config,
            self.layer_config,
            self.cache_dir,
            offline=offline,
            update=update,
            max_age_days=max_age_days,
        )
        return self._downloaded_paths

    @abstractmethod
    def prepare(self) -> None:
        """Pre-process downloaded data.

        Called after download(). Performs format-specific preparation:
        - GeotiffProcessor: pre-warp to EPSG:4326, build VRT
        - GpkgProcessor: rasterize features to PNG tiles
        - WmtsProcessor: no-op (tiles are fetched on demand)
        """

    @abstractmethod
    def to_raster(self, x: int, y: int, z: int) -> Image.Image | None:
        """Return an RGBA tile for position (x, y, z).

        Returns:
            PIL Image in RGBA mode, or None if no data at this position.
        """


# ---------------------------------------------------------------------------
# Processor registry
# ---------------------------------------------------------------------------

_PROCESSOR_REGISTRY = Registry[LayerProcessor]("Processor")
register_processor = _PROCESSOR_REGISTRY.register
get_processor_registry = _PROCESSOR_REGISTRY.get_all


def make_processor(
    format_name: str,
    source: Source,
    source_config: SourceConfig,
    layer_config: LayerConfig,
    cache_dir: Path,
) -> LayerProcessor:
    """Create a processor instance for the given format.

    Args:
        format_name: Data format (``geotiff``, ``gpkg``, ``wmts``)
        source: Source instance for downloading
        source_config: Source configuration
        layer_config: Layer configuration
        cache_dir: Root cache directory

    Returns:
        Configured LayerProcessor instance

    Raises:
        ValueError: If the format is not registered
    """
    cls = _PROCESSOR_REGISTRY.resolve(format_name)
    return cls(source, source_config, layer_config, cache_dir)


# Auto-import built-in processor implementations so their register_processor()
# calls execute when this module is imported.
from .geotiff import processor as _geotiff_proc  # noqa: E402, F401
from .gpkg import processor as _gpkg_proc  # noqa: E402, F401
from .wmts import processor as _wmts_proc  # noqa: E402, F401
