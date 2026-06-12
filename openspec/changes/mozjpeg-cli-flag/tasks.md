## 1. CLI flag

- [ ] 1.1 Add `--mozjpeg` / `--no-mozjpeg` flag to `cartoload build` in `cli.py` using Click's `flag_value` pattern for tri-state (`None` = auto, `True` = require, `False` = disable)
- [ ] 1.2 Add early validation: when `--mozjpeg` is set and `shutil.which("cjpeg")` returns None, raise `click.ClickException` with a clear message
- [ ] 1.3 Update `--fast` help text to clarify it skips mirror-padding (remove mention of cjpeg since that's now controlled by `--mozjpeg`)

## 2. Pipeline wiring

- [ ] 2.1 Add `mozjpeg: bool | None = None` parameter to `build_target()` in `pipeline.py`
- [ ] 2.2 Pass `mozjpeg` through to `export_from_metadata()` call

## 3. Encoder integration

- [ ] 3.1 Add `use_mozjpeg: bool | None = None` parameter to `_encode_cjpeg()`. When `False`, skip cjpeg and use Pillow directly. When `True` and cjpeg not found, error.
- [ ] 3.2 Add `use_mozjpeg: bool | None = None` parameter to `_reencode_jpeg()`. Pass it through to `_encode_cjpeg()` calls. Update `fast` mode: when `fast=True` and `use_mozjpeg=True`, use cjpeg (instead of always skipping it).
- [ ] 3.3 Add `use_mozjpeg` parameter to `_process_tile_jpeg()` and the batch processing call sites, threading it through to `_reencode_jpeg()`.
- [ ] 3.4 Add `use_mozjpeg` parameter to `export_from_metadata()` and thread it down to the tile processing/batch loop.

## 4. Verify

- [ ] 4.1 Run `just test` and `just check` to confirm everything passes
