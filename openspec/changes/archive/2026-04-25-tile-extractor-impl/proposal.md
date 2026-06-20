## Why

The `TileExtractor` in `garmin_img_writer.py` is a stub that returns empty tile lists with a "Full implementation pending" warning. This means the Garmin IMG exporter produces only headers and metadata (~128 KB) instead of the actual raster tiles, making the output useless despite a correctly processed 299 MB GeoTIFF.

## What Changes

- Implement `TileExtractor.extract_tiles` to read the processed GeoTIFF and extract 256x256 pixel tiles at each configured zoom level
- Use `gdal_translate` CLI (consistent with existing project pattern) to extract tile regions from the GeoTIFF, leveraging its built-in overview pyramids for lower zoom levels
- Use PIL/numpy to load extracted regions and return them as numpy arrays for JPEG encoding
- Wire the grid computation (already in `TileEncoder.compute_grid`) into the extraction loop so tiles map to correct Web Mercator grid positions

## Capabilities

### New Capabilities

- `tile-extraction`: Extract georeferenced raster tiles from a processed GeoTIFF at multiple zoom levels using the Web Mercator tile grid

### Modified Capabilities

<!-- No existing specs to modify -->

## Impact

- **Code**: `src/cartoload/exporters/garmin_img_writer.py` — `TileExtractor` class
- **Dependencies**: No new dependencies (uses existing `gdal_translate` CLI, PIL, numpy)
- **Output**: Garmin IMG files will now contain actual raster tile data instead of empty tile sets
