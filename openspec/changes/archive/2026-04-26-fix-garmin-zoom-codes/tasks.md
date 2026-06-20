## 1. Code Changes

- [x] 1.1 Replace `_GARMIN_ZOOM_CODES` dict in `garmin_img.py` with a `_compute_zoom_codes()` function that dynamically computes codes based on number of levels
- [x] 1.2 Update `_build_img_structure()` in `garmin_img.py` to call `_compute_zoom_codes()` instead of the static dict lookup
- [x] 1.3 Update tests in `test_exporter_garmin_img.py` that reference specific zoom codes to use dynamically computed values

## 2. Verification

- [x] 2.1 Run test suite and verify all tests pass
- [x] 2.2 Build an IMG file with `cartoload build` and verify gmt output shows `levels [...]` line with correct zoom codes
