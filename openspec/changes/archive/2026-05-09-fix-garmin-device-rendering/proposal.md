## Why

Generated Garmin IMG files render correctly in GPXSee but show almost nothing on actual Garmin devices (GPSMAP 66i). At some zoom levels (200m–800m) a blurry stretched overview is visible; most zoom levels show nothing. Two bugs prevent proper device rendering: the TRE1 zoom code for level 1 incorrectly sets the inherited flag (0x86 instead of 0x06), causing the device to skip raster data at that level; and the RGN sub-header is missing extended type fields (local flags and section offsets) that Garmin firmware needs to locate raster data.

## What Changes

- Fix `_compute_zoom_codes` in `garmin_img.py` to only apply the `0x80` inherited flag to level 0 (overview), not level 1. The current `if i <= 1` condition was incorrectly generalized from the 5-level SwissTopo pattern. The existing spec `dynamic-zoom-codes` already specifies the correct behavior.
- Populate the RGN sub-header extended fields (offsets 0x25–0x7C) with local flag bitmasks and section offsets for polygons/lines/points/dictionary, matching the pattern observed in both IOM and SwissTopo reference files.
- Verify rendering on actual Garmin GPSMAP 66i hardware at all zoom levels.

## Capabilities

### New Capabilities

- `rgn-extended-header`: RGN sub-header extended type fields (local flags, section offsets for polygons/lines/points/dictionary) required by Garmin device firmware for proper raster data decoding.

### Modified Capabilities

- `dynamic-zoom-codes`: The implementation already deviates from the spec — level 1 gets `0x86` (inherited) instead of `0x06` as the spec requires. This change aligns implementation with the existing spec (no spec change needed, only a bug fix).

## Impact

- `src/cartoload/exporters/garmin_img.py` — `_compute_zoom_codes` function fix
- `src/cartoload/exporters/garmin_img_writer.py` — `_build_rgn_subheader` function enhancement
- Generated IMG files will have different binary structure (corrected TRE1 zoom codes, populated RGN header fields)
- Backward compatible — GPXSee rendering unaffected (it already works), only fixes Garmin device rendering
