## Context

Analysis of the SwissTopo reference IMG file revealed that its RGN2 bitstream encoding is fundamentally different from our implementation:

**SwissTopo bitstream** (level 22, shift=2, tile ~576x400 MU):
- 3 points forming an L-shaped marker
- Deltas: (288, 0) then (0, -12) — in shifted coordinates
- After applying shift: boundingRect is ~1152 x 48 MU
- Just a coarse position marker for `copyPolys()` filtering

**Our implementation**:
- 2 points forming a line from bottom-left to top-right
- Single delta: (+width_ls, +height_ls) — covering the full tile
- After applying shift: boundingRect is ~580 x 404 MU
- Tries to cover the full tile but is a different format than the reference

GPXSee's rendering pipeline:
1. R-tree query finds subdivisions whose TRE2 bounds overlap the view
2. For matching subdivisions, iterate RGN2 records and compute boundingRect from deltas
3. `copyPolys()` filters tiles whose boundingRect intersects the view
4. Render matching tiles using absolute 32-bit bounds from `readRasterInfo()`

Both header deltas and bitstream deltas are shifted by `LS(delta, 24-bits)` (confirmed rgnfile.cpp:851).

## Goals / Non-Goals

**Goals:**
- Match the SwissTopo bitstream format (proven to work)
- Fix subdivision bounds to cover all assigned tiles
- Minimize quantization error by centering subdivisions on actual tile positions

**Non-Goals:**
- Switching to JNX format
- Modifying GPXSee's rendering
- Changing the subdivision hierarchy structure

## Decisions

### Decision 1: Match SwissTopo's 3-point L-shaped bitstream

**Choice**: Encode 2 delta pairs forming an L-shape: (+half_width, 0) then (0, +half_height), where each half is approximately half the tile dimension in shifted coordinates.

**Rationale**: This matches the SwissTopo reference file exactly. SwissTopo uses deltas like (288, 0) and (0, -12) for tiles of ~576x400 MU. The exact values encode the tile extent direction — the first delta moves right, the second moves up/down, forming an L that creates a boundingRect marker near the tile position. Since this is proven in millions of devices, matching it is the safest approach.

**Implementation**: In `_encode_tile_bitstream()`, change from 1 delta pair (+width, +height) to 2 delta pairs (+width/2, 0) and (0, +height/2). Adjust the info byte to use smaller baseSize since each individual delta is smaller.

### Decision 2: Compute subdivision bounds from actual tile positions

**Choice**: Use min/max of assigned tiles' geographic bounds for subdivision `bounds_west/east/north/south`, not grid cell boundaries.

**Rationale**: Grid cell boundaries are computed from a regular grid that may not align with tile positions. Tiles near cell boundaries may have boundingRects extending beyond the grid cell, causing the R-tree to miss them. Using actual tile bounds ensures full coverage.

### Decision 3: Compute subdivision center from tile midpoint

**Choice**: `center = (min_tile_bound + max_tile_bound) / 2` for each axis.

**Rationale**: The grid cell center may not align with the centroid of tiles assigned to that cell. A misaligned center increases delta magnitudes, amplifying quantization error. Centering on tile bounds minimizes this.

## Risks / Trade-offs

- **[Format correctness]**: The 3-point L-shape must produce a valid boundingRect that intersects the view when the tile should be visible. → Mitigation: SwissTopo uses this exact format successfully.

- **[baseSize recalculation]**: With 2 smaller deltas instead of 1 large one, the bit budget per delta changes. Need to verify the total fits in 56 bits. → Mitigation: Each delta is ~half the tile size, so baseSize may be smaller. 2 pairs at smaller baseSize should fit.

- **[Regression]**: Changing the bitstream format affects all levels. → Mitigation: Existing tests verify bitstream decoding; add tests for the new format matching SwissTopo patterns.
