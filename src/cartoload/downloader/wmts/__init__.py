"""WMTS tile downloading, capabilities parsing, and tile grid computation."""

from __future__ import annotations

from .capabilities import (
    ResourceUrl,
    TileMatrix,
    TileMatrixSet,
    WmtsCapabilities,
    WmtsLayer,
    parse_capabilities,
    resource_url_to_template,
)
from .download import (
    WMTSDownloader,
    _PerUrlRateLimiter,
    _UrlSelector,
)
from .tile_grid import (
    bbox_to_tile_indices,
    compute_tile_bounds,
    wgs84_to_tms_bbox,
)

__all__ = [
    "ResourceUrl",
    "TileMatrix",
    "TileMatrixSet",
    "WMTSDownloader",
    "WmtsCapabilities",
    "WmtsLayer",
    "bbox_to_tile_indices",
    "compute_tile_bounds",
    "parse_capabilities",
    "resource_url_to_template",
    "wgs84_to_tms_bbox",
]
