## 1. Forward quality parameter in pipeline

- [x] 1.1 Add `quality: int | None = None` parameter to `build_composite_layer()` in `src/cartoload/pipeline.py`
- [x] 1.2 Pass `quality=quality` in the call from `build_layer()` to `build_composite_layer()`
- [x] 1.3 Pass `quality=quality` in the call from `build_composite_layer()` to `_make_composite_processor()`
- [x] 1.4 Add `quality: int | None = None` parameter to `_make_composite_processor()`, use it as `effective_quality` inside the closure instead of the writer's `quality` argument

## 2. Verify

- [x] 2.1 Run `just check` and `just check types` to verify formatting and type correctness
- [x] 2.2 Run `just test` to verify all tests pass
