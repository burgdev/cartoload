## Why

The `--quality` CLI flag is ignored when building composite (multi-layer) layers. Tiles are always encoded at quality 85, producing IMG files roughly 2-3x larger than single-layer builds with the same quality setting. For example, a multi-layer build with `--quality 30` produces a 35 MB IMG instead of the expected ~15 MB.

## What Changes

- Forward the `quality` parameter from `build_composite_layer()` through `_make_composite_processor()` so it is applied when encoding composited tiles to JPEG.
- Currently the composite export path passes `quality=None` to the exporter with a comment that "quality applied inside the composite processor", but the processor closure never captures the quality value from the pipeline.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

(none — this is a bug fix in existing implementation, no spec-level behavior changes)

## Impact

- `src/cartoload/pipeline.py`: `build_composite_layer()` and `_make_composite_processor()` need the `quality` parameter threaded through.
- No API or config changes. No breaking changes.
