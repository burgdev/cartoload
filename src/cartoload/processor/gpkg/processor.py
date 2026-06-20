"""GpkgProcessor — process GeoPackage vector data into raster tiles.

Downloads GPKG files from STAC or local paths, rasterizes vector features
using StyleEngine + VectorRasterizer, and returns RGBA tiles on demand.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cartoload.processor.base import LayerProcessor, register_processor

if TYPE_CHECKING:
    from PIL import Image

    from cartoload.config import LayerConfig, SourceConfig
    from cartoload.processor.gpkg.vector_rasterizer import VectorRasterizer
    from cartoload.source.base import Source

logger = logging.getLogger(__name__)


class GpkgProcessor(LayerProcessor):
    """Processor for GeoPackage vector data.

    Lifecycle:
    1. download(): Fetch GPKG files via StacSource or PathSource
    2. prepare(): Initialize VectorRasterizer with style rules
    3. to_raster(): Render vector features onto transparent RGBA tiles
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
        self._rasterizer: VectorRasterizer | None = None

    @property
    def supported_extensions(self) -> list[str]:
        return [".gpkg"]

    def prepare(self) -> None:
        if not self._downloaded_paths:
            logger.warning(
                "GpkgProcessor.prepare(): no GPKG files for layer '%s'",
                self.layer_config.id,
            )
            return

        from cartoload.processor.gpkg.vector_rasterizer import VectorRasterizer

        # Build style engine from layer config
        style_engine = self._build_style_engine()

        self._rasterizer = VectorRasterizer(
            gpkg_paths=self._downloaded_paths,
            style_engine=style_engine,
            layer=self.layer_config.source_args.get("layer"),
        )

    def to_raster(self, x: int, y: int, z: int) -> Image.Image | None:
        if self._rasterizer is None:
            return None
        return self._rasterizer.render_tile(z, x, y)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_style_engine(self) -> "StyleEngine":  # noqa: F821  # ty: ignore[unresolved-reference]
        """Build a StyleEngine from the layer config's style rules."""
        from cartoload.style.engine import StyleEngine  # ty: ignore

        # Priority: inline rules > QML file > default
        if self.layer_config.rules:
            return StyleEngine(rules=self.layer_config.rules)

        if self.layer_config.style:
            # Resolve QML path relative to config dir
            qml_path = Path(self.layer_config.style)
            if not qml_path.is_absolute() and self.layer_config.config_dir:
                qml_path = Path(self.layer_config.config_dir) / qml_path

            if qml_path.exists():
                return StyleEngine.from_qml(
                    qml_path,
                    garmin_types=self.layer_config.garmin_types,
                )
            else:
                logger.warning("QML style file not found: %s, using default", qml_path)

        # Default: simple red lines
        return StyleEngine.default()


# Register built-in processor
register_processor("gpkg", GpkgProcessor)
