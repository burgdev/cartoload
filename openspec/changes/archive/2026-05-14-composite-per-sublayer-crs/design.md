## Context

The composite layer pipeline in `pipeline.py` currently derives a single `source_crs` from the **first** sub-layer's source config and uses it for all sub-layers. This works when all sub-layers share the same source type and CRS, but breaks when mixing types — e.g., STAC GeoTIFFs (EPSG:4326 mosaics) and WMTS tiles (EPSG:3857).

The core issue: `_make_composite_processor` takes a single `source_crs` string and uses it for every sub-layer's tile loading. For WMTS sub-layers it checks `source_crs != "EPSG:4326"` to decide whether to warp, but since the first sub-layer is STAC (no CRS field), `source_crs` ends up as `None`, causing `warp_tile_to_rgba` to fail with "images do not match".

Current flow:

```
build_composite_layer()
  first_sub = sub_layers[0]
  first_source = resolve(first_sub.source)
  source_crs = first_source.crs or None          ← single CRS for all
  ...
  composite_processor = _make_composite_processor(
      ..., source_crs=source_crs, ...
  )

  composite_processor():
    for each sub:
      if idx in stac_mosaics:
          read_tile_from_warped_geotiff(...)      ← OK, ignores source_crs
      else:  # WMTS
          if source_crs != "EPSG:4326":           ← None != "EPSG:4326" → True
              warp_tile_to_rgba(..., source_crs=None, ...)  ← BOOM
```

## Goals / Non-Goals

**Goals:**
- Each composite sub-layer independently resolves its source type and CRS.
- Mixing STAC, GeoTIFF, WMTS (and future source types) in one composite layer works correctly.
- WMTS sub-layers default to EPSG:3857 when their source has no explicit `crs` field.
- Minimal change — keep the existing composite processor closure pattern, just fix CRS/type resolution.

**Non-Goals:**
- Adding new source types (vector, etc.) — this change just makes the existing ones composable.
- Changing the config format — `CompositeSubLayer` already carries `source.ref`, `source_args`, etc.
- Refactoring the composite processor into a class or plugin system — keep the closure pattern.

## Decisions

### Decision 1: Per-sub-layer source resolution inside the composite processor

Instead of passing a single `source_crs` into the closure, pre-resolve each sub-layer's source config and CRS at closure-creation time. Store a list of `(source_type, source_crs)` tuples parallel to `sub_layers`.

**Why:** The closure already iterates over `sub_layers` by index. Adding parallel metadata avoids re-resolving on every tile. The `stac_mosaics` dict already does this pattern (index → mosaic path).

**Alternative considered:** Resolve inside the per-tile loop. Rejected — source resolution involves dict lookups and CRS parsing, wasteful to repeat for every tile.

### Decision 2: CRS resolution function per sub-layer

Extract a helper `_resolve_source_crs(source: SourceConfig) -> str` that returns the effective CRS for a source:
- If `source.crs` is set → use it
- If `source.type == "wmts"` → default to `"EPSG:3857"`
- Otherwise → `"EPSG:4326"` (GeoTIFF/STAC files carry their own CRS)

**Why:** Centralizes the CRS default logic that's already scattered across `build_layer`, `build_geotiff_layer`, and `build_composite_layer`.

### Decision 3: Source type dispatch in composite processor

The composite processor already has two paths (STAC mosaic vs WMTS cache). Add a per-sub-layer `source_type` to dispatch correctly:
- `stac` / `geotiff` → read from mosaic via `read_tile_from_warped_geotiff`
- `wmts` → load from cache, warp if `source_crs != "EPSG:4326"`

**Why:** This is essentially what the code already does, but keyed off `stac_mosaics` dict membership rather than explicit type. Making it explicit prepares for future source types.

## Risks / Trade-offs

- **Risk: Missing source type** → If a new source type is added without updating the composite processor, it will silently skip those tiles. Mitigation: log a warning for unrecognized source types.
- **Risk: CRS mismatch between sub-layers** → Sub-layers in different CRSes are now correctly handled per-sub-layer, but the final composite still assumes all tiles are composited in EPSG:4326 (the warp outputs). This is correct since both STAC (pre-warped) and WMTS (warped via `warp_tile_to_rgba`) produce EPSG:4326 output.
