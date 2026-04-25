## Context

The WMTS downloader (`src/cartoload/downloader/wmts.py`) downloads map tiles as plain JPEG files and stores them in a cache directory structured as `cache/{source_id}/{z}/{x}/{y}.jpeg`. These tiles are served by Web Mercator (EPSG:3857) tile services like swisstopo.

The raster processor (`src/cartoload/processor/raster.py`) calls `gdalbuildvrt` to mosaic these tiles into a VRT. However, `gdalbuildvrt` requires georeferenced inputs — plain JPEGs lack spatial metadata, so GDAL skips them with the warning: "gdalbuildvrt does not support ungeoreferenced image."

The tile grid coordinates (z/x/y) implicitly define the spatial position of each tile in the Web Mercator projection. This information just needs to be written as a GDAL-readable world file.

## Goals / Non-Goals

**Goals:**

- Attach georeferencing to each downloaded WMTS tile so `gdalbuildvrt` can mosaic them
- Use the standard Web Mercator (EPSG:3857) tile grid math to compute bounding boxes from z/x/y indices
- Write world files (`.jgw` for JPEG, `.pgw` for PNG) alongside cached tiles
- Handle already-cached tiles that lack world files (regenerate them)

**Non-Goals:**

- Supporting non-standard tile grids (only the standard Web Mercator / Slippy Map grid)
- Modifying the raster processor — the fix is entirely in the download/cache layer
- Embedding EXIF or other metadata into the image files themselves

## Decisions

### Decision 1: World files vs. individual VRTs per tile

**Choice:** Write ESRI world files (`.jgw`/`.pgw`) alongside each tile.

**Alternatives considered:**

- Per-tile VRT files: More flexible but heavier (XML overhead per tile) and not standard practice
- Using `gdal_translate` to re-encode with georeferencing: Slow, re-encodes image data unnecessarily
- Setting CRS via `gdalbuildvrt -a_srs`: Only sets the output CRS, doesn't georeference individual inputs

**Rationale:** World files are the standard, lightweight way to georeference image tiles. GDAL automatically reads them when present. They contain only 6 numbers (affine transform) and add negligible disk usage. No image re-encoding needed.

### Decision 2: CRS specification

**Choice:** Pass CRS to `gdalbuildvrt` via the `-a_srs EPSG:3857` flag in the raster processor.

**Rationale:** World files contain the affine transform but not the CRS identifier. GDAL needs both. Since all WMTS tiles use EPSG:3857, we add `-a_srs EPSG:3857` to the `gdalbuildvrt` command.

### Decision 3: Where to compute and write world files

**Choice:** In the `WMTSDownloader` class, as part of the cache write path.

**Rationale:** The downloader already has the z/x/y coordinates when writing tiles. Computing the world file at download time keeps the logic co-located and ensures world files exist for both new and re-downloaded tiles.

### Decision 4: Tile bounding box computation

**Choice:** Standard Web Mercator tile grid formulas:

```
tile_size_m = 2 * pi * 6378137 / 2^z
origin = -2 * pi * 6378137 / 2   (i.e., -20037508.3427892)

left  = origin + x * tile_size_m
top   = origin + y * tile_size_m
right = left + tile_size_m
bottom = top + tile_size_m
```

The world file affine transform is then:

```
pixel_size_x = tile_size_m / tile_width_pixels
rotation_y = 0
rotation_x = 0
pixel_size_y = -tile_size_m / tile_height_pixels  (negative because Y axis is inverted)
top_left_x = left
top_left_y = top
```

**Rationale:** This is the standard OGC/EPSG:3857 tile grid. Assumes 256x256 pixel tiles (the WMTS standard).

## Risks / Trade-offs

- **[Non-256px tiles]** Some WMTS services serve non-standard tile sizes (e.g., 512x512). → Mitigation: Assume 256x256 for now (covers swisstopo and the vast majority of services). Can be made configurable later if needed.
- **[World file missing for cached tiles]** Existing cached tiles lack world files, so the fix won't help until they are re-downloaded or world files are regenerated. → Mitigation: Check for world file existence alongside tile cache check; generate on demand if missing.
- **[CRS mismatch]** If a non-EPSG:3857 tile service is used, world files will be wrong. → Mitigation: The config already specifies `3857` in the URL template. Acceptable risk for now; the `-a_srs` flag in gdalbuildvrt handles the CRS declaration.
