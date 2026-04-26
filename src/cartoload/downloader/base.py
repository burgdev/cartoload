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

    def reprojection_cache_path(
        self, x: int, y: int, zoom: int, target_crs: str, tile_format: str
    ) -> Path:
        """Return the reprojection cache path for a tile.

        The reprojection cache is stored at:
            cache/{source_id}_{crs_code}/{zoom}/{x}/{y}.{format}

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            zoom: Zoom level
            target_crs: Target CRS string (e.g., "EPSG:4326")
            tile_format: Tile format extension (e.g., "jpeg", "png")

        Returns:
            Path to the reprojected tile in cache
        """
        crs_code = target_crs.lower().replace(":", "_")
        return (
            self._cache_dir
            / f"{self._source_id}_{crs_code}"
            / str(zoom)
            / str(x)
            / f"{y}.{tile_format}"
        )

    @staticmethod
    def reprojection_cache_dir(
        cache_dir: Path, source_id: str, target_crs: str
    ) -> Path:
        """Return the reprojection cache directory for a source and target CRS.

        Args:
            cache_dir: Base cache directory
            source_id: Source identifier
            target_crs: Target CRS string (e.g., "EPSG:4326")

        Returns:
            Path to the reprojection cache directory
        """
        crs_code = target_crs.lower().replace(":", "_")
        return cache_dir / f"{source_id}_{crs_code}"

    def is_reprojection_valid(self, source_tile: Path, reprojected_tile: Path) -> bool:
        """Check if a reprojected tile is still valid based on source tile mtime.

        A reprojected tile is considered valid if it exists and its mtime is
        >= the source tile's mtime (i.e., it was created after the source tile
        was last modified).

        Args:
            source_tile: Path to the source (downloaded) tile
            reprojected_tile: Path to the reprojected tile

        Returns:
            True if the reprojected tile is valid, False if it needs re-reprojection
        """
        if not reprojected_tile.exists():
            return False
        if not source_tile.exists():
            return False
        if reprojected_tile.stat().st_size == 0:
            return False
        return reprojected_tile.stat().st_mtime >= source_tile.stat().st_mtime

    @staticmethod
    def needs_reprojection(source_crs: str | None, target_crs: str) -> bool:
        """Check if reprojection is needed between source and target CRS.

        Args:
            source_crs: Source CRS string (e.g., "EPSG:3857"), or None if unknown
            target_crs: Target CRS string (e.g., "EPSG:4326")

        Returns:
            True if reprojection is needed, False if source and target CRS match
        """
        if source_crs is None:
            return True
        return source_crs.strip().upper() != target_crs.strip().upper()

    @abstractmethod
    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        """Download a single tile and return its cached path."""

    @abstractmethod
    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        """Download all tiles covering the bbox at the given zoom level."""
