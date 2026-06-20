## Why

Cartoload's composite pipeline can blend transparent overlay tiles onto a base map. To use vector data (skitours, hiking routes) as raster overlays, we need to render GeoPackage features onto transparent PNG tiles that the composite pipeline can consume. This is Path B of the vector data integration strategy.

## What Changes

- New `VectorRasterizer` that reads features from GPKG, applies style engine rules, and draws lines onto transparent PNG tiles
- Tile-based rendering: for each (z, x, y) tile, read intersecting features, project to pixel coordinates, draw styled lines
- Line rendering with Pillow: solid lines, dashed lines, border/casing support
- Output transparent PNG tiles in the existing cache directory structure (z/x/y.png)
- Integration with the composite pipeline as an overlay sub-layer
- New dependency: Pillow

## Capabilities

### New Capabilities
- `vector-rasterizer`: Render vector features from GeoPackage onto transparent PNG tiles using the style engine, compatible with the composite pipeline

### Modified Capabilities

## Impact

- **New module**: `src/cartoload/processor/vector_rasterizer.py`
- **Pipeline**: New processing path for `gpkg` sources with `raster_overlay` role
- **Dependency**: Pillow added as a project dependency
- **Upstream**: Consumes output from `gpkg-download` and `vector-style-engine` changes
