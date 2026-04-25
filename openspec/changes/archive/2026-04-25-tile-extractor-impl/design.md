## Context

The Garmin IMG export pipeline has three stages: extract tiles from GeoTIFF → encode to JPEG → write binary IMG. The extraction stage (`TileExtractor` in `garmin_img_writer.py`) is currently a stub returning empty lists, so no tile data reaches the IMG writer.

The processed GeoTIFF is in EPSG:4326 (WGS84), LZW-compressed, with overview pyramids at levels 2, 4, 8, 16, 32, 64. The GeoTIFF covers the configured geographic bounds at the highest requested zoom level.

The project does not use rasterio or GDAL Python bindings — it shells out to GDAL CLI tools (`gdalbuildvrt`, `gdalwarp`, `gdaladdo`). This pattern should be followed for tile extraction.

## Goals / Non-Goals

**Goals:**

- Implement `TileExtractor.extract_tiles` to extract 256x256 tiles from the processed GeoTIFF at each configured zoom level
- Use GDAL CLI tools (consistent with project patterns) to read and reproject tile regions
- Leverage the GeoTIFF's overview pyramids for lower zoom levels to avoid full-resolution reads
- Map extracted tiles to the correct Web Mercator grid positions using bounds and zoom math

**Non-Goals:**

- Adding rasterio or GDAL Python bindings as dependencies
- Changing the Garmin IMG binary writer or tile encoding logic
- Fixing unrelated issues (e.g., the Y-axis sign issue in the GeoTIFF origin)
- Supporting tile sizes other than 256x256

## Decisions

### Decision 1: Use `gdal_translate` for tile extraction

**Choice:** For each tile grid position, call `gdal_translate` with `-projwin` to extract the corresponding geographic region from the GeoTIFF, pipe the result through PIL to get a numpy array.

**Alternatives considered:**

- **rasterio/gdal Python bindings**: Would be cleaner but requires adding a heavy dependency. Project pattern is CLI tools.
- **Read entire GeoTIFF into memory and slice**: The GeoTIFF can be hundreds of MB; reading the whole thing is wasteful for tile extraction.
- **Reproject GeoTIFF back to EPSG:3857 and read pixel windows**: Adds an extra reprojection step. `gdal_translate -projwin` handles CRS transformation internally.

**Rationale:** `gdal_translate -projwin` supports reading from overviews (via `-outsize`), handles CRS conversion, and outputs exactly the tile region needed. One subprocess call per tile is the trade-off for avoiding heavy Python dependencies.

### Decision 2: Use overview levels for lower zoom tiles

**Choice:** When extracting tiles at zoom levels lower than the maximum, use `gdal_translate -outsize 256 256` with the `-ovr` flag or appropriate scaling to read from overview pyramids instead of full-resolution data.

**Rationale:** The GeoTIFF already has overview pyramids built by `gdaladdo`. Reading from overviews avoids decompressing the full raster for each low-zoom tile and is significantly faster.

### Decision 3: Tile grid computation reuse

**Choice:** Reuse the existing `TileEncoder.compute_grid` math to determine which tile grid positions (x, y) fall within the bounds at each zoom level.

**Rationale:** The Web Mercator tile grid math is already implemented and tested. No need to duplicate it.

### Decision 4: Batch extraction via VRT

**Choice:** For each zoom level, build a temporary VRT from the GeoTIFF at the target resolution, then use `gdal_translate` to extract individual tiles from the VRT.

**Rationale:** Building a per-zoom-level VRT with the correct resolution means each `gdal_translate` call extracts a fixed-size pixel window rather than needing geographic coordinate conversion per tile. This is faster and simpler.

## Risks / Trade-offs

- **[Performance: subprocess per tile]** Calling `gdal_translate` once per tile is slow for large grids. → Mitigation: Use per-zoom-level VRTs and fixed-size pixel windows; for very large exports, this is acceptable as it's a batch process. Can optimize later with in-memory approaches.
- **[GeoTIFF CRS mismatch]** The GeoTIFF is in EPSG:4326 but tiles are in Web Mercator grid. → Mitigation: `gdal_translate` handles reprojection via `-projwin` which accepts geographic coordinates and reads from the correct CRS source.
- **[Empty tiles at bounds edges]** Tiles at the edge of the bbox may be partially outside the data. → Mitigation: `gdal_translate` fills missing data with nodata (black), which is acceptable for map tiles.
