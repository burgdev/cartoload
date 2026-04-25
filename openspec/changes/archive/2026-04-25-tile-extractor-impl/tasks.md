## 1. Tile Grid Computation

- [x] 1.1 Add a `_tile_grid_for_zoom` method to `TileExtractor` that takes bounds and zoom level and returns a list of `(x, y, lon_min, lat_max, lon_max, lat_min)` tuples for every Web Mercator tile cell within the bounds
- [x] 1.2 Reuse the existing Web Mercator tile math from `TileEncoder.compute_grid` / `WMTSDownloader._bbox_to_tile_indices` to compute x/y ranges

## 2. Tile Extraction via gdal_translate

- [x] 2.1 Add a `_extract_tile_region` method that calls `gdal_translate` with `-projwin` and `-outsize 256 256` to extract a geographic region from the GeoTIFF as a 256x256 PNG/JPEG in memory
- [x] 2.2 Load the `gdal_translate` output into a numpy array using PIL and return it as shape `(256, 256, 3)` uint8

## 3. Implement extract_tiles

- [x] 3.1 Replace the stub `TileExtractor.extract_tiles` with a real implementation that iterates over zoom levels, computes the tile grid, and extracts each tile using `_extract_tile_region`
- [x] 3.2 Remove the "Full implementation pending" warning log

## 4. Tests

- [x] 4.1 Unit test for `_tile_grid_for_zoom` with known bounds and zoom levels, verifying correct tile count and coordinates
- [x] 4.2 Unit test for `_extract_tile_region` using a small test GeoTIFF, verifying the output is a 256x256x3 uint8 array
- [x] 4.3 Integration test: create a small GeoTIFF, run `extract_tiles`, verify non-empty tile data is returned at expected zoom levels
