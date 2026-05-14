## Why

Currently each layer is built independently from a single source into its own IMG file. There is no way to overlay multiple raster layers (e.g., ski routes over a basemap, hiking trails over topography) into a single composite tile set. Users must produce separate IMG files and manually toggle them on their device. Compositing multiple layers into one IMG file would produce more useful, information-rich maps with a single build step.

## What Changes

- **New config syntax**: Introduce a `layers` sub-field on `LayerConfig` that contains an ordered list of sub-layers. Each sub-layer is either an inline raster definition (with its own `source`, `wmts_layer`, `zoom_levels`, `opacity`, `extension`) or a `ref` to an existing top-level layer. The first sub-layer is the base (bottom), subsequent ones are composited on top in order.
- **Multi-source tile fetching**: The pipeline must download tiles from multiple sources (potentially different WMTS services, different tile grids) and align them geographically.
- **Alpha compositing**: A new compositing step merges multiple raster tiles into a single output tile per (x, y, z) position. Sub-layers support per-layer `opacity` (float 0.0–1.0, uniform or zoom-level-based). PNG tiles (with transparency) must be read and correctly blended.
- **Unified tile grid**: The composite layer's tile grid is the union of all sub-layer zoom levels. Sub-layers that don't cover a given zoom level are simply absent at that zoom.
- **Streaming-compatible output**: The composite result feeds into the existing `StreamingIMGWriter` pipeline unchanged — the compositing step produces JPEG bytes just like the current single-source path.
- **No changes to single-layer pipeline**: Existing layer configs (without the `layers` sub-field) work identically. This is purely additive.

## Capabilities

### New Capabilities
- `layer-compositing`: Alpha compositing of multiple raster sub-layers into a single tile, with per-layer opacity control and PNG transparency support
- `composite-layer-config`: Config model for composite layers — inline sub-layer definitions, references to existing layers, per-sub-layer overrides (zoom_levels, opacity, extension, quality)

### Modified Capabilities
- `fast-img-pipeline`: Modified to support composite layers — when a layer has sub-layers, the pipeline fetches from multiple sources and composites before writing to IMG instead of reading from a single source
- `direct-tile-writer`: Modified to accept composited JPEG bytes from the compositing step (the writer itself is unchanged, but the source of tile data changes)
- `rasterio-warp-processor`: Modified to handle PNG input tiles in addition to JPEG, since overlay layers (ski routes, hiking trails) are commonly served as PNG with transparency

## Impact

- **Config model** (`src/cartoload/config.py`): New `CompositeSubLayer` dataclass, `LayerConfig` gains optional `layers` field, validation logic for composite layers
- **Pipeline** (`src/cartoload/pipeline.py`): New composite-aware `build_layer` path that downloads from multiple sources and invokes compositing
- **New module** (`src/cartoload/processor/compositor.py`): Tile compositing logic using PIL alpha blending
- **Warp processor** (`src/cartoload/processor/rasterio_warp.py`): PNG input support for tiles that need reprojection
- **Downloader** (`src/cartoload/downloader/wmts.py`): No changes — already supports different sources independently
- **IMG writer** (`src/cartoload/exporters/garmin_img_writer.py`): No changes — consumes JPEG bytes as before
- **Dependencies**: No new dependencies (PIL/Pillow and rasterio already used)
