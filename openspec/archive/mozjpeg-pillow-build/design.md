## Context

Pillow ships with libjpeg-turbo as its JPEG backend. mozjpeg is an API-compatible superset of libjpeg-turbo that adds trellis quantization for better lossy compression. Since mozjpeg is ABI-compatible, Pillow can use it transparently when compiled against it.

## Goals / Non-Goals

**Goals:**
- Use mozjpeg's trellis quantization for 3-8% smaller JPEG tiles at same visual quality
- Keep standard Pillow compatibility for local development (graceful fallback)
- Only affect Docker builds (where we control the build environment)

**Non-Goals:**
- No application code changes (this is purely a build-time change)
- No custom Python package for mozjpeg (just compile Pillow against it)
- No changes to quality settings, quantization tables, or encoding parameters

## Decisions

### D1: Build mozjpeg from source in Docker

**Choice**: Clone mozjpeg from GitHub, build with cmake, install as shared library, then build Pillow from source against it.

**Rationale**: mozjpeg is API/ABI-compatible with libjpeg-turbo. Pillow's `setup.py` detects the system libjpeg via `pkg-config` or standard paths. Installing mozjpeg to `/usr/local` makes Pillow pick it up automatically.

**Alternatives considered**:
- Shell out to `cjpeg` per tile: 10ms process spawn × 585K tiles = 1.6h overhead. Not viable.
- ctypes/cffi wrapper: High maintenance, no benefit over compiling Pillow.
- `mozjpeg-lossless-optimization` package: Already handled in separate change. Only does lossless, not trellis quantization.

### D2: Use Docker multi-stage build

**Choice**: Add a build stage that compiles mozjpeg, then use it in the final image.

**Rationale**: Keeps the Dockerfile clean. The mozjpeg build artifacts are ~20 MB; only the shared library is needed in the final image.

### D3: Verify mozjpeg is active at runtime

**Choice**: Add a startup check that logs which JPEG backend is in use.

**Rationale**: Makes it easy to verify the build worked. Can check via `PIL.features.check_codec("jpg")` or by inspecting the version string.

## Risks / Trade-offs

- **Docker build complexity** → Adds ~2 min to Docker build time for mozjpeg compilation. → Acceptable.
- **Alpine/musl compatibility** → mozjpeg may need adjustments for musl libc if using Alpine-based images. → Use Debian-based images.
- **Pillow version pinning** → Building from source means the pinned wheel version won't be used. Need to ensure the same Pillow version is compiled. → Pin version in pip install.
- **Debugging** → If mozjpeg causes issues, it's hard to tell from Pillow's side. → Add runtime logging of the JPEG backend.
