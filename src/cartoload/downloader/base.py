from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseDownloader(ABC):
    """Abstract base class for geodata downloaders."""

    def __init__(
        self,
        source_id: str,
        cache_dir: str | Path = "cache",
        max_workers: int = 4,
        delay_ms: int = 150,
    ) -> None:
        self._source_id = source_id
        self._cache_dir = Path(cache_dir)
        self._max_workers = max_workers
        self._delay_ms = delay_ms

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @abstractmethod
    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        """Download a single tile and return its cached path."""

    @abstractmethod
    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        """Download all tiles covering the bbox at the given zoom level."""
