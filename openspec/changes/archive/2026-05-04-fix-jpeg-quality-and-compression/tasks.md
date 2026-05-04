## 1. Fix JPEG encoding in rasterio warp processor

- [x] 1.1 In `rasterio_warp.py`, replace rasterio MemoryFile JPEG encoding with PIL encoding in `_warp_to_jpeg()`: after rasterio warping produces a numpy array, use `Image.fromarray()` + `BytesIO` + `save(format='JPEG', quality=quality)` instead of `MemoryFile.open(driver='JPEG')`
- [x] 1.2 Verify that `warp_tile_to_jpeg()` quality parameter is actually passed through to the PIL encoding call

## 2. Add JPEG re-encoding for pass-through path

- [x] 2.1 Add a `_reencode_jpeg(jpeg_bytes: bytes, quality: int) -> bytes` helper in `garmin_img_writer.py` that decodes JPEG bytes via PIL and re-encodes at the specified quality
- [x] 2.2 Update `_process_tile_jpeg()` to call `_reencode_jpeg()` on the result when no tile_processor is set (EPSG:4326 pass-through path), applying the quality parameter

## 3. Fix quality parameter flow in sequential processing

- [x] 3.1 Update `_process_tile_jpeg()` to pass `jpeg_quality` to `tile_processor` callable — update the call to include quality (currently calls `tile_processor(path, x, y, zoom, source_crs)` without quality)
- [x] 3.2 Update the `tile_processor` type signature in `garmin_img.py` to accept and forward the quality parameter

## 4. Tests

- [x] 4.1 Add test verifying that `--quality 20` produces smaller output than `--quality 85` for the same tiles (integration test with actual JPEG encoding)
- [x] 4.2 Add unit test for `_reencode_jpeg()` helper: verify different quality levels produce different byte sizes
- [x] 4.3 Add unit test for `warp_tile_to_jpeg()` verifying quality parameter produces size differences (for the warp path with EPSG:3857 source)
- [x] 4.4 Run `just test` and verify all tests pass
- [x] 4.5 Run `just check` and `just check types` and verify no new diagnostics
