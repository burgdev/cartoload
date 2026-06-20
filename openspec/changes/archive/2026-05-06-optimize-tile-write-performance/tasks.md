## 1. Persistent executor with pre-loaded libraries

- [x] 1.1 Add `_init_worker` function in `garmin_img_writer.py` that pre-imports `warp_tile_to_jpeg` and stores it in a module-level global `_warp_func`
- [x] 1.2 Modify `_warp_tile_worker` to use the pre-loaded `_warp_func` global instead of importing `warp_tile_to_jpeg` on every call
- [x] 1.3 Move the `ProcessPoolExecutor` creation outside the batch loop in `_write_gmp_data`, using `initializer=_init_worker`, and shut it down via `try/finally` after all batches

## 2. Configurable executor mode

- [x] 2.1 Add `_get_executor_mode()` function that reads `CARTOLOAD_EXECUTOR` env var (values: `process`, `thread`, default: `process`) with validation
- [x] 2.2 Modify `_write_gmp_data` to choose `ProcessPoolExecutor` or `ThreadPoolExecutor` based on executor mode, using the same `initializer` for both
- [x] 2.3 Add `--executor` CLI parameter (choices: `process`, `thread`) that sets `CARTOLOAD_EXECUTOR` or passes mode directly through the pipeline

## 3. Batch I/O optimizations

- [x] 3.1 Replace per-offset LBL28 write loop with batched bytearray write: pre-allocate `bytearray(len(lbl28_offsets) * 4)`, pack all offsets with `struct.pack_into`, write as single `f.write()` call
- [x] 3.2 Add `jpeg_sizes: list[int]` tracking inline during LBL29 streaming loop, appending `len(jpeg_data)` for each tile
- [x] 3.3 Update `_fixup_rgn2_jpeg_sizes` to accept `jpeg_sizes` directly instead of computing sizes from LBL28 offset differences

## 4. Batch size increase

- [x] 4.1 Change `BATCH_SIZE` constant from 500 to 5000 in `StreamingIMGWriter`

## 5. Tests

- [x] 5.1 Add test for persistent executor: verify that processing N tiles produces correct results with both process and thread executor modes
- [x] 5.2 Add test for batched LBL28 offset write verifying correct output for a multi-tile GMP subfile
- [x] 5.3 Add test for `_fixup_rgn2_jpeg_sizes` with direct `jpeg_sizes` parameter verifying correct RGN2 records
- [x] 5.4 Add test for `_get_executor_mode()` validating env var parsing and invalid input handling
- [x] 5.5 Run full test suite and verify all existing tests pass
