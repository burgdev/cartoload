## Context

The cartoload pipeline encodes map tiles as JPEG for Garmin IMG format. The critical encoding path is `_reencode_jpeg()` in `garmin_img_writer.py`, which:
1. Decodes the source JPEG
2. Mirror-pads edges (quality < 85) to prevent border artifacts
3. Re-encodes at the target quality with optional custom quantization tables
4. Applies mozjpeg lossless bitstream optimization

Benchmarks showed mozjpeg's `cjpeg` binary with trellis quantization produces 12-24% smaller files than Pillow at quality 25-75. Pillow and TurboJPEG APIs do NOT trigger trellis — only the full libjpeg compress API path does, which `cjpeg` uses. The subprocess overhead is ~10ms/tile (vs 0.8ms for Pillow), but with 4 parallel workers the effective overhead is ~2.5ms/tile (3-4x slower overall). For GPS devices with limited storage, 24% more map data is worth the build time increase.

## Goals / Non-Goals

**Goals:**
- Use cjpeg subprocess for final JPEG encode in `_reencode_jpeg()` to activate trellis quantization
- Provide `--fast` flag that skips mirror-padding and cjpeg for quick iteration builds
- Install mozjpeg in Docker for production builds
- Gracefully fall back to Pillow when cjpeg is unavailable (local dev)

**Non-Goals:**
- No ctypes/cffi wrapper around libjpeg (too complex, high maintenance)
- No changes to download, compositing, or binary format writing
- No custom quantization table handling for cjpeg (too niche; when qtables are specified, fall back to Pillow which supports them natively)

## Decisions

### D1: cjpeg subprocess for final encode only

**Choice**: Replace only the final `Pillow.save()` call in `_reencode_jpeg()` with `cjpeg` subprocess. Keep Pillow for the intermediate mirror-padding encode (which simulates JPEG artifacts at edges).

**Rationale**: The mirror-padding path does decode → pad → **Pillow encode** → decode → crop → **final encode**. The intermediate Pillow encode must stay because it simulates JPEG blocking artifacts with the padded border context. Only the final encode benefits from trellis. For quality >= 85 (no padding), the single encode switches to cjpeg directly.

**Data flow**:
```
quality < 85:
  decode → mirror-pad → Pillow encode → decode → crop →
  raw RGB → cjpeg encode (trellis)

quality >= 85:
  decode → raw RGB → cjpeg encode (trellis)

--fast mode (any quality):
  decode → Pillow encode (no padding, no cjpeg)
```

### D2: Custom qtables → Pillow fallback

**Choice**: When custom quantization tables are specified, fall back to Pillow encoding. Do not implement `-qtables FILE` support for cjpeg.

**Rationale**: Custom qtables are a niche feature used with `--qtables raster`. cjpeg requires tables in a file format, adding complexity. Pillow supports qtables natively. The qtables path remains unchanged — only the default-table path gets cjpeg.

Wait — actually this is important since the test command uses `--qtables raster`. Let me reconsider.

**Revised**: Support cjpeg with custom qtables by writing them to a temp file in cjpeg's expected format. The `iom_qtables_for_quality()` function returns the tables in zigzag order — cjpeg expects the same format in its `-qtables` file.

Actually, looking more carefully: cjpeg's `-qtables FILE` format expects 64 values per table (8x8 in natural order, one per line). Pillow's `qtables` parameter expects zigzag order. We'd need to convert. This adds complexity.

**Final decision**: When qtables are specified, use cjpeg with `-qtables FILE`. Convert from zigzag to natural order and write to a temp file. This ensures the test command (`--qtables raster`) gets the full trellis benefit.

### D3: --fast flag skips padding AND cjpeg

**Choice**: `--fast` flag bypasses both mirror-padding and cjpeg. Falls back to a single Pillow encode at the target quality.

**Rationale**: Mirror-padding and cjpeg are the two expensive steps. Skipping both gives the fastest possible build. The output is larger but visually fine for previews and iteration.

### D4: Docker mozjpeg build stage

**Choice**: Add a mozjpeg build stage to the existing Dockerfile. Clone mozjpeg v4.1.5, build with cmake, install to `/usr/local`. The cjpeg binary ends up at `/usr/local/bin/cjpeg`.

**Rationale**: mozjpeg is ~20MB source, compiles in ~2 min. Only the shared library and cjpeg binary are needed at runtime. Multi-stage build keeps the runtime image clean.

### D5: cjpeg availability detection

**Choice**: On module load, check if `cjpeg` is on PATH using `shutil.which("cjpeg")`. Cache the result. Fall back to Pillow with a single debug-level log message.

**Rationale**: No hard dependency. Local development works without mozjpeg. Docker builds get the benefit automatically.

## Risks / Trade-offs

- **Build time increase** → 3-4x slower re-encode step (~20-30% of total build time). Mitigated by `--fast` flag for quick iterations. → Acceptable for production builds where file size matters.
- **Subprocess overhead** → ~10ms per tile single-threaded, ~2.5ms with 4 workers. For 1.5M tiles, this adds ~1h to build. → Acceptable tradeoff for 24% smaller files.
- **cjpeg binary availability** → Not available on all systems. → Graceful fallback to Pillow.
- **qtables temp files** → Need cleanup. → Use `tempfile` with automatic cleanup or write to a reused buffer.
- **Docker build complexity** → Adds ~2 min to Docker build for mozjpeg compilation. → One-time cost, acceptable.
