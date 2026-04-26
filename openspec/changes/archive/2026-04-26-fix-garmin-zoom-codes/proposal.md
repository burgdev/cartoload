## Why

The Garmin IMG writer produces zoom codes that don't match the pattern used by real Garmin devices and reference files (IOM.img, SwissTopo_West.img). GMT validation shows no `levels [...]` line, and Garmin devices don't display the map. The root cause is a static zoom-code lookup table (`_GARMIN_ZOOM_CODES` in `garmin_img.py`) that is incorrect for most zoom levels and entirely missing zoom 8.

## What Changes

- Replace the static `_GARMIN_ZOOM_CODES` dictionary with a dynamic function that computes zoom codes based on the number of levels in the file
- The zoom code pattern (confirmed from IOM and SwissTopo reference files): first level gets `0x80 + (N-1)`, remaining levels count down from `N-2` to `0`
- Remove the static mapping that incorrectly assigns absolute codes per zoom level
- Fix zoom level 8 (currently missing, defaults to code 0x00)

## Capabilities

### New Capabilities

- `dynamic-zoom-codes`: Compute Garmin TRE1 zoom codes dynamically based on the number of zoom levels in the IMG file, matching the pattern observed in reference files

### Modified Capabilities

## Impact

**Files Modified**:

- `src/cartoload/exporters/garmin_img.py`: Replace `_GARMIN_ZOOM_CODES` dict with a function; update `_build_img_structure()` to call it
- `tests/test_exporter_garmin_img.py`: Update test zoom codes to match dynamic computation

**Validation**:

- GMT output should show `levels [...]` line with correct zoom codes
- Generated IMG should match reference file patterns for TRE1 level encoding
