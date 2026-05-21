## Why

When building IMG files with low JPEG quality (e.g. 30), visible border artifacts appear between adjacent tiles. JPEG's 8×8 DCT blocks at tile edges have no neighbor context, causing quantization ringing that doesn't match the adjacent tile's edge encoding. Additionally, quality is currently applied at multiple encoding steps in the pipeline (warp, compositing, GeoTIFF reading, final write), causing unnecessary quality degradation through repeated encode-decode cycles.

## What Changes

- **Mirror-pad tiles before quality encoding**: Before encoding a tile at low quality, mirror-reflect the edges by 16px, encode the padded image, decode it, then crop to the original 256×256. This gives DCT blocks at the true tile boundary smooth neighbor context, eliminating visible seam artifacts.
- **Consolidate quality to a single application point**: All intermediate pipeline stages (warp, compositing, GeoTIFF reading) will produce tiles at high quality (85). The target quality is applied only during the final IMG write step in `_reencode_jpeg()`. This eliminates multiple lossy encode-decode cycles.

## Capabilities

### New Capabilities
- `jpeg-border-padding`: Mirror-pad tiles before low-quality JPEG encoding to eliminate DCT edge artifacts at tile boundaries.

### Modified Capabilities
- `fix-composite-quality`: Extends the existing quality consolidation to cover all pipeline stages (not just compositing), ensuring quality is applied exactly once at the final write step.

## Impact

- **`src/cartoload/exporters/garmin_img_writer.py`**: `_reencode_jpeg()` gains mirror-pad logic. All intermediate encoding already uses high quality.
- **`src/cartoload/processor/rasterio_warp.py`**: `warp_tile_to_jpeg()` quality parameter becomes internal-only (always 85), no longer propagated from CLI.
- **`src/cartoload/processor/geotiff_provider.py`**: Already uses hardcoded quality=85 — no functional change needed.
- **`src/cartoload/processor/compositor.py`**: `encode_composite_to_jpeg()` always uses high quality; target quality deferred to final write.
- **`src/cartoload/processor/unified_pipeline.py`**: Intermediate quality parameters removed or fixed to high quality; only the final write receives the target quality.
