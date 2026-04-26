## Why

WMTS tiles downloaded from sources like Swisstopo are georeferenced with inverted Y coordinates. The `_compute_tile_bounds()` method computes tile positions starting from the bottom of the Web Mercator grid (-20M meters) instead of the top (+20M meters), placing all tiles in the southern hemisphere. This causes the GeoTIFF to contain data at wrong coordinates, the tile extractor to produce blank tiles, and the resulting Garmin IMG files to be empty (~1.2 MB instead of ~50 MB).

## What Changes

- Fix `_compute_tile_bounds()` in `src/cartoload/downloader/wmts.py` to compute Y coordinates from the top of the Web Mercator grid (positive northing) instead of the bottom (negative northing)
- Fix `_write_world_file()` world file generation to use the corrected Y coordinates
- Fix any downstream code that depends on the coordinate sign convention

## Capabilities

### New Capabilities

_None_

### Modified Capabilities

_None (no existing specs)_

## Impact

- `src/cartoload/downloader/wmts.py`: `_compute_tile_bounds()` and `_write_world_file()` — core coordinate computation
- All WMTS downloads will produce correctly georeferenced tiles after this fix
- Existing cached tiles with wrong world files will need to be regenerated (delete cache or use `--force`)
- Downstream pipeline (VRT building, GeoTIFF processing, tile extraction, IMG export) all benefit automatically
