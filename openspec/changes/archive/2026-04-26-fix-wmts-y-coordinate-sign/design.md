## Context

The WMTS downloader in `src/cartoload/downloader/wmts.py` computes tile bounding boxes in EPSG:3857 (Web Mercator) meters. The current implementation uses a single `origin = -20037508.34` constant for both X and Y axes. This is correct for X (tile x=0 starts at the left/antimeridian) but wrong for Y (tile y=0 should start at the top, +20M meters near 85° N).

The bug propagates through the entire pipeline:

1. World files (.jgw) get negative Y northing values
2. VRT/TIF is built with data at southern hemisphere coordinates
3. TileExtractor asks gdal_translate for correct northern hemisphere coordinates
4. gdal_translate finds no data → empty tiles
5. Empty tiles compress to ~668 bytes instead of ~24KB
6. Garmin IMG is ~1.5MB instead of ~50MB with blank bitmaps

## Goals / Non-Goals

**Goals:**

- Fix the Y coordinate computation so tiles are placed at correct northern/southern hemisphere locations
- Ensure world files, VRT, TIF, and final IMG all have correct georeferencing

**Non-Goals:**

- Changes to the tile extraction or IMG writer pipeline (they are correct; the input data is wrong)
- Automatic cache invalidation or migration of existing cached tiles

## Decisions

### Fix `_compute_tile_bounds()` Y computation

**Decision**: Change `top` and `bottom` to compute from positive northing.

Current (wrong):

```python
origin = -20037508.342789244
top = origin + y * tile_size      # starts negative, goes more negative
bottom = top + tile_size           # even more negative
```

Fixed:

```python
top = -origin - y * tile_size     # starts at +20M, decreases for higher y
bottom = top - tile_size           # further south
```

**Rationale**: Web Mercator tile y=0 is at the northernmost row (85.05° N, northing +20M). Each increment of y moves one tile south. The X axis is unaffected — it already works correctly because longitude increases left-to-right.

**Alternatives considered**:

- Compute using lat/lon then project to EPSG:3857 — more complex, unnecessary
- Use separate `origin_x` and `origin_y` constants — clearer but more code for a one-line fix

### Cache invalidation

**Decision**: Do NOT automatically invalidate existing cache. Users must delete cached tiles or use `--force` to rebuild.

**Rationale**: The cached JPEG tiles themselves are fine — only the world files are wrong. Auto-deleting cache would force re-downloading ~46MB per build. Documenting the need to clear cache is sufficient.

## Risks / Trade-offs

- **[Existing cached tiles have wrong world files]** → Users must clear their cache directory after this fix. Document this as a required step.
- **[World file format assumptions]** → The world file format is standard (6 lines: pixel size X, rotation, rotation, pixel size Y, origin X, origin Y). The fix only changes the Y values, which is safe.
