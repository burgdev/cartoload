## 1. Bitstream Encoding — Full tile coverage (1 delta pair)

- [x] 1.1 Keep `_encode_tile_bitstream()` in `garmin_img_writer.py`: 1 delta pair (+width, +height) from P0 (tile bottom-left) to P1 (top-right), producing full-tile boundingRect
- [x] 1.2 Keep baseSize range up to 15 (no clamping) — 1 pair fits in 56 bits for all tile sizes
- [x] 1.3 L-shape approach rejected: baseSize clamped to 9 limits max delta to 2047, causing clamping for large tiles at shift=0

## 2. Subdivision Generation — Tile-derived Bounds

- [x] 2.1 Update `_assign_tiles_to_grid()` in `garmin_img.py`: compute subdivision center from midpoint of actual assigned tile bounds instead of grid cell center
- [x] 2.2 Update `_assign_tiles_to_grid()`: compute subdivision bounds from min/max of assigned tiles' geographic bounds, not grid cell boundaries
- [x] 2.3 Verify `encode_tre2_width()`/`encode_tre2_height()` in `garmin_img_model.py` handle tile-derived bounds correctly

## 3. Tests

- [x] 3.1 Add test verifying boundingRect covers full tile at all level_numbers (20-24)
- [x] 3.2 Add test verifying subdivision bounds cover all assigned tiles' positions
- [x] 3.3 Add test verifying subdivision center is computed from tile bounds, not grid cell center
- [x] 3.4 Run full test suite — all existing tests must pass

## 4. Documentation

- [x] 4.1 Add JNX format comparison section to `docs/exporters/garmin-img.md`
- [x] 4.2 Update Section 4.5.2 (DeltaStream Bitstream Encoding) with reference format comparison
- [x] 4.3 Update Section 6.3 (Raster Subdivision Format) to document tile-derived bounds
