## 1. Core: cjpeg encoding in _reencode_jpeg

- [ ] 1.1 Add `shutil.which("cjpeg")` detection at module level in `garmin_img_writer.py`, cache result in `_CJPEG_AVAILABLE`
- [ ] 1.2 Create `_encode_cjpeg(img, quality, qtables)` helper that converts PIL Image to PPM, pipes to cjpeg subprocess, returns JPEG bytes. Handle custom qtables by writing temp file.
- [ ] 1.3 Rewrite `_reencode_jpeg()` to use cjpeg for the final encode when available, with Pillow fallback. Quality < 85 still uses Pillow for the intermediate padded encode. Skip mozjpeg-lossless-optimization when cjpeg is used.
- [ ] 1.4 Add `fast` parameter to `_reencode_jpeg()` — when True, skip padding and cjpeg, use Pillow directly

## 2. CLI and pipeline plumbing

- [ ] 2.1 Add `--fast` flag to CLI (`cli.py`) in the build command
- [ ] 2.2 Propagate `fast` through config (`config.py`) — add `fast: bool = False` to BuildConfig
- [ ] 2.3 Propagate `fast` through pipeline (`processor/pipeline.py`) — pass to `_reencode_jpeg` via `_refine_jpeg_sizes` and `_process_tile_jpeg`
- [ ] 2.4 Propagate `fast` through garmin_img_writer.py — pass to all `_reencode_jpeg` call sites

## 3. Docker integration

- [ ] 3.1 Add mozjpeg build stage to Dockerfile (clone v4.1.5, cmake, install)
- [ ] 3.2 Copy cjpeg binary to runtime stage

## 4. Cleanup

- [ ] 4.1 Remove benchmark files (`Dockerfile.mozjpeg-benchmark`, `benchmark_mozjpeg.py`) and Docker image `cartoload:mozjpeg-bench`
- [ ] 4.2 Archive the abandoned `mozjpeg-pillow-build` change
