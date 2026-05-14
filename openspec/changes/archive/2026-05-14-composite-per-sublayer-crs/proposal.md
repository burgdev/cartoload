## Why

The composite layer pipeline derives a single `source_crs` from the first sub-layer's source and uses it for all sub-layers. This breaks when mixing source types with different CRSes — for example, STAC GeoTIFFs (EPSG:4326) and WMTS tiles (EPSG:3857) in the same composite layer. Each sub-layer should independently resolve its own source type and CRS, since any combination of sources must work together.

## What Changes

- Each composite sub-layer independently resolves its source type and CRS from its own `source.ref`, instead of sharing one CRS derived from the first sub-layer.
- The composite processor dispatches per-sub-layer based on source type (stac, wmts, geotiff, future types), choosing the correct tile loading path for each.
- WMTS sub-layers default to EPSG:3857 when their source has no explicit `crs` field (existing convention).
- STAC/GeoTIFF sub-layers use their pre-warped EPSG:4326 mosaics as before.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `source-crs`: Composite sub-layers now resolve CRS independently per sub-layer instead of sharing one CRS from the first sub-layer.

## Impact

- `src/cartoload/pipeline.py` — `_make_composite_processor` closure and `build_composite_layer` CRS resolution logic.
- `src/cartoload/config.py` — may need to verify `CompositeSubLayer` carries enough source info for independent CRS resolution.
- No breaking changes to config format — existing composite layers with homogeneous sources continue to work identically.
