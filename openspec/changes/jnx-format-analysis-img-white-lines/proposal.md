## Why

White lines (vertical and/or horizontal gaps) still appear on some zoom/scale levels in the generated Garmin IMG raster files. Tiles are correct but appear clipped or have lines over them.

Analysis of the JNX format and the SwissTopo IMG reference file revealed critical findings:

1. **JNX uses independent per-tile bounding rectangles** (32-bit, no quantization). The JNX→IMG conversion that produced SwissTopo re-encoded these as subdivision-relative 16-bit deltas — the IMG format requires this.
2. **SwissTopo's bitstream uses a tiny L-shaped marker** (3 points, ~1152 x 48 MU) rather than full tile coverage (~576 x 400 MU). The boundingRect from the bitstream is just a coarse position marker used by `copyPolys()` filtering. The absolute 32-bit bounds (top/right/bottom/left) handle actual rendering.
3. **GPXSee shifts BOTH header deltas and bitstream deltas** by `LS(delta, 24-bits)` — confirmed from `rgnfile.cpp` line 851. Our implementation encodes them correctly in shifted coordinates.
4. **The most likely white line cause** is the subdivision bounds (TRE2 width/height) not covering all assigned tiles' boundingRects. If the R-tree query doesn't find a subdivision for a given view area, tiles in that area are never checked.

## What Changes

- **Match SwissTopo bitstream format**: Change from 2-point full-coverage bitstream to SwissTopo's proven 3-point L-shaped marker encoding. This matches the reference file that renders correctly.

- **Fix subdivision bounds**: Compute subdivision bounds from actual assigned tile positions instead of grid cell boundaries, ensuring TRE2 extent covers all tiles' boundingRects.

- **Fix subdivision center**: Compute from tile midpoint instead of grid cell center, minimizing delta magnitudes and quantization impact.

- **Update documentation**: Add JNX format comparison section and update bitstream/boundingRect notes.

- **Add tests**: Verify boundingRect positioning at all level_numbers and subdivision coverage.

## Capabilities

### New Capabilities
- `raster-tile-gap-prevention`: Ensures raster tiles in Garmin IMG files are correctly positioned and filtered at all zoom levels by matching the SwissTopo reference bitstream format and fixing subdivision bounds.

### Modified Capabilities
- `rgn2-segment-encoding`: Update bitstream encoding to match SwissTopo's 3-point L-shaped format.

## Impact

- **Code**: `garmin_img_writer.py` (bitstream encoding), `garmin_img.py` (subdivision generation), `garmin_img_model.py` (TRE2 width/height encoding)
- **Tests**: `tests/test_exporter_garmin_img.py`
- **Documentation**: `docs/exporters/garmin-img.md`
