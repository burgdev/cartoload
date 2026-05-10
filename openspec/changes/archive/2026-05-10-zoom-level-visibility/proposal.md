## Why

When zooming out past ~12k scale on the GPSMAP 66i, the map disappears entirely. The root cause is that the `_compute_zoom_codes()` function unconditionally sets the 0x80 inherited flag on the first (most zoomed-out) zoom level. GPXSee and Garmin devices skip all levels with this flag set, starting rendering from the first non-inherited level. If the most-zoomed-out level with actual tiles has the inherited flag, those tiles are never displayed. Additionally, using 8 zoom levels (e.g., [8, 9, 11, 12, 13, 14, 15, 16]) creates a deeper subdivision tree than necessary — mkgmap typically uses 3-5 levels — adding overhead to device rendering without meaningful visual benefit.

## What Changes

- Change `_compute_zoom_codes()` to only set the 0x80 inherited flag on levels that are truly empty (no tiles, serving only as spatial index roots)
- The most-zoomed-out level that contains tiles SHALL NOT have the inherited flag, ensuring its tiles are rendered at the device's most zoomed-out scale
- Empty overview levels (no tiles) that exist purely for spatial indexing SHALL keep the inherited flag
- **BREAKING**: The zoom code computation contract changes — the inherited flag is no longer always on the first level

## Capabilities

### New Capabilities

### Modified Capabilities
- `dynamic-zoom-codes`: Zoom code computation changes to set 0x80 inherited flag based on tile presence, not unconditionally on the first level
- `garmin-img-exporter`: The zoom level visibility behavior changes — tiles at the most-zoomed-out level with data will now be visible on devices

## Impact

- **Core files**: `garmin_img.py` (`_compute_zoom_codes()`)
- **Binary output**: TRE1 zoom code byte will change for some configurations (no longer always 0x80 on first entry)
- **Device behavior**: Map will remain visible at zoomed-out scales instead of disappearing
- **Existing tests**: Tests for `_compute_zoom_codes()` will need updating to reflect the new inherited-flag logic
