## Why

mozjpeg adds trellis quantization to JPEG encoding, which makes smarter decisions about which DCT coefficients to zero out. At low quality settings (like quality 25), this produces 3-8% smaller files with the same or better visual quality. The `mozjpeg-lossless-optimization` post-processing approach (separate change) only optimizes the bitstream representation — it cannot apply trellis quantization, which requires re-encoding from pixel data.

## What Changes

- **Build mozjpeg in Docker**: Add mozjpeg build steps to the Dockerfile, compile it as a shared library
- **Compile Pillow against mozjpeg**: Build Pillow from source in Docker so it uses mozjpeg instead of libjpeg-turbo for lossy encoding
- **Fall back to standard Pillow**: In non-Docker environments (development, CI without mozjpeg), use standard Pillow — no mozjpeg features required
- This is an **infrastructure change** — no application code changes needed. Pillow transparently uses whatever libjpeg-compatible library it was compiled against.

## Capabilities

### New Capabilities

_None_ (infrastructural — Pillow uses mozjpeg automatically)

### Modified Capabilities

_None_ (the `jpeg-border-padding` spec's behavior doesn't change, just the underlying encoder)

## Impact

- `Dockerfile` or `docker/Dockerfile` — add mozjpeg build steps, compile Pillow from source
- `pyproject.toml` — may need to adjust Pillow dependency to allow source builds
- CI pipeline — may need mozjpeg available for consistent builds
- Local development — unchanged (standard Pillow works fine, just without trellis quantization)
- Expected file size reduction: 3-8% on top of progressive + mozjpeg post-processing
