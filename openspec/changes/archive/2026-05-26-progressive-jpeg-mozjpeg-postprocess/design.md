## Context

The Garmin IMG writer encodes JPEG tiles using Pillow's `Image.save(format="JPEG", quality=X, optimize=True)`. This uses baseline JPEG encoding with per-tile Huffman optimization. Two additional optimizations can reduce file size without any visual quality change.

## Goals / Non-Goals

**Goals:**
- Reduce JPEG tile file sizes by 4-7% through progressive encoding and mozjpeg post-processing
- Maintain identical visual quality (both optimizations are lossless)
- Keep Garmin device compatibility (progressive JPEG is standard)

**Non-Goals:**
- Custom quantization tables (separate change)
- Building Pillow against mozjpeg for trellis quantization (separate change)
- Any changes to tile dimensions, mirror padding logic, or quality settings

## Decisions

### D1: Use Pillow's built-in `progressive=True`

**Choice**: Add `progressive=True` to all JPEG save calls.

**Rationale**: Progressive JPEG stores data in multiple scans (coarse to fine). This allows more efficient Huffman coding across scans, typically 2-3% smaller than baseline. It's a one-parameter change with no new dependencies.

**Alternatives considered**:
- Skip progressive: would miss 2-3% savings
- Progressive via mozjpeg-only: would require the mozjpeg dependency for something Pillow can do natively

### D2: Add `mozjpeg-lossless-optimization` as post-processing

**Choice**: After Pillow encodes a tile, pass the JPEG bytes through `mozjpeg_lossless_optimization.optimize()`.

**Rationale**: This is a pip-installable package with pre-built wheels that applies mozjpeg's `jpegtran` optimizations. It's strictly lossless — only reorganizes the bitstream for better compression. Adds 2-5% on top of Pillow's progressive encoding.

**Alternatives considered**:
- Build Pillow against mozjpeg: would give trellis quantization (3-8%), but requires custom builds, complicates Docker and CI. Separate change.
- Subprocess call to `cjpeg`: process spawn overhead per tile (~10ms × 585K tiles = 1.6h extra). The Python package avoids this.

### D3: Apply both optimizations in `_reencode_jpeg`

**Choice**: Modify the existing `_reencode_jpeg` function to add progressive encoding and mozjpeg post-processing.

**Rationale**: This is the single point where all tile JPEG encoding happens. All callers benefit automatically. The function already handles the mirror-padding flow, so the optimizations apply to the final encode step only.

## Risks / Trade-offs

- **Garmin compatibility** → Progressive JPEG is part of the JPEG standard (ITU-T T.81, 1992). All compliant decoders support it. The IOM reference file uses baseline, but progressive is not a different *format* — it's a different *scan ordering*. Risk is very low. → Mitigation: test on device after implementation.
- **Encoding speed** → Progressive encoding is ~5-10% slower per tile. mozjpeg post-processing adds a small overhead. For 585K tiles this adds a few minutes to the total build time. → Acceptable trade-off for 4-7% smaller files.
- **mozjpeg package maintenance** → The `mozjpeg-lossless-optimization` package is maintained by wanadev, supports Python 3.9-3.13, has pre-built wheels. If it becomes unmaintained, we can remove the post-processing step and still keep progressive encoding. → Low risk.
