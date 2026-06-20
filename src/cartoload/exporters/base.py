from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cartoload.config import LayerConfig


class BaseExporter(ABC):
    """
    Abstract base class for map exporters.

    Exporters convert processed raster data into device-specific formats
    (e.g., Garmin .img, GeoPackage, MBTiles).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable name of this exporter.

        Returns:
            Exporter name (e.g., "garmin_img", "mbtiles")
        """
        pass

    @abstractmethod
    def export(
        self, raster_path: Path, layer_config: LayerConfig, output_path: Path
    ) -> list[Path]:
        """
        Export processed raster data to device-specific format.

        Args:
            raster_path: Path to processed GeoTIFF raster file
            layer_config: Layer configuration (zoom levels, bounds, metadata)
            output_path: Path to output file (may produce multiple files)

        Returns:
            List of paths to created files (one or more if splitting occurred)

        Raises:
            Exception: If export fails
        """
        pass

    @abstractmethod
    def validate(self, output_path: Path) -> bool:
        """
        Validate that the exported file is structurally correct.

        Args:
            output_path: Path to file to validate

        Returns:
            True if valid, False otherwise

        Raises:
            Exception: If validation cannot be performed
        """
        pass
