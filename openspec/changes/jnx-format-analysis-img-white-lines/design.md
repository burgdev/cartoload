## Context

The Garmin IMG raster format positions tiles within spatial subdivisions using delta-encoding relative to subdivision centers. This differs fundamentally from the JNX format (Garmin's BirdsEye imagery format), where each tile has an independent 32-bit bounding rectangle with no quantization.

**Current architecture**: Tiles are positioned via:
1. RGN2 header deltas (int16 `lon_delta`/`lat_delta`) — tile position relative to subdivision center, right-shifted by `24 - level_number`
2. DeltaStream bitstream — tile extent from bottom-left to top-right, also in shifted units
3. TRE2 width/height — subdivision extent, also shifted
4. GPXSee reconstructs a boundingRect from (1)+(2) for tile filtering

**The problem**: The shift operation `>> (24 - level_number)` introduces quantization error. At lower level_numbers, the quantization step can exceed tile dimensions, causing:
- Tile boundingRect points to fall outside the view → tiles filtered out → white gaps
- Adjacent tiles' boundingRects to not meet → white lines between them
- Tiles near subdivision boundaries to be excluded → missing edge tiles

**JNX comparison**: JNX avoids this entirely — each tile has absolute 32-bit bounds, no subdivision scheme, no delta encoding. QMapShack's JNX reader even has explicit gap detection that switches to a high-quality rendering mode when gaps exceed 2 pixels.

## Goals / Non-Goals

**Goals:**
- Eliminate white lines/gaps at all zoom levels in generated IMG raster files
- Ensure boundingRects of adjacent tiles always overlap (never gap)
- Ensure tiles near subdivision boundaries are correctly included in filtering
- Document the JNX format comparison and quantization behavior

**Non-Goals:**
- Switching to JNX format (we need IMG for Garmin device compatibility)
- Modifying GPXSee's rendering code (we control only the writer)
- Changing the overall subdivision hierarchy structure
- Supporting Garmin vector map features

## Decisions

### Decision 1: Extend bitstream boundingRect with quantization margin

**Choice**: Add a quantization-safe overlap margin to the bitstream delta encoding, extending the boundingRect beyond the actual tile bounds.

**Rationale**: The boundingRect is GPXSee's primary filter for tile visibility. If two adjacent tiles have boundingRects that barely touch or have a 1-unit gap (due to quantization rounding), GPXSee's `intersects()` check can exclude one tile. Extending each boundingRect by 1 quantization step in each direction ensures overlap regardless of rounding direction.

**How**: In `_encode_tile_bitstream()`, add 1 to `width_ls` and `height_ls` after the shift operation. This extends the boundingRect by one quantization step past the tile's actual right/top edge, ensuring overlap with the next tile.

**Alternative considered**: Use overlapping tile images — rejected because JPEG tiles are independent and overlap would require duplicating/compositing pixel data.

### Decision 2: Extend TRE2 subdivision bounds to cover all assigned tiles

**Choice**: When computing subdivision width/height for TRE2, ensure the bounds cover all assigned tiles' quantized positions, not just the grid cell.

**Rationale**: The grid cell bounds are computed from a regular geographic grid, but tiles near cell boundaries may have their boundingRect extend slightly beyond the grid cell due to quantization rounding. If the TRE2 bounds don't cover this extension, GPXSee's R-tree query won't find the subdivision for those view rects, causing missing tiles at cell boundaries.

**How**: In `encode_tre2_width()`/`encode_tre2_height()`, compute bounds from actual tile positions rather than grid cell bounds. Use the min/max of assigned tiles' geographic bounds, rounded outward to account for quantization.

**Alternative considered**: Make grid cells overlap — rejected because it complicates tile assignment and can cause duplicate rendering.

### Decision 3: Ensure subdivision center is at the midpoint of actual tile bounds

**Choice**: Compute subdivision center from the geometric midpoint of assigned tiles' bounds, not from the grid cell center.

**Rationale**: The grid cell center may not align with the centroid of the tiles assigned to that cell (especially when tiles at cell boundaries are assigned to one side). A misaligned center increases the magnitude of lon_delta/lat_delta, which increases the impact of quantization error. Centering on actual tile bounds minimizes delta magnitudes.

**How**: In `_assign_tiles_to_grid()`, compute `center_lat`/`center_lon` from the average of min/max tile bounds in the cell, not from the geometric center of the grid cell.

### Decision 4: Add JNX format comparison to documentation

**Choice**: Add a dedicated section to `garmin-img.md` comparing JNX and IMG raster positioning models.

**Rationale**: The JNX format analysis provided key insights into why the IMG subdivision approach is prone to gaps. Documenting this comparison helps future developers understand the trade-offs and avoid similar issues.

## Risks / Trade-offs

- **[Slight boundingRect over-coverage]**: Extending boundingRects by 1 quantization step means GPXSee may draw some tiles that are just outside the view. This is harmless — the rendering uses the absolute 32-bit bounds for positioning, so the image is placed correctly regardless of boundingRect extent. → Mitigation: The over-coverage is at most 1 quantization step (typically < 0.001°), negligible for rendering.

- **[Increased TRE2 extent]**: Using tile-derived bounds instead of grid cell bounds may increase subdivision extent slightly. → Mitigation: The increase is bounded by tile size plus 1 quantization step. TRE2 width/height clamping to 0x7FFF handles overflow.

- **[Regression in existing levels]**: Changing the bitstream encoding may affect levels that currently render correctly. → Mitigation: All 104 existing tests pass; new tests verify overlap at all level_numbers. Visual testing required after implementation.
