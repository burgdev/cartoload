"""WmtsProvider — fetch and process WMTS tiles into raster tiles.

Uses the WmtsSource's internal WMTSDownloader to fetch tiles on demand.
No batch download is needed — tiles are fetched per-request during export.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from cartoload.processor.provider import LayerProvider, register_provider

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig
    from cartoload.downloader.source import Source

logger = logging.getLogger(__name__)


class WmtsProvider(LayerProvider):
    """Provider for WMTS tile service data.

    Lifecycle:
    1. download(): Initialize the WMTS downloader (no actual download)
    2. prepare(): No-op (tiles are fetched on demand)
    3. to_raster(): Fetch a single tile and return as RGBA Image
    """

    def __init__(
        self,
        source: Source,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ):
        super().__init__(source, source_config, layer_config, cache_dir)
        self._downloader = None

    @property
    def supported_extensions(self) -> list[str]:
        return [".jpeg", ".jpg", ".png"]

    def download(
        self,
        *,
        offline: bool = False,
        update: bool = False,
        max_age_days: int | None = None,
    ) -> list[Path]:
        from cartoload.downloader.wmts_source import WmtsSource

        assert isinstance(self.source, WmtsSource)

        # Initialize the downloader (stored internally in WmtsSource)
        self.source.download(
            self.source_config,
            self.layer_config,
            self.cache_dir,
            offline=offline,
            update=update,
            max_age_days=max_age_days,
        )
        self._downloader = self.source.get_downloader(
            self.source_config, self.layer_config, self.cache_dir
        )
        return [self._downloader.source_cache_dir]

    def prepare(self) -> None:
        # WMTS tiles are fetched on demand — no pre-processing needed
        pass

    def to_raster(self, x: int, y: int, z: int) -> Image.Image | None:
        if self._downloader is None:
            return None

        # Download the tile (uses cache if available)
        tile_path = self._downloader.download_tile(x, y, z)

        if not tile_path.exists() or tile_path.stat().st_size == 0:
            return None

        try:
            img = Image.open(tile_path)
            # Ensure RGBA mode for compositing
            if img.mode == "RGB":
                img = img.convert("RGBA")
            elif img.mode != "RGBA":
                img = img.convert("RGBA")
            return img
        except Exception as e:
            logger.warning("Failed to load WMTS tile (%d, %d, z=%d): %s", x, y, z, e)
            return None

    @property
    def downloader(self):
        """The underlying WMTSDownloader (for direct tile access)."""
        return self._downloader


# Register built-in provider
register_provider("wmts", WmtsProvider)
