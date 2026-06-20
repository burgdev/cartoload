## Why

mozjpeg's trellis quantization produces 12-24% smaller JPEG tiles than Pillow at the same visual quality (quality 25-75). This directly translates to more map data fitting on GPS devices with limited storage. Benchmarks confirmed that compiling Pillow against mozjpeg provides zero benefit — trellis only activates through the full libjpeg compress API path used by the `cjpeg` binary. The only viable path is subprocess invocation of `cjpeg` for the final JPEG encode.

## What Changes

- **Use `cjpeg` (mozjpeg) for final JPEG encoding**: Replace Pillow's `save()` in `_reencode_jpeg()` with a subprocess call to mozjpeg's `cjpeg` binary. This activates trellis quantization for 12-24% smaller output.
- **Add `--fast` CLI flag**: Skip mirror-padding and cjpeg encoding. Falls back to Pillow's fast encode. Produces larger output but significantly faster builds. Useful for quick iterations and previews.
- **Install mozjpeg in Docker**: Add mozjpeg build step to the Dockerfile so `cjpeg` is available at runtime.
- **Graceful fallback**: When `cjpeg` is not available (local dev, CI), fall back to Pillow encoding with a warning. No hard dependency.
- **Remove `mozjpeg-lossless-optimization` from the cjpeg path**: mozjpeg's trellis already optimizes the bitstream; the lossless post-processing is redundant when cjpeg is used.

## Capabilities

### New Capabilities
- `fast-build-mode`: The `--fast` CLI flag that skips expensive optimization steps (mirror-padding, cjpeg trellis encode) for faster builds at the cost of larger output.

### Modified Capabilities
- `jpeg-border-padding`: The `_reencode_jpeg` function now uses cjpeg subprocess for the final JPEG encode when available, falling back to Pillow when not. In `--fast` mode, mirror-padding and cjpeg are both skipped.
- `docker-multi-stage-build`: Dockerfile gains a mozjpeg build stage to compile and install cjpeg.

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — `_reencode_jpeg()` rewritten to use cjpeg subprocess
- `src/cartoload/cli.py` — new `--fast` flag
- `src/cartoload/config.py` — propagate `fast` mode through pipeline config
- `src/cartoload/processor/pipeline.py` — pass `fast` flag through to tile processing
- `Dockerfile` — add mozjpeg build stage
- `pyproject.toml` — `mozjpeg-lossless-optimization` remains for non-cjpeg paths and fallback
- All pipelines that call `_reencode_jpeg` or do JPEG encoding
