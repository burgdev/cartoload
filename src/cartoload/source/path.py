"""PathSource — resolve and verify local file paths.

For layers that use data already present on the local filesystem
(e.g. previously downloaded GeoTIFFs, local GPKG files). No download
is needed — the source just validates that the path exists and returns it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cartoload.source.base import Source, register_source
from cartoload.template import expand

if TYPE_CHECKING:
    from cartoload.config import LayerConfig, SourceConfig

logger = logging.getLogger(__name__)


class PathSource(Source):
    """Source for local filesystem paths.

    No actual downloading occurs. The source resolves the path (using
    template variables if needed) and checks that the files exist.
    """

    @classmethod
    def can_handle(cls, source_config: SourceConfig) -> bool:
        return source_config.type == "path"

    def download(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
        *,
        offline: bool = False,
        update: bool = False,
        max_age_days: int | None = None,
    ) -> list[Path]:
        """Resolve and verify local paths.

        Returns:
            List of paths to existing files matching the source config.
        """
        paths = self._resolve_paths(source_config, layer_config)
        existing = [p for p in paths if p.exists()]

        if not existing:
            # Log the attempted paths for debugging
            for p in paths:
                logger.warning("Local path does not exist: %s", p)

        return existing

    def is_cached(
        self,
        source_config: SourceConfig,
        layer_config: LayerConfig,
        cache_dir: Path,
    ) -> bool:
        """Check if the local path exists."""
        paths = self._resolve_paths(source_config, layer_config)
        return any(p.exists() for p in paths)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_paths(
        source_config: SourceConfig,
        layer_config: LayerConfig,
    ) -> list[Path]:
        """Resolve source URLs to local paths.

        Applies template variable substitution and resolves relative paths
        against the config file directory.
        """
        if not source_config.urls:
            return []

        variables = {
            **source_config.defaults,
            **layer_config.source_args,
        }

        # Config directory for relative path resolution
        config_dir = source_config.config_dir or layer_config.config_dir or "."

        paths = []
        for url in source_config.urls:
            resolved = expand(url, variables)

            # Resolve relative paths against config directory
            p = Path(resolved)
            if not p.is_absolute():
                p = Path(config_dir) / p

            # If the path is a directory, expand to contained files
            if p.is_dir():
                fmt = layer_config.format or "geotiff"
                if fmt == "geotiff":
                    paths.extend(sorted(p.glob("**/*.tif")))
                    paths.extend(sorted(p.glob("**/*.tiff")))
                elif fmt == "gpkg":
                    paths.extend(sorted(p.glob("**/*.gpkg")))
                else:
                    paths.extend(sorted(p.iterdir()))
            else:
                paths.append(p)

        return paths


# Register built-in source
register_source("path", PathSource)
