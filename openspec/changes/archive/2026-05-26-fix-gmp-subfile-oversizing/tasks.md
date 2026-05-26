## 1. Lower MAX_GMP_SIZE

- [x] 1.1 Change `MAX_GMP_SIZE` in `garmin_img_writer.py` from `3_500_000_000` to `600_000_000` (~600 MB)
- [x] 1.2 Verify the target per-group JPEG size computation (`MAX_GMP_SIZE * 0.85 = 510 MB`) works with the new value

## 2. Apply quality ratio to split decision

- [x] 2.1 Extract or adapt `_estimate_quality_ratio` in `garmin_img_writer.py` to accept `dict[int, list[TileMetadata]]` directly (instead of `list[Subdivision]`), so it can be called before subdivisions are created
- [x] 2.2 In `GarminIMGExporter.export()` (garmin_img.py), compute the quality ratio before the split decision using the tile_metadata, quality setting, and source_crs
- [x] 2.3 Pass the quality ratio to `_split_into_gmp_groups` as a new parameter
- [x] 2.4 In `_split_into_gmp_groups`, multiply each `t.jpeg_size` by the quality ratio when computing `zoom_jpeg_sizes` and band sizes
- [x] 2.5 Apply the quality ratio to the `total_jpeg_size` computation in `GarminIMGExporter.export()` before comparing against `MAX_GMP_SIZE`

## 3. Verify and test

- [ ] 3.1 Rebuild the full Switzerland basemap at quality 25 and verify it produces multiple reasonably-sized GMP subfiles (each under 600 MB) — SKIPPED: rebuild takes >1 hour
- [ ] 3.2 Verify the rebuilt file works on the GPS device (gpsmap 66i) — SKIPPED: depends on 3.1
- [x] 3.3 Run existing test suite to ensure no regressions
