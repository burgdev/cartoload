## 1. Consolidate quality to final write step

- [x] 1.1 In `rasterio_warp.py`, make `warp_tile_to_jpeg()` always encode at quality 95 internally (remove the `quality` parameter). Update all callers.
- [x] 1.2 In `compositor.py`, make `encode_composite_to_jpeg()` always encode at quality 95 (ignore the `quality` parameter). Update all callers.
- [x] 1.3 In `unified_pipeline.py`, remove quality propagation to intermediate processors (`_make_single_provider_processor`, `_make_composite_processor`). Ensure the target quality is only passed through to the final IMG writer.
- [x] 1.4 In `garmin_img_writer.py` `_process_tile_jpeg()`, ensure `_reencode_jpeg()` is called on bytes returned by the custom `tile_processor` when `jpeg_quality` is set (previously bypassed).

## 2. Implement mirror-padding in `_reencode_jpeg()`

- [x] 2.1 In `garmin_img_writer.py`, update `_reencode_jpeg()` to: decode input JPEG → mirror-pad by 16px using `ImageOps.expand()` with `Image.MIRROR` → encode at target quality → decode → crop center 256×256 → re-encode at target quality → return bytes.
- [x] 2.2 Add a guard: skip padding when quality >= 85 (not needed at high quality) and when quality is None (passthrough).
- [x] 2.3 Import `ImageOps` from PIL in `garmin_img_writer.py`.

## 3. Verify and test

- [x] 3.1 Run `just check` and `just check types` to verify formatting, linting, and type correctness.
- [x] 3.2 Run `just test` to verify all existing tests pass.
- [ ] 3.3 Run a test build at quality 30 and visually inspect for border artifacts: `cartoload build -c examples/configs/layers/test.yaml -l ch_basemap_25k -y 46.93459 -x 7.51105 -W 5 -H 5 -f --preview --executor thread --quality 30`
