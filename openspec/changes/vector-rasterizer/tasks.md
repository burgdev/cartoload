## 1. Dependency and setup

- [ ] 1.1 Add Pillow as a project dependency (`uv add pillow`)
- [ ] 1.2 Create `src/cartoload/processor/vector_rasterizer.py` module

## 2. Feature reading

- [ ] 2.1 Implement `read_features(gpkg_path, bbox, crs="EPSG:4326")` — open GPKG with Fiona, apply bbox filter, reproject to target CRS, return list of (geometry, attributes) tuples
- [ ] 2.2 Write tests for feature reading: with bbox filter, CRS reprojection, empty result

## 3. Coordinate projection

- [ ] 3.1 Implement `geo_to_tile_pixel(lon, lat, tile_bounds, tile_size=256)` — affine transform from EPSG:4326 coordinates to pixel coordinates within a tile
- [ ] 3.2 Implement `project_feature_to_pixels(geometry, tile_bounds)` — convert a Shapely geometry's coordinates to pixel coordinates, returning a list of pixel-coordinate polylines
- [ ] 3.3 Write tests for coordinate projection: point within tile, point at tile edge, point outside tile

## 4. Line rendering

- [ ] 4.1 Implement `draw_line(image, pixel_coords, style: LineStyle)` — draw a single styled line onto a PIL RGBA image
- [ ] 4.2 Implement solid line rendering (no dash, no border) using `ImageDraw.line()`
- [ ] 4.3 Implement border/casing rendering: draw wider border line first, then core line on top
- [ ] 4.4 Implement dashed line rendering: segment polyline by dash pattern, draw "on" segments only
- [ ] 4.5 Implement dashed line with border: border segments and core segments drawn separately
- [ ] 4.6 Write tests for line rendering: solid line, dashed line, line with border, dashed with border, verify pixel output with test fixtures

## 5. Tile rasterizer

- [ ] 5.1 Implement `VectorRasterizer` class with `render_tile(gpkg_path, style_engine, z, x, y) -> PIL.Image` method: compute tile bounds, read features, resolve style per feature, draw lines, return RGBA image
- [ ] 5.2 Implement `render_tiles(gpkg_path, style_engine, zoom_levels, bounds, cache_dir, max_workers)` — iterate over all tiles in the zoom range, render each, write to cache
- [ ] 5.3 Write tile to disk as PNG: `<cache_dir>/<source_id>/<cache_key>/<z>/<x>/<y>.png`
- [ ] 5.4 Skip tiles where no features intersect (optional: write nothing or write empty transparent PNG)
- [ ] 5.5 Write integration test: render a small GPKG fixture with known features, verify tile output exists and contains expected pixels

## 6. Pipeline integration

- [ ] 6.1 Extend `build_gpkg_layer()` in pipeline.py to call `VectorRasterizer.render_tiles()` when the layer is used as a raster overlay (within a composite layer)
- [ ] 6.2 Wire the rasterizer output directory into the composite pipeline as a sub-layer tile source
- [ ] 6.3 Write test: composite layer with GPKG overlay renders correctly through the full pipeline
