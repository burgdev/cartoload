## Context

The `build_composite_layer` function in `pipeline.py` orchestrates multi-layer builds by downloading and compositing sub-layers. It currently handles `geotiff` (via STAC download + pre-warped mosaic) and `wmts` (via cached tiles). The `build_gpkg_layer` function handles standalone gpkg layers by downloading GPKG files from STAC, rasterizing vector features onto transparent PNG tiles using `VectorRasterizer` + `StyleEngine`, and then exporting.

These two code paths have never been connected. The composite layer pipeline has no branch for gpkg sub-layers, causing the crash. The `ref:` sub-layer resolution in `config.py` already correctly merges source and style info from referenced layers, so all necessary config is available at runtime.

### Key existing components:
- `GPKGDownloader`: Downloads GPKG files from STAC collections (used by `build_gpkg_layer`)
- `VectorRasterizer.render_tile(z, x, y)`: Renders vector features onto a 256x256 RGBA tile, returns `Image | None`
- `StyleEngine.from_config(layer)`: Creates a style engine from layer config (rules/style)
- `_make_composite_processor`: Creates a tile processor that composites sub-layers per-tile

## Goals / Non-Goals

**Goals:**
- Support gpkg sub-layers in composite layers end-to-end: download, rasterize, composite
- Reuse existing `GPKGDownloader`, `VectorRasterizer`, and `StyleEngine` without modification
- Handle style rules from referenced layer configs (via `ref:` resolution)
- Support both `stac` and `path` source methods for gpkg sub-layers

**Non-Goals:**
- No changes to the `VectorRasterizer` or `StyleEngine` classes themselves
- No changes to config resolution logic (already works correctly)
- No new config file format or schema changes
- No optimization of gpkg rasterization performance (use existing single-threaded per-tile rendering)

## Decisions

### Decision 1: Pre-rasterize gpkg sub-layers during the download stage

**Choice**: Download GPKG files and pre-rasterize all needed tiles during the download stage of `build_composite_layer`, storing them in a cache directory (same pattern as standalone `build_gpkg_layer`).

**Alternative**: On-demand rasterization in the composite processor (render each tile as needed during export).

**Rationale**: Pre-rasterization matches the existing standalone gpkg pipeline and avoids introducing `VectorRasterizer` and `StyleEngine` instances into the composite processor closure. The rasterized tiles are small PNGs that can be loaded quickly during compositing. This also allows reuse of the existing progress reporting for rasterization.

### Decision 2: One VectorRasterizer + StyleEngine per gpkg sub-layer

**Choice**: Create a separate `VectorRasterizer` and `StyleEngine` for each gpkg sub-layer, using the sub-layer's resolved config for style rules.

**Rationale**: Each gpkg sub-layer may reference a different layer with different style rules and different GPKG source files. A single shared rasterizer would require complex config merging.

### Decision 3: Pass gpkg raster cache paths via a dict similar to `stac_mosaics`

**Choice**: Use a `dict[int, Path]` mapping sub-layer index to the raster cache directory (parallel to the existing `stac_mosaics: dict[int, Path]`).

**Rationale**: Minimal API change. The composite processor already receives `stac_mosaics` — adding `gpkg_raster_dirs` follows the same pattern. The processor checks `gpkg_raster_dirs` for gpkg sub-layers and loads the pre-rasterized PNG.

### Decision 4: Style resolution from referenced layer configs

**Choice**: When a gpkg sub-layer uses `ref:` to reference a layer, the style rules are already resolved into the sub-layer during config loading (`resolve_sub_layer_refs`). Pass the sub-layer's resolved config to `StyleEngine.from_config()`.

**Rationale**: No new resolution logic needed. The `ref:` mechanism already copies `rules` and `style` from the referenced layer into the sub-layer config.

## Risks / Trade-offs

- **[Memory]** Multiple `VectorRasterizer` instances could consume memory for large GPKG files → Mitigation: Each rasterizer is used sequentially and garbage-collected after pre-rasterization. Only the PNG cache files persist.
- **[Performance]** Pre-rasterizing all gpkg tiles adds time to the download stage → Mitigation: Acceptable trade-off for simplicity. The existing standalone pipeline already rasterizes all tiles upfront. Can be optimized later with on-demand rendering if needed.
- **[Style rules on sub-layers]** Inline sub-layers (no `ref:`) won't have style rules → Mitigation: Log a warning and skip rasterization for gpkg sub-layers without style rules. This matches the standalone `build_gpkg_layer` behavior.
