## 1. Fix raster qtables function

- [x] 1.1 Rename `iom_qtables_for_quality` to `raster_qtables_for_quality` in `garmin_img_writer.py`
- [x] 1.2 Simplify `raster_qtables_for_quality` to return the unscaled `_IOM_LUMA` / `_IOM_CHROMA` base tables directly (remove quality-based scaling). Keep the `quality` parameter in the signature for API compatibility but ignore it.
- [x] 1.3 Update the `get_qtables()` function to call the renamed function

## 2. Fix cjpeg default quantization table

- [x] 2.1 In `_encode_cjpeg()`, add `-quant-table 0` to the cjpeg command when `qtables is None` (no custom tables). When `qtables` is provided, omit `-quant-table` (the `-qtables FILE` takes precedence).

## 3. Update tests

- [x] 3.1 Update any test references from `iom_qtables_for_quality` to `raster_qtables_for_quality`
- [x] 3.2 Verify `raster_qtables_for_quality(25)` returns the same values as `raster_qtables_for_quality(50)` (i.e., quality parameter is ignored, base tables returned)
- [x] 3.3 Run `just test` and `just check` to confirm everything passes
