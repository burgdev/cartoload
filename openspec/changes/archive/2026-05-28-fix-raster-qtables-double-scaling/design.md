## Context

`iom_qtables_for_quality()` in `garmin_img_writer.py` scales the raw IOM base tables (`_IOM_LUMA`, `_IOM_CHROMA`) by a quality-dependent factor. The resulting pre-scaled tables are passed to JPEG encoders (Pillow or cjpeg/mozjpeg) alongside the same quality number. Both encoders treat custom qtables as base tables and scale them again — causing double-scaling.

Verified empirically:
- Pre-scaled q25 tables at quality 25 (double-scaled): Pillow = 2094 bytes, cjpeg = 1859 bytes
- Base tables at quality 25 (single-scaled): Pillow = 3538 bytes, cjpeg = 3116 bytes

The Pillow double-scaled output was "acceptable by accident." The cjpeg double-scaled output is not, because trellis optimization compounds the over-compression.

Additionally, when no custom qtables are provided, cjpeg uses mozjpeg's default quant-table 3 (Robidoux) while Pillow uses Annex K (quant-table 0). This means the same quality number has different meanings across encoders even without custom tables.

## Goals / Non-Goals

**Goals:**
- Eliminate double-scaling so `--qtables raster` produces consistent quality between Pillow and cjpeg
- Rename `iom_qtables_for_quality` to `raster_qtables_for_quality` to match the user-facing preset name
- Make cjpeg use Annex K tables by default (same as Pillow) when no custom qtables are provided

**Non-Goals:**
- Changing the CLI interface or preset names
- Adjusting quality numbers or adding quality offsets
- Optimizing trellis tuning parameters

## Decisions

### 1. Return unscaled base tables, let encoders handle scaling

`raster_qtables_for_quality()` will return the raw `_IOM_LUMA` / `_IOM_CHROMA` tables without any quality-based scaling. Both Pillow and cjpeg apply the same quality-to-scale-factor formula (`5000/quality` for quality < 50, `200 - 2*quality` for quality >= 50) to custom qtables before use. Returning the base tables means quality scaling happens once, in the encoder.

The `quality` parameter is kept in the function signature for API stability — it's simply ignored since scaling is delegated to the encoder.

**Alternative considered:** Pass `-quality 100` to cjpeg to disable its scaling, keep pre-scaling in the function. Rejected because Pillow has no equivalent "use qtables as-is" mode — it always scales by quality.

### 2. Add `-quant-table 0` when no custom qtables in cjpeg

When `qtables is None`, the cjpeg command gains `-quant-table 0` to force Annex K tables. When custom qtables are provided via `-qtables FILE`, the `-quant-table` flag is omitted (cjpeg uses the file instead).

### 3. Rename function

`iom_qtables_for_quality` → `raster_qtables_for_quality`. The `iom` prefix refers to internal Garmin IMG terminology and is confusing. `raster` matches the `--qtables raster` CLI preset.

## Risks / Trade-offs

- **Output quality changes for existing users of `--qtables raster`**: Files will be larger and higher quality at the same nominal quality number. This is the correct behavior — the old behavior was unintentionally over-compressing. → Document in changelog.
- **Trellis savings are smaller than initially observed**: The initial 12-24% file size reduction from the mozjpeg-trellis-encode change was partly due to the double-scaling + Robidoux table, not just trellis. After this fix, trellis-only savings will be more modest (~12%). → This is honest and correct.
