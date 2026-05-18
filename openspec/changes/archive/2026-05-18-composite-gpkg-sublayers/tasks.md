## 1. Download Stage — GPKG sub-layer support in `build_composite_layer`

- [ ] 1.1 Add a `gpkg` branch in the download loop of `build_composite_layer` (alongside existing `geotiff` and `wmts` branches) that handles `sub_source.type == "gpkg"` by downloading GPKG files via `GPKGDownloader` (for `source_method: stac`) or resolving local paths (for `source_method: path`), reusing the same logic from `build_gpkg_layer`
- [ ] 1.2 Verify: the download branch correctly raises `DownloadError` on failure (not `PipelineError`), matching the existing error handling pattern

## 2. Pre-rasterization — Rasterize gpkg sub-layers after download

- [ ] 2.1 After the download loop, add a pre-rasterization loop (parallel to the existing STAC mosaic build loop) that iterates over gpkg sub-layers, creates a `StyleEngine` and `VectorRasterizer` per sub-layer, and calls `render_tiles` to write rasterized PNGs to a cache directory
- [ ] 2.2 Store the raster cache directory paths in a `dict[int, Path]` (e.g., `gpkg_raster_dirs`) keyed by sub-layer index, similar to `stac_mosaics`
- [ ] 2.3 Log a warning and skip sub-layers that have no style rules (no `rules` or `style` resolved from the ref layer)

## 3. Composite Processor — Load and composite gpkg tiles

- [ ] 3.1 Add `gpkg_raster_dirs` parameter to `_make_composite_processor`
- [ ] 3.2 In the composite processor's per-tile loop, add a branch for gpkg sub-layers (after the STAC mosaic and WMTS branches) that loads the pre-rasterized PNG from the cache directory and uses it as an RGBA image for compositing
- [ ] 3.3 Handle missing tiles gracefully (skip sub-layer for that coordinate — treat as transparent)
- [ ] 3.4 Apply opacity from sub-layer config before compositing, matching the existing opacity handling for other sub-layer types

## 4. Error handling and edge cases

- [ ] 4.1 Remove the misleading else branch that raises "not supported" for gpkg and instead let it only trigger for truly unsupported types, or update the error message to be accurate
- [ ] 4.2 Verify zoom level filtering works correctly for gpkg sub-layers (only rasterize and composite tiles at configured zoom levels)

## 5. Testing

- [ ] 5.1 Add a unit test for the gpkg download branch in `build_composite_layer` (mock `GPKGDownloader`, verify it is called with correct parameters for stac and path source methods)
- [ ] 5.2 Add a unit test for the pre-rasterization loop (verify `VectorRasterizer.render_tiles` is called with correct bounds and zoom levels for each gpkg sub-layer)
- [ ] 5.3 Add a unit test for the composite processor gpkg branch (verify pre-rasterized PNGs are loaded and composited with correct opacity)
- [ ] 5.4 Add a test verifying that a gpkg sub-layer without style rules logs a warning and is skipped
- [ ] 5.5 Run existing test suite (`just test`) and verify no regressions
