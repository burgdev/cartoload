## Context

cjpeg is currently detected at module import time via `_CJPEG_PATH = shutil.which("cjpeg")`. The `_encode_cjpeg()` function checks `_CJPEG_PATH` and falls back to Pillow if it's `None`. The `--fast` flag bypasses `_encode_cjpeg` entirely, using Pillow directly in `_reencode_jpeg()`.

There are three encoding paths in `_reencode_jpeg()`:
1. `fast=True`: Pillow only, no padding, no cjpeg
2. `fast=False`, quality < 85: Mirror-pad → Pillow encode → decode → crop → cjpeg final encode
3. `fast=False`, quality >= 85: Direct cjpeg encode

The new flag needs to control whether cjpeg is used in paths 2 and 3, independent of `--fast`.

## Goals / Non-Goals

**Goals:**
- Add `--mozjpeg` / `--no-mozjpeg` CLI flag with three-state behavior (auto/enable/disable)
- Wire it through pipeline to the encoder
- When `--no-mozjpeg`, paths 2 and 3 use Pillow instead of cjpeg
- When `--mozjpeg` and cjpeg not found, error before processing starts

**Non-Goals:**
- Changing the `--fast` flag behavior (it still skips padding AND cjpeg for speed)
- Adding config file support for this flag (can be added later if needed)

## Decisions

### 1. Use `bool | None` tri-state parameter

The mozjpeg preference flows as `bool | None`:
- `None` (default): auto-detect from PATH (current behavior)
- `True`: require cjpeg, error if missing
- `False`: force Pillow, ignore cjpeg

This maps cleanly to Click's `--flag / --no-flag` pattern with a default of `None`.

### 2. Pass through pipeline, not module-level

Don't modify `_CJPEG_PATH`. Instead, pass `use_mozjpeg: bool | None` through the existing pipeline → exporter → `_reencode_jpeg` → `_encode_cjpeg` chain. The `_encode_cjpeg` function gains a `use_mozjpeg` parameter that overrides the module-level detection.

### 3. Early validation for `--mozjpeg`

When `--mozjpeg` is set and cjpeg is not on PATH, fail immediately in the CLI with a clear error message, before any processing starts.

### 4. `--fast` interaction

`--fast` + `--mozjpeg` is allowed: fast mode skips padding but still uses cjpeg for the final encode (instead of the current behavior of skipping cjpeg). This gives users the combination of "no padding overhead, but still get trellis savings."

This is a behavior change for `--fast`: previously it always skipped cjpeg. Now `--fast` alone still skips cjpeg, but `--fast --mozjpeg` uses cjpeg without padding.

## Risks / Trade-offs

- **`--fast` behavior change**: `--fast` currently skips cjpeg. After this change, `--fast` alone still skips cjpeg (auto-detect with no padding), but `--fast --mozjpeg` will use cjpeg. This is strictly additive — no existing `--fast` usage changes.
- **Parameter proliferation**: Adding another flag. Acceptable since it controls a distinct behavior (encoder choice) that users have asked for.
