from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseDownloader(ABC):
    """Abstract base class for geodata downloaders."""

    def __init__(
        self,
        source_id: str,
        cache_dir: str | Path = "cache",
        max_workers: int = 4,
        delay_ms: int = 150,
        crs: str | None = None,
    ) -> None:
        self._source_id = source_id
        self._cache_dir = Path(cache_dir)
        self._max_workers = max_workers
        self._delay_ms = delay_ms
        self._crs = crs

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @property
    def source_cache_dir(self) -> Path:
        """Cache directory for this source."""
        return self._cache_dir / self._source_id

    def write_cache_metadata(self) -> None:
        """Write metadata.json to the source cache directory if it doesn't exist."""
        metadata_path = self.source_cache_dir / "metadata.json"
        if metadata_path.exists():
            return
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {}
        if self._crs:
            metadata["crs"] = self._crs
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        logger.debug(f"Wrote cache metadata to {metadata_path}")

    @staticmethod
    def read_cache_crs(cache_dir: Path, source_id: str) -> str | None:
        """Read CRS from cache metadata.json. Returns None if not found."""
        metadata_path = cache_dir / source_id / "metadata.json"
        if not metadata_path.exists():
            return None
        try:
            data = json.loads(metadata_path.read_text())
            return data.get("crs")
        except (json.JSONDecodeError, OSError):
            return None

    @abstractmethod
    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        """Download a single tile and return its cached path."""

    @abstractmethod
    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        """Download all tiles covering the bbox at the given zoom level."""
