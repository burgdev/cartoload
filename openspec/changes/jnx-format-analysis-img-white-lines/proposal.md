## Why

White lines (vertical and/or horizontal gaps) still appear on some zoom/scale levels in the generated Garmin IMG raster files. Tiles are correct but appear clipped or have lines over them. A comparative analysis of the JNX format (which Garmin uses for BirdsEye imagery) reveals that JNX tiles have independent 32-bit bounding rectangles with no quantization — a fundamentally simpler positioning model than our IMG subdivision-based delta encoding. This analysis identifies where our delta-encoding and subdivision approach introduces gaps and proposes fixes.

## What Changes

- **Fix tile positioning quantization**: The RGN2 header deltas (lon_delta/lat_delta) and bitstream deltas use `shift = 24 - level_number`, introducing quantization that can shift tile boundingRect points away from actual tile edges. At certain level_numbers, the quantization step is large enough to create visible gaps between adjacent tiles. Fix by extending the bitstream boundingRect to add quantization-safe overlap margins.

- **Fix subdivision boundary clipping**: Tiles near subdivision grid boundaries may have their boundingRect point fall outside the subdivision's queryable extent due to quantization of the TRE2 width/height. Fix subdivision bounds to include a margin that covers all assigned tiles' quantized positions.

- **Update garmin-img.md documentation**: Add JNX format comparison section documenting the key differences in tile positioning models (independent bounds vs subdivision-relative deltas), and update the RGN2 raster record section with corrected quantization handling notes.

- **Add tests for white line scenarios**: Add tests verifying that adjacent tiles at all zoom levels produce overlapping boundingRects (no gaps) and that tiles near subdivision boundaries are correctly included.

## Capabilities

### New Capabilities
- `raster-tile-gap-prevention`: Ensures adjacent raster tiles in Garmin IMG files produce overlapping boundingRects at all zoom levels, preventing white line artifacts from quantization error in the subdivision delta-encoding.

### Modified Capabilities
- `garmin-img-raster`: Update raster tile positioning to add quantization-safe margins in bitstream encoding and subdivision bounds, ensuring no gaps at any level_number.

## Impact

- **Code**: `src/cartoload/exporters/garmin_img_writer.py` (bitstream encoding, RGN2 record writing), `src/cartoload/exporters/garmin_img.py` (subdivision generation), `src/cartoload/exporters/garmin_img_model.py` (TRE2 width/height encoding)
- **Tests**: `tests/test_exporter_garmin_img.py` (new gap-prevention tests)
- **Documentation**: `docs/exporters/garmin-img.md` (JNX comparison, updated RGN2/bitstream notes)
