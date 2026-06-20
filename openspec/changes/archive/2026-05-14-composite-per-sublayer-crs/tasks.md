## 1. Per-sub-layer CRS resolution

- [x] 1.1 Add `_resolve_source_crs(source: SourceConfig) -> str` helper to `pipeline.py` — returns `source.crs` if set, `"EPSG:3857"` for wmts, `"EPSG:4326"` otherwise
- [x] 1.2 In `build_composite_layer`, replace single `source_crs` derivation with per-sub-layer resolution: build a list `_sub_sources` of `(source_type, source_crs)` tuples resolved from each sub-layer's `source.ref`
- [x] 1.3 Pass `_sub_sources` into `_make_composite_processor` instead of the single `source_crs` string

## 2. Fix composite processor dispatch

- [x] 2.1 In `_make_composite_processor`, use `_sub_sources[idx]` to get each sub-layer's source type and CRS instead of the shared `source_crs`
- [x] 2.2 For WMTS sub-layers, use the sub-layer's own CRS (from `_sub_sources`) when calling `warp_tile_to_rgba`
- [x] 2.3 For STAC/GeoTIFF sub-layers, keep existing mosaic path (no CRS needed — already EPSG:4326)
- [x] 2.4 Log a warning for unrecognized source types instead of silently skipping
- [x] 2.5 Normalize all sub-layer tile images to 256x256 before compositing (PIL alpha_composite requires identical sizes; STAC mosaics produce 256x256 but WMTS warp produces variable dimensions)

## 3. Verify

- [ ] 3.1 Run `just check` and `just check types`
- [ ] 3.2 Run `just test`
- [ ] 3.3 Test manually: `cartoload build -c examples/configs/layers/test.yaml -l ch_stac -y 46.93459 -x 7.51105 -W 5 -H 5 -f --preview --executor thread --quality 25` — no "images do not match" errors
