from __future__ import annotations

from ._base_downloader import BaseDownloader
from .base import Source, register_source, resolve_source, get_source_registry
from .path import PathSource
from .stac import StacSource
from .stac.downloader import STACDownloader
from .wmts import WmtsDownloader, WmtsSource

__all__ = [
    "BaseDownloader",
    "PathSource",
    "STACDownloader",
    "Source",
    "StacSource",
    "WmtsDownloader",
    "WmtsSource",
    "get_source_registry",
    "register_source",
    "resolve_source",
]
