## Why

Custom raster quantization tables are pre-scaled to the target quality by `iom_qtables_for_quality()`, then passed to the JPEG encoder (Pillow or cjpeg/mozjpeg) along with the same quality parameter. Both encoders treat custom qtables as **base tables** and scale them again — resulting in double-scaling. With Pillow this produces acceptable output, but with cjpeg/mozjpeg the double-scaling compounds with trellis optimization, making quality 16 visually unusable (vs. fine with Pillow).

## What Changes

- Rename `iom_qtables_for_quality()` to `raster_qtables_for_quality()` — the "IOM" prefix is internal jargon; "raster" matches the user-facing `--qtables raster` preset name.
- Change `raster_qtables_for_quality()` to return the **unscaled base IOM tables** (scale factor 1.0, equivalent to quality 50) instead of pre-scaling. The encoder's own `quality` parameter handles the scaling.
- Add `-quant-table 0` to the cjpeg command when no custom qtables are provided, forcing mozjpeg to use Annex K tables (same as Pillow/libjpeg) instead of the default Robidoux table. This ensures quality N has the same meaning in both encoders.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `fix-composite-quality`: The raster qtables function signature and behavior changes — callers that passed pre-scaled tables now receive base tables and must rely on the encoder's quality scaling.

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — `iom_qtables_for_quality()` renamed and simplified, `_encode_cjpeg()` gains `-quant-table 0` default, callers updated.
- Any code referencing `iom_qtables_for_quality` must be updated to `raster_qtables_for_quality`.
- JPEG output quality will change (improve) for users of `--qtables raster` — tiles will be less aggressively compressed at the same nominal quality. File sizes will increase slightly, but quality will be consistent between Pillow and cjpeg paths.
