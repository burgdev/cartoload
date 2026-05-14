## 1. Config Model

- [x] 1.1 Add `CompositeSubLayer` dataclass to `config.py` with fields: `source`, `wmts_layer`, `zoom_levels`, `extension`, `opacity`, `ref`, `quality`, and helper method `is_resolved()`
- [x] 1.2 Add optional `layers: list[CompositeSubLayer] | None` field to `LayerConfig`
- [x] 1.3 Add parsing logic for sub-layers in `load_layers_file()` — handle inline sub-layers (with `source`) and ref sub-layers (with `ref`), with optional overrides
- [x] 1.4 Add validation: inline sub-layers require `source`, refs must resolve to existing top-level layers, no composite-to-composite refs, opacity range 0.0–1.0, per-zoom opacity dict validation
- [x] 1.5 Add `resolve_sub_layer_refs()` function that resolves `ref` entries by merging the referenced layer's fields with the sub-layer's overrides into a fully resolved `CompositeSubLayer`
- [x] 1.6 Update `load_config()` to call ref resolution after loading all layers, and relax the `source` required-field check for composite layers (source comes from sub-layers)

## 2. Compositor Module

- [x] 2.1 Create `src/cartoload/processor/compositor.py` with `composite_tiles()` function that takes a list of PIL Images with their opacities and returns a composited PIL Image
- [x] 2.2 Implement painter's algorithm: iterate sub-layers bottom-to-top, apply per-layer opacity (multiply alpha channel), alpha-composite onto canvas
- [x] 2.3 Implement `resolve_opacity(sub_layer, zoom)` helper that returns the float opacity for a given sub-layer at a given zoom level (uniform float, per-zoom dict, or default 1.0)
- [x] 2.4 Implement `encode_composite_to_jpeg(image, quality)` that converts RGBA to RGB and encodes as JPEG bytes
- [x] 2.5 Implement tile fallback logic: `find_fallback_tile(sub_layer, x, y, zoom)` that searches the sub-layer's cache for the closest lower zoom tile covering the same position and returns an upscaled PIL Image
- [x] 2.6 Add unit tests for compositing: two opaque layers, opacity blending, PNG transparency, per-zoom opacity, fallback upscaling, missing sub-layer tile with and without fallback

## 3. PNG Input Support in Warp Processor

- [x] 3.1 Update `warp_tile_to_jpeg()` in `rasterio_warp.py` to detect PNG input files and read all bands (including alpha) with rasterio
- [x] 3.2 Add `warp_tile_to_rgba()` variant that returns a PIL RGBA Image instead of JPEG bytes (used by compositing path when reprojection is needed)
- [x] 3.3 Ensure PNG passthrough (EPSG:4326 source) reads the PNG as RGBA PIL Image directly without rasterio
- [x] 3.4 Add unit tests for PNG reprojection: RGBA preserved, RGB treated as opaque, passthrough path

## 4. Composite Pipeline Integration

- [x] 4.1 Add `is_composite()` helper to `LayerConfig` (returns True if `layers` field is non-empty)
- [x] 4.2 Add `build_composite_layer()` function to `pipeline.py` that handles the composite flow: resolve sub-layers → download per sub-layer → composite per tile position → export
- [x] 4.3 Implement per-sub-layer download: iterate sub-layers, create downloader for each, download to separate cache paths (keyed by sub-layer source)
- [x] 4.4 Implement composite tile metadata: for each zoom level, compute the union of tile coordinates across sub-layers that contribute to that zoom
- [x] 4.5 Implement per-tile compositing in the export path: for each tile position, load available sub-layer tiles as PIL Images (reprojecting if needed), call compositor, encode to JPEG, feed to streaming writer
- [x] 4.6 Wire `build_layer()` to dispatch to `build_composite_layer()` when `layer.is_composite()` is True, otherwise use existing single-source path

## 5. Documentation

- [x] 5.1 Update layer configuration docs to document composite layers syntax (the `layers` sub-field, inline vs ref sub-layers, opacity, extension)
- [x] 5.2 Add a composite layer example to the getting-started guide or configuration reference
- [x] 5.3 Update CLI docs if any new flags or behavior changes affect the build command

## 6. End-to-End Testing

- [x] 6.1 Create example composite layer config in `examples/configs/layers/` with basemap + overlay
- [ ] 6.2 Test composite build with the test build command (`cartoload build -S ... -L ... -l <composite_layer>`)
- [ ] 6.3 Verify single-layer configs still build correctly (regression test)
- [ ] 6.4 Verify composite IMG output renders correctly on device or in `cartoload analyze img info`
