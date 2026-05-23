"""GeotiffProcessor — process GeoTIFF files into raster tiles.

Downloads GeoTIFF data from STAC or local paths, pre-warps to EPSG:4326,
builds a VRT mosaic, and reads tiles on demand.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cartoload.processor.base import LayerProcessor, register_processor

if TYPE_CHECKING:
    from PIL import Image

    from cartoload.config import LayerConfig, SourceConfig
    from cartoload.source.base import Source

logger = logging.getLogger(__name__)


class GeotiffProcessor(LayerProcessor):
    """Processor for GeoTIFF data.

    Lifecycle:
    1. download(): Fetch GeoTIFF files via StacSource or PathSource
    2. prepare(): Pre-warp to EPSG:4326, build VRT mosaic
    3. to_raster(): Read tiles from the warped mosaic
    """

    def __init__(
        self,
        source: Source,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ):
        super().__init__(source, source_config, layer_config, cache_dir)
        self._downloaded_paths: list[Path] = []
        self._prewarped_map: dict[Path, Path] = {}
        self._mosaic_path: Path | None = None

    @property
    def supported_extensions(self) -> list[str]:
        return [".tif", ".tiff"]

    def prepare(self) -> None:
        if not self._downloaded_paths:
            logger.warning(
                "GeotiffProcessor.prepare(): no downloaded files for layer '%s'",
                self.layer_config.id,
            )
            return

        from cartoload.processor.geotiff.prewarp import (
            merge_prewarped_geotiffs,
            prewarp_all_geotiffs,
        )

        # Determine bbox from layer bounds
        bbox = None
        if self.layer_config.bounds:
            bbox = (
                self.layer_config.bounds["west"],
                self.layer_config.bounds["south"],
                self.layer_config.bounds["east"],
                self.layer_config.bounds["north"],
            )

        # Pre-warp all GeoTIFFs to EPSG:4326
        self._prewarped_map = prewarp_all_geotiffs(
            self._downloaded_paths,
            target_crs="EPSG:4326",
            cleanup=True,
            bbox=bbox,
            label=self.layer_config.name,
        )

        prewarped_paths = list(self._prewarped_map.values())

        if not prewarped_paths:
            return

        # Build VRT mosaic if multiple files
        if len(prewarped_paths) > 1:
            # Use the parent of the first file as the mosaic directory
            mosaic_dir = prewarped_paths[0].parent
            self._mosaic_path = merge_prewarped_geotiffs(
                prewarped_paths,
                mosaic_dir,
                mosaic_name=f"{self.layer_config.id}_mosaic.vrt",
            )
        else:
            self._mosaic_path = prewarped_paths[0]

    def to_raster(self, x: int, y: int, z: int) -> Image.Image | None:
        if not self._mosaic_path or not self._mosaic_path.exists():
            return None

        from cartoload.processor.geotiff.tile_reader import (
            read_tile_from_warped_geotiff,
        )

        result = read_tile_from_warped_geotiff(self._mosaic_path, x, y, z, quality=95)
        if result is None:
            return None

        from PIL import Image
        import io

        jpeg_bytes, _bounds = result
        return Image.open(io.BytesIO(jpeg_bytes))

    @property
    def mosaic_path(self) -> Path | None:
        """Path to the VRT mosaic (after prepare())."""
        return self._mosaic_path


# Register built-in processor
register_processor("geotiff", GeotiffProcessor)
