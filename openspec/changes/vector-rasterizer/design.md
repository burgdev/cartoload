## Context

The composite pipeline reads JPEG/PNG tiles from cache directories, blends them using alpha compositing, and feeds the result into the Garmin IMG exporter. Tiles are 256x256 pixels, organized as `z/x/y.jpeg` (or `.png`) in cache directories. The compositor supports per-layer opacity.

The vector rasterizer sits between the GPKG downloader (provides `.gpkg` files) and the composite pipeline (consumes transparent PNG tiles). It reads features from GPKG via Fiona, applies style rules from the style engine, and draws lines using Pillow onto transparent RGBA tiles.

## Goals / Non-Goals

**Goals:**
- Render vector line features from GPKG onto 256x256 transparent PNG tiles
- Apply style engine rules for color, width, dash, and border/casing
- Per-zoom-level rendering with appropriate style variants
- Spatial filtering: only render features intersecting each tile's bounds
- Output tiles in cache directory structure compatible with the compositor

**Non-Goals:**
- Point or polygon rendering (lines only initially)
- Label/text rendering (deferred)
- Arrow rendering (deferred)
- Anti-aliasing beyond Pillow's built-in (sufficient for Garmin device displays)
- Vector IMG output (that's Path C)

## Decisions

### 1. Tile rendering approach: per-tile spatial query

**Decision:** For each tile (z, x, y), compute the tile's geographic bounds in EPSG:4326, query the GPKG for intersecting features via Fiona's bbox filter, project coordinates to pixel space, and draw.

**Rationale:** This matches how the WMTS pipeline works — one tile at a time. Fiona's bbox filtering uses the GPKG's spatial index, so queries are efficient. No need to load the entire GPKG into memory.

**Alternative considered:** Render all features to one large GeoTIFF, then tile. Rejected — more complex, memory-intensive, and loses the ability to render only tiles that have features.

### 2. Coordinate projection: direct lon/lat → pixel mapping

**Decision:** For each tile, compute a simple affine transform from geographic coordinates (EPSG:4326) to pixel coordinates on the 256x256 tile. No need for rasterio CRS transformation — the math is straightforward:

```
pixel_x = (lon - tile_west) / (tile_east - tile_west) * 256
pixel_y = (tile_north - lat) / (tile_north - tile_south) * 256
```

GPKG data in EPSG:2056 (Swiss LV95) will need reprojection to EPSG:4326 before rendering. This can be done with pyproj (already available via Fiona/rasterio dependency chain) or by reprojecting at query time.

**Rationale:** The tile coordinate system is already EPSG:4326 in the existing pipeline. A simple affine transform avoids GDAL overhead per tile.

### 3. Line drawing: Pillow ImageDraw

**Decision:** Use `PIL.ImageDraw.Draw.line()` for rendering. For casing, draw a wider line first in the border color, then a thinner line on top in the core color. For dashes, manually segment the polyline based on the dash pattern.

**Rationale:** Pillow is lightweight and sufficient for this use case. The rendering target is Garmin devices with limited resolution — sub-pixel anti-aliasing isn't critical.

**Dash implementation:** Walk the polyline segments, accumulating length. Alternate between "on" (draw) and "off" (skip) based on the dash pattern. Each "on" segment is a short polyline drawn normally.

### 4. Output format: transparent PNG

**Decision:** Output tiles as RGBA PNG files with transparent background.

**Rationale:** The compositor supports both JPEG and PNG, but only PNG preserves alpha transparency. RGBA is needed for overlay compositing. File sizes are larger than JPEG but the tiles are mostly transparent (sparse features), so compression is efficient.

### 5. Pipeline integration: overlay sub-layer

**Decision:** The rasterizer is invoked as part of `build_gpkg_layer()` when the layer is used as an overlay. It writes tiles to a cache directory that the composite pipeline references as a sub-layer.

```yaml
layers:
  ch_basemap_with_skitours:
    type: composite
    layers:
      - name: "Base map"
        source: {ref: swisstopo_wmts}
      - name: "Skitours overlay"
        source: {ref: skitouren_gpkg}
        opacity: 0.8
```

**Rationale:** Fits naturally into the existing composite pipeline. The GPKG overlay is just another sub-layer with transparent PNG tiles.

### 6. CRS handling

**Decision:** Reproject GPKG features from their source CRS to EPSG:4326 at read time using Fiona's built-in CRS transformation (`fiona.open(path, crs="EPSG:4326")`). This avoids storing reprojected data.

**Rationale:** Fiona supports on-the-fly CRS transformation. The GPKG source CRS is read from the file. If it's already EPSG:4326, no transformation occurs.

## Risks / Trade-offs

- **[Performance]** Per-tile spatial queries add overhead, especially at high zoom levels with many tiles. → GPKG spatial index makes queries fast. Only tiles with features need rendering (sparse coverage for route networks). Can parallelize across tiles.
- **[Dash rendering quality]** Manual dash segmentation may produce visual artifacts at sharp corners. → Acceptable for Garmin device rendering. Can improve later if needed.
- **[Pillow dependency]** Adds Pillow as a new dependency. → Pillow is the standard Python imaging library, widely available, small footprint (~5MB).
- **[No labels]** Routes without labels are less useful. → Labels deferred to a future change. Users can rely on the base map labels.
