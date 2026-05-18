## Why

Composite layers currently only support `geotiff` (via STAC) and `wmts` sub-layers. When a composite layer includes a `gpkg` sub-layer (e.g., hiking trails, skiroutes, steepness overlays), the pipeline crashes with a contradictory error: "Composite sub-layer source type 'gpkg' is not supported. Supported types: wmts, geotiff, gpkg". The gpkg source type is fully supported for standalone layers but was never wired into the composite layer download and processing pipeline.

## What Changes

- Add gpkg download support in `build_composite_layer`: download GPKG files from STAC (or resolve local paths) for gpkg sub-layers, reusing the existing `GPKGDownloader` and path resolution logic from `build_gpkg_layer`.
- Add gpkg rasterization support in `_make_composite_processor`: use `VectorRasterizer` and `StyleEngine` to render vector features onto transparent tiles that can be composited with other sub-layers.
- Resolve style rules for gpkg sub-layers from the referenced layer config (via `ref:` resolution) or inline rules on the sub-layer.
- Fix the misleading error message.

## Capabilities

### New Capabilities
- `composite-gpkg-sublayers`: Download and rasterize GPKG vector sub-layers within composite layers, compositing the rendered tiles with raster sub-layers.

### Modified Capabilities
- `source-method-resolution`: Extend pipeline dispatch to handle gpkg source type within the composite layer code path (in addition to standalone layers already supported).

## Impact

- **`src/cartoload/pipeline.py`**: `build_composite_layer` (download stage), `_make_composite_processor` (processing stage), and any helper functions for gpkg sub-layer resolution.
- **`src/cartoload/processor/vector_rasterizer.py`**: May need minor adjustments to support per-tile rasterization in a composite context.
- **`src/cartoload/style.py`**: Style engine needs to be instantiable per gpkg sub-layer within composites.
- **`examples/configs/layers/test.yaml`**: The `ch_stac` layer already references gpkg sub-layers; no config changes needed.
- **Tests**: New test coverage for gpkg sub-layers in composite layers.
