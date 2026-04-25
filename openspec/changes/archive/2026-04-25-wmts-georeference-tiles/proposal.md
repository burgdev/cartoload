## Why

Downloaded WMTS tiles are saved as plain JPEG files without georeferencing metadata. When `gdalbuildvrt` tries to assemble them into a VRT, it cannot determine their spatial position, producing the error: "gdalbuildvrt does not support ungeoreferenced image." The pipeline cannot proceed to mosaic, reproject, or export tiles without a valid VRT.

## What Changes

- Add georeferencing metadata (world files) to each downloaded WMTS tile so GDAL can place them spatially
- Use the tile's z/x/y coordinates and the known Web Mercator (EPSG:3857) grid to compute the correct bounding box for each tile
- Write a `.jgw` world file alongside each downloaded JPEG (or `.pgw` for PNG) with the affine transformation parameters
- Ensure `gdalbuildvrt` receives properly georeferenced inputs and builds a correct VRT

## Capabilities

### New Capabilities

- `tile-georeferencing`: Compute and write georeferencing world files for WMTS tiles based on their z/x/y indices and the EPSG:3857 tiling scheme

### Modified Capabilities

<!-- No existing specs to modify -->

## Impact

- **Code**: `src/cartoload/downloader/wmts.py` — must generate world files after downloading tiles
- **Dependencies**: No new dependencies (pure math using the Web Mercator tile grid formula)
- **Data**: Downloaded tile cache will include `.jgw`/`.pgw` sidecar files
- **Pipeline**: The VRT building step in `RasterProcessor` will no longer skip tiles
