from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GdalNotFoundError(Exception):
    """Raised when required GDAL tools are not found on PATH."""

    pass


class GdalProcessError(Exception):
    """Raised when a GDAL subprocess returns a non-zero exit code."""

    pass


class RasterProcessor:
    """
    Processes raster tiles into a single mosaicked, reprojected GeoTIFF.

    Uses GDAL command-line tools (gdalbuildvrt, gdalwarp, gdaladdo) to:
    1. Build a VRT (virtual raster) from input tiles
    2. Reproject to target CRS and write to GeoTIFF
    3. Build overview pyramids for multi-resolution access
    """

    def __init__(
        self, target_crs: str, output_path: Path | str, source_crs: str | None = None
    ):
        """
        Initialize the raster processor.

        Args:
            target_crs: Target coordinate reference system (e.g., "EPSG:3857", "EPSG:4326")
            output_path: Path to output GeoTIFF file
            source_crs: Optional source CRS to declare via -a_srs when building the VRT

        Raises:
            GdalNotFoundError: If required GDAL tools are not available
        """
        self.target_crs = target_crs
        self.output_path = Path(output_path)
        self.source_crs = source_crs

        # Ensure GDAL is available
        self._check_gdal_available()

    @staticmethod
    def _check_gdal_available() -> None:
        """
        Verify that required GDAL tools are on PATH.

        Raises:
            GdalNotFoundError: If any required tool is missing
        """
        required_tools = ["gdalbuildvrt", "gdalwarp", "gdaladdo"]
        missing_tools = []

        for tool in required_tools:
            if not shutil.which(tool):
                missing_tools.append(tool)

        if missing_tools:
            missing_str = ", ".join(missing_tools)
            raise GdalNotFoundError(
                f"Required GDAL tools not found: {missing_str}\n\n"
                f"Install GDAL:\n"
                f"  Ubuntu/Debian: sudo apt install gdal-bin\n"
                f"  macOS (Homebrew): brew install gdal\n"
                f"  Windows (OSGeo4W): https://trac.osgeo.org/osgeo4w/\n"
                f"  Docker: Use the cartoload Docker image"
            )

    def process(self, tiles: list[Path]) -> Path:
        """
        Process a list of raster tiles into a single output GeoTIFF.

        Args:
            tiles: List of paths to input raster tiles

        Returns:
            Path to the output GeoTIFF

        Raises:
            ValueError: If tiles list is empty
            GdalProcessError: If any GDAL operation fails
        """
        if not tiles:
            raise ValueError("Cannot process empty tile list")

        logger.info(f"Processing {len(tiles)} tile(s) into {self.output_path}")

        # Ensure output directory exists
        self._ensure_output_dir()

        # Step 1: Build VRT from input tiles
        vrt_path = self.output_path.with_suffix(".vrt")
        logger.info(f"Building VRT from {len(tiles)} tiles")
        self._build_vrt(tiles, vrt_path)

        # Step 2: Reproject VRT to target CRS and write GeoTIFF
        logger.info(f"Reprojecting to {self.target_crs}")
        self._reproject(vrt_path, self.output_path)

        # Step 3: Build overviews
        logger.info("Building overview pyramids")
        self._build_overviews(self.output_path)

        logger.info(f"Raster processing complete: {self.output_path}")

        return self.output_path

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def _build_vrt(self, tiles: list[Path], vrt_path: Path) -> Path:
        """
        Build a VRT (Virtual Raster Table) from input tiles.

        Args:
            tiles: List of paths to input raster files
            vrt_path: Path to output VRT file

        Returns:
            Path to the created VRT file

        Raises:
            ValueError: If tiles list is empty
            GdalProcessError: If gdalbuildvrt fails
        """
        if not tiles:
            raise ValueError("Cannot build VRT from empty tile list")

        # Build command
        cmd = ["gdalbuildvrt"]
        if self.source_crs:
            cmd.extend(["-a_srs", self.source_crs])
        cmd.append(str(vrt_path))
        cmd.extend(str(tile) for tile in tiles)

        # Execute
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise GdalProcessError(
                f"gdalbuildvrt failed with exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

        logger.debug(f"Created VRT: {vrt_path}")
        return vrt_path

    def _reproject(self, vrt_path: Path, output_path: Path) -> Path:
        """
        Reproject VRT to target CRS and write as GeoTIFF.

        Args:
            vrt_path: Path to input VRT file
            output_path: Path to output GeoTIFF file

        Returns:
            Path to the output GeoTIFF

        Raises:
            GdalProcessError: If gdalwarp fails
        """
        cmd = [
            "gdalwarp",
            "-t_srs",
            self.target_crs,
            "-of",
            "GTiff",
            "-co",
            "COMPRESS=LZW",
            "-co",
            "TILED=YES",
            "-co",
            "BIGTIFF=IF_SAFER",
            str(vrt_path),
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise GdalProcessError(
                f"gdalwarp failed with exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

        logger.debug(f"Reprojected to: {output_path}")
        return output_path

    def _build_overviews(self, geotiff_path: Path) -> None:
        """
        Build overview pyramids for a GeoTIFF.

        Args:
            geotiff_path: Path to GeoTIFF file (modified in-place)

        Raises:
            GdalProcessError: If gdaladdo fails
        """
        cmd = [
            "gdaladdo",
            "-r",
            "average",
            str(geotiff_path),
            "2",
            "4",
            "8",
            "16",
            "32",
            "64",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise GdalProcessError(
                f"gdaladdo failed with exit code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

        logger.debug(f"Built overviews for: {geotiff_path}")
