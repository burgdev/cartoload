## 1. Add progressive JPEG encoding

- [x] 1.1 Add `progressive=True` to all `img.save(format="JPEG", ...)` calls in `_reencode_jpeg` in `garmin_img_writer.py`
- [x] 1.2 Add `subsampling="4:2:0"` explicitly to all JPEG save calls for clarity (already the default at quality < 75, but explicit is better)

## 2. Add mozjpeg post-processing

- [x] 2.1 Add `mozjpeg-lossless-optimization` to project dependencies (`pyproject.toml`)
- [x] 2.2 In `_reencode_jpeg`, after the final `img.save()`, apply `mozjpeg_lossless_optimization.optimize()` to the JPEG bytes
- [x] 2.3 Make mozjpeg post-processing optional: if the package is not installed, skip it with a log warning (graceful degradation)

## 3. Verify and test

- [x] 3.1 Run existing test suite to ensure no regressions
- [x] 3.2 Benchmark on real tiles: progressive provides 0% savings at quality 25 (actually 3.4% larger), removed progressive=True. mozjpeg alone gives 1.8% savings. Removed progressive and subsampling params, kept mozjpeg only.
- [ ] 3.3 Verify the output file works in GPXSee
- [ ] 3.4 Test on GPS device to confirm JPEG compatibility
