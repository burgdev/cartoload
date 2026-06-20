## Context

Cartoload produces Garmin IMG files from map tiles. Tiles are 256×256 JPEG images that go through multiple pipeline stages (download, warp, composite, export). The `--quality` flag controls JPEG compression in the final output.

Currently, JPEG quality is applied at multiple points: `warp_tile_to_jpeg()`, `encode_composite_to_jpeg()`, the GeoTIFF reader (hardcoded 85), and `_reencode_jpeg()` in the final write. When quality is low (e.g. 30), JPEG's 8×8 DCT blocks at tile edges produce visible ringing artifacts because they lack neighbor pixel context. Adjacent tiles encode their edges independently, creating mismatched seams.

## Goals / Non-Goals

**Goals:**
- Eliminate visible border artifacts between adjacent tiles at low quality settings (≤50)
- Apply JPEG quality reduction exactly once, at the final IMG write step
- Keep the fix simple: mirror-padding with encode-crop-reencode in `_reencode_jpeg()`

**Non-Goals:**
- Lossless JPEG cropping via libjpeg-turbo's `tjTransform` (would avoid the reencode but requires C bindings)
- Variable margin sizes based on quality level (fixed 16px is sufficient)
- Changing tile dimensions or the Garmin IMG tile storage format

## Decisions

### 1. Mirror-pad in `_reencode_jpeg()` only

**Decision**: The border fix goes in `_reencode_jpeg()` in `garmin_img_writer.py`, the single universal choke point where all tiles get final quality encoding.

**Rationale**: Every tile passes through this function during the IMG write pass. No matter the provider (WMTS, GeoTIFF, GPKG, composite), the fix applies uniformly.

**Alternatives considered**:
- Per-provider padding: More complex, scattered across the codebase, easy to miss a path.
- Pad during warp: Only helps WMTS tiles, not GeoTIFF/composite paths.

### 2. Mirror reflection for edge padding

**Decision**: Use PIL's `ImageOps.expand()` with mirror reflection to create a 16px border on all sides before encoding.

**Rationale**: Mirror padding provides smooth continuation of edge pixels, giving DCT blocks neighbor context. It doesn't require fetching actual neighbor tiles, keeping the implementation simple and dependency-free.

**Alternatives considered**:
- Neighbor tile fetching: More accurate but complex (need to find/load adjacent tiles from cache).
- Zero/black padding: Worse than no padding — creates a sharp discontinuity that amplifies artifacts.

### 3. Fixed 16px margin

**Decision**: Always pad by 16 pixels (2 JPEG MCU blocks) regardless of quality level.

**Rationale**: At quality=30, DCT ringing typically extends 8-16 pixels. 16px provides a safe margin. For higher qualities (e.g. 85), the padding adds negligible overhead since the encode-crop-reencode cost is small.

### 4. Quality consolidation — intermediate steps always use quality 85

**Decision**: All intermediate pipeline stages encode at quality 85 (high quality). Only `_reencode_jpeg()` applies the user's target quality.

**Rationale**: Eliminates multiple lossy encode-decode cycles. Currently a tile can be encoded at quality X during warp, then re-encoded at quality Y during the final write — two rounds of DCT quantization for no benefit. With consolidation, each pixel is quantized exactly once.

**Affected paths**:
- `rasterio_warp.py`: `warp_tile_to_jpeg()` always encodes at 85 internally.
- `compositor.py`: `encode_composite_to_jpeg()` always encodes at 85.
- `unified_pipeline.py`: Removes quality propagation to intermediate processors.

## Risks / Trade-offs

- **[Double encode overhead]** → The encode-padded-crop-reencode cycle adds ~2x encoding cost per tile. Acceptable because the final write is I/O-bound and the padded encode is on a small (288×288) image. Mitigated by only applying when quality < 85.
- **[Residual step-6 artifacts]** → The final re-encode after cropping still creates new edge blocks without neighbor context. However, these are significantly smaller than the original artifacts because the input pixels are already smooth (they came from the interior of the padded encode). At quality=30, the visual improvement should be substantial.
- **[Larger intermediate tiles]** → Consolidating to quality 85 everywhere means intermediate tiles are larger. Since these are in-memory (not persisted), this is not a concern.
