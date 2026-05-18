"""Source abstraction for fetching geodata.

A Source handles *how* to fetch data (STAC API, WMTS tile service, local path).
The data format (GeoTIFF, GPKG, etc.) is determined by the layer's ``format``
field, not the source type.

Three built-in sources:
- ``StacSource``: Query and download from STAC collection endpoints
- ``WmtsSource``: Download tiles from WMTS/XYZ tile services
- ``PathSource``: Resolve and verify local file paths

Sources are registered in ``SOURCE_REGISTRY`` and resolved by name via
``resolve_source()``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)


class Source(ABC):
    """Abstract base class for geodata sources.

    A source is responsible for:
    1. Downloading raw data to a cache directory
    2. Checking whether data is already cached
    3. Writing metadata sidecars for cache management

    The source does NOT process the data — that's the LayerProvider's job.
    """

    @classmethod
    @abstractmethod
    def can_handle(cls, source_config: SourceConfig) -> bool:
        """Return True if this source can handle the given config.

        Used by the registry to auto-select the right source implementation.
        """

    @abstractmethod
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
        """Download raw data to the cache directory.

        Args:
            source_config: Source configuration (URLs, type, etc.)
            layer_config: Layer configuration (bounds, zoom_levels, format)
            cache_dir: Root cache directory
            offline: If True, skip network requests and use only cached data
            update: If True, check freshness of cached files (ETag/Last-Modified)
            max_age_days: If set, re-check freshness only for files older than N
                days (implies update=True)

        Returns:
            List of paths to downloaded (or cached) files
        """

    @abstractmethod
    def is_cached(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> bool:
        """Check if data is already cached and valid.

        Checks for file existence + metadata sidecar or processor marker.
        """


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

_SOURCE_TYPES: dict[str, type[Source]] = {}


def register_source(name: str, cls: type[Source]) -> None:
    """Register a source implementation by name."""
    if name in _SOURCE_TYPES:
        logger.warning("Source '%s' already registered, overwriting", name)
    _SOURCE_TYPES[name] = cls


def resolve_source(source_type: str) -> type[Source]:
    """Look up a registered source class by type name.

    Raises:
        ValueError: If the source type is not registered.
    """
    cls = _SOURCE_TYPES.get(source_type)
    if cls is None:
        available = ", ".join(sorted(_SOURCE_TYPES.keys()))
        raise ValueError(
            f"Unknown source type '{source_type}'. Available sources: {available}"
        )
    return cls


def get_source_registry() -> dict[str, type[Source]]:
    """Return a copy of the source registry (for inspection/testing)."""
    return dict(_SOURCE_TYPES)


# Auto-import built-in source implementations so their register_source()
# calls execute when this module is imported.
from . import stac_source as _stac_source  # noqa: E402, F401
from . import path_source as _path_source  # noqa: E402, F401
from . import wmts_source as _wmts_source  # noqa: E402, F401
