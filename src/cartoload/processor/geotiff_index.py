"""Spatial index for GeoTIFF files — maps geographic extents to file paths."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_bounds

logger = logging.getLogger(__name__)


@dataclass
class GeoTIFFEntry:
    """A single GeoTIFF file with its geographic extent in WGS84."""

    path: Path
    crs: CRS
    bounds_wgs84: tuple[float, float, float, float]  # (west, south, east, north)


class GeoTIFFIndex:
    """In-memory spatial index over a set of GeoTIFF files.

    Reads CRS and bounds from each file's metadata and provides
    fast lookup by geographic extent. Uses a last-hit cache to
    exploit spatial coherence between consecutive tile lookups.
    """

    def __init__(self, entries: list[GeoTIFFEntry]) -> None:
        self._entries = entries
        self._last_hit_idx: int | None = None

    @classmethod
    def from_paths(cls, paths: list[Path]) -> GeoTIFFIndex:
        """Build an index by reading metadata from each GeoTIFF file.

        Args:
            paths: List of GeoTIFF file paths to index

        Returns:
            A GeoTIFFIndex with entries for all readable files
        """
        entries: list[GeoTIFFEntry] = []
        for path in paths:
            try:
                entry = _read_entry(path)
                entries.append(entry)
                logger.debug(
                    "Indexed %s: CRS=%s bounds=%s",
                    path.name,
                    entry.crs,
                    entry.bounds_wgs84,
                )
            except Exception as e:
                logger.warning("Failed to index %s: %s", path, e)

        if not entries:
            raise ValueError(f"No valid GeoTIFF files found among {len(paths)} path(s)")

        logger.info(
            "Built spatial index with %d entr(y/ies), bounds: %s",
            len(entries),
            _union_bounds(entries),
        )
        return cls(entries)

    @property
    def entries(self) -> list[GeoTIFFEntry]:
        return self._entries

    @property
    def total_bounds(self) -> tuple[float, float, float, float]:
        """Union of all GeoTIFF extents as (west, south, east, north) in WGS84."""
        return _union_bounds(self._entries)

    def find(self, west: float, south: float, east: float, north: float) -> Path | None:
        """Find a GeoTIFF file that covers the given geographic extent.

        Returns the first file whose bounds intersect the query extent.
        Uses a last-hit cache: consecutive tiles are spatially coherent,
        so the same GeoTIFF often covers many tiles in a row.

        Args:
            west, south, east, north: Query extent in WGS84 degrees

        Returns:
            Path to the covering GeoTIFF, or None if no match
        """
        entries = self._entries

        # Fast path: check last-hit entry first (spatial coherence)
        if self._last_hit_idx is not None:
            entry = entries[self._last_hit_idx]
            ew, es, ee, en = entry.bounds_wgs84
            if ew <= east and ee >= west and es <= north and en >= south:
                return entry.path

        # Full scan with cache update
        for i, entry in enumerate(entries):
            ew, es, ee, en = entry.bounds_wgs84
            if ew <= east and ee >= west and es <= north and en >= south:
                self._last_hit_idx = i
                return entry.path

        self._last_hit_idx = None
        return None


def _read_entry(path: Path) -> GeoTIFFEntry:
    """Read CRS and bounds from a GeoTIFF file."""
    with rasterio.open(path) as src:
        crs = src.crs
        if crs is None:
            raise ValueError(f"No CRS in {path}")

        # Read bounds in native CRS, transform to WGS84
        native_bounds = src.bounds
        bounds_wgs84 = transform_bounds(
            crs,
            CRS.from_epsg(4326),
            native_bounds.left,
            native_bounds.bottom,
            native_bounds.right,
            native_bounds.top,
        )

        return GeoTIFFEntry(
            path=path,
            crs=crs,
            bounds_wgs84=bounds_wgs84,  # (left, bottom, right, top)
        )


def _union_bounds(entries: list[GeoTIFFEntry]) -> tuple[float, float, float, float]:
    """Compute the union of all entry bounds."""
    if not entries:
        return (0, 0, 0, 0)
    west = min(e.bounds_wgs84[0] for e in entries)
    south = min(e.bounds_wgs84[1] for e in entries)
    east = max(e.bounds_wgs84[2] for e in entries)
    north = max(e.bounds_wgs84[3] for e in entries)
    return (west, south, east, north)
