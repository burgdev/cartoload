## Why

cjpeg (mozjpeg with trellis quantization) is used automatically when available on PATH, with no way to opt out. The existing `--fast` flag disables cjpeg but also skips mirror-padding, bundling two unrelated behaviors. Users need a way to control cjpeg independently — to force Pillow for consistency, or to explicitly require mozjpeg and fail early if it's missing.

## What Changes

- Add `--mozjpeg` / `--no-mozjpeg` flag to `cartoload build`:
  - Default (no flag): auto-detect — use cjpeg if on PATH, Pillow otherwise (current behavior)
  - `--mozjpeg`: explicitly require cjpeg, error if not found
  - `--no-mozjpeg`: force Pillow, skip cjpeg entirely
- The `--fast` flag's help text should be updated to clarify it skips mirror-padding (cjpeg control is now separate)

## Capabilities

### New Capabilities

- `mozjpeg-flag`: CLI flag to control whether mozjpeg's cjpeg is used for JPEG encoding

### Modified Capabilities

(none — existing specs don't define encoder selection behavior)

## Impact

- `src/cartoload/cli.py` — new `--mozjpeg` option
- `src/cartoload/processor/pipeline.py` — pass mozjpeg preference through to exporter
- `src/cartoload/exporters/garmin_img_writer.py` — `_encode_cjpeg` respects the flag (or disable cjpeg when `--no-mozjpeg`)
