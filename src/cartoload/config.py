from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceConfig:
    """Configuration for a geodata source (WMTS, GeoTIFF/STAC, etc.)."""

    id: str
    type: str  # wmts, geotiff, gpkg, geojson, pbf
    url_template: str | None = None
    stac_url: str | None = None
    attribution: str = ""
    rate_limit_ms: int = 150
    max_threads: int = 4


@dataclass
class LayerConfig:
    """Configuration for a map layer to build."""

    id: str
    name: str
    description: str = ""
    type: str = "raster"  # raster, raster_overlay, vector
    source: str = ""
    wmts_fallback: str | None = None
    wmts_layer: str | None = None
    geotiff_product: str | None = None
    zoom_levels: list[int] = field(default_factory=list)
    exporter: str = "garmin_img"
    output: str = ""
    bounds: dict[str, float] | None = None
