## Why

Large maps generated at low JPEG quality (e.g., quality 25) produce GMP subfiles that are too large for Garmin GPS devices (gpsmap 66i). The root cause is that `_split_into_gmp_groups` estimates GMP sizes using **original** JPEG file sizes, not the quality-adjusted sizes. At low quality, the estimate is far too high, so the split logic creates too few GMP groups. The actual output per GMP can reach 2.47 GB, which exceeds what the GPS firmware can handle. An old working file split the same total data into 8 GMPs (max 577 MB each) and worked fine.

## What Changes

- **Apply quality ratio to split estimates**: `_split_into_gmp_groups` and the split decision in `GarminIMGExporter.export()` will use quality-adjusted JPEG sizes (estimated via `_estimate_quality_ratio`) instead of raw source file sizes.
- **Lower the per-GMP target size**: `MAX_GMP_SIZE` and the split target will be reduced so individual GMP subfiles stay well within GPS device limits (targeting ~512 MB per GMP, matching the pattern of the known-working IOM reference file).
- **Keep the quality ratio estimate accessible**: The quality ratio estimation (currently only in `StreamingIMGWriter`) needs to be callable from the exporter's split logic.

## Capabilities

### New Capabilities

_None_

### Modified Capabilities

- `multi-gmp-subfiles`: Split decision and grouping now use quality-adjusted JPEG size estimates instead of original file sizes. Per-GMP target lowered from ~2.975 GB to ~512 MB.

## Impact

- `src/cartoload/exporters/garmin_img.py` — split decision logic, `_split_into_gmp_groups`, `export()`
- `src/cartoload/exporters/garmin_img_writer.py` — `MAX_GMP_SIZE`, quality ratio estimation, block size computation
- All maps with multiple zoom levels will produce more GMP subfiles (each smaller). Single-zoom small maps unaffected.
- File sizes remain similar overall (same data, just distributed differently across GMP subfiles).
