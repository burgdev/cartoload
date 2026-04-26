## 1. Fix Y coordinate computation

- [x] 1.1 Fix `_compute_tile_bounds()` in `src/cartoload/downloader/wmts.py`: change `top` and `bottom` to compute from positive northing (`top = -origin - y * tile_size`, `bottom = top - tile_size`)
- [x] 1.2 Verify `_write_world_file()` uses the corrected `_compute_tile_bounds()` return values (it already uses `left, top` from that method — no changes needed beyond the bounds fix)

## 2. Verify and test

- [x] 2.1 Delete existing cache (`cache/swisstopo_wmts/`) to remove world files with wrong coordinates
- [x] 2.2 Run `cartoload build` for the Swiss basemap test layer and verify the GeoTIFF has correct positive latitude coordinates (use `gdalinfo`)
- [x] 2.3 Verify the output IMG is ~50MB (not ~1.5MB) and gmt shows reasonable bitmap sizes
- [ ] 2.4 Copy IMG to Garmin device and verify the map is visible at Guemligen
