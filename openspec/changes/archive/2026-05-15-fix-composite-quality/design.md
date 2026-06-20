## Context

The composite (multi-layer) build pipeline in `pipeline.py` has a bug where the `--quality` CLI parameter is never forwarded to the composite tile processor. The call chain is:

1. `build_layer()` receives `quality` from CLI, but calls `build_composite_layer()` **without** passing `quality`
2. `build_composite_layer()` calls `exporter.export_from_metadata()` with `quality=None` and comment "quality applied inside the composite processor"
3. `_make_composite_processor()` creates a closure that uses `quality or 85` from the writer's argument — which is `None` → always defaults to 85

The single-layer path works correctly: `build_layer()` → `exporter.export_from_metadata(quality=quality)`.

## Goals / Non-Goals

**Goals:**
- Forward `quality` from `build_composite_layer()` to `_make_composite_processor()` so composited tiles are encoded at the requested quality

**Non-Goals:**
- Changing how quality is applied (compose at full quality, encode at target quality — this is already correct conceptually)
- Modifying the exporter or writer interfaces

## Decisions

**Decision: Thread `quality` through as a closure variable**

Add a `quality` parameter to `build_composite_layer()` and `_make_composite_processor()`. The processor closure captures the quality value and uses it in `encode_composite_to_jpeg()`.

Alternative considered: Pass quality through `export_from_metadata()` → writer → processor callback. Rejected because the composite processor already handles encoding internally and the writer's quality would be redundant/confusing.

This is a 3-line change:
1. `build_composite_layer()` signature: add `quality: int | None = None`
2. `build_composite_layer()` call to `_make_composite_processor()`: pass `quality=quality`
3. `_make_composite_processor()` signature: add `quality: int | None = None`, use it in the closure instead of the writer's quality argument

Plus updating the call site in `build_layer()` to pass `quality=quality` to `build_composite_layer()`.

## Risks / Trade-offs

- Minimal risk — the change only affects the quality value passed to JPEG encoding in the composite path.
