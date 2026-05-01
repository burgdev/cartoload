## 1. TileMetadata Model and Computation

- [ ] 1.1 Add `TileMetadata` dataclass to `garmin_img_model.py` with fields: `x: int, y: int, zoom: int, lat_min: float, lon_min: float, lat_max: float, lon_max: float, jpeg_size: int, source_path: Path | None`
- [ ] 1.2 Add `compute_tile_metadata(tile_coords, zoom, source_crs, downloader) -> list[TileMetadata]` function that computes bounds from tile grid math and JPEG sizes from source file stat. Place in a new module `processor/tile_metadata.py` or in `garmin_img_model.py`.
- [ ] 1.3 Verify: unit tests for `TileMetadata` bounds computation (EPSG:3857 and EPSG:4326), JPEG size from stat, correct bounds for edge tiles at zoom boundaries

## 2. Refactor generate_subdivisions to use TileMetadata

- [ ] 2.1 Add `generate_subdivisions_from_metadata(tile_metadata_by_zoom, sorted_zoom_levels, bounds) -> list[Subdivision]` alongside the existing `generate_subdivisions()`. The new function accepts `dict[int, list[TileMetadata]]` and uses `TileMetadata` bounds fields instead of unpacking `(bytes, bounds)` tuples.
- [ ] 2.2 Verify: `generate_subdivisions_from_metadata` produces identical subdivisions as `generate_subdivisions` for the same tile set (comparison test using existing test data)

## 3. Refactor LayoutComputer to use TileMetadata

- [ ] 3.1 Add `LayoutComputerFromMetadata` class (or extend `LayoutComputer`) that accepts `dict[int, list[TileMetadata]]` instead of `CompressedTiles`. The `_compute_gmp_size()` method reads `metadata.jpeg_size` instead of `len(jpeg_data)`.
- [ ] 3.2 Verify: Layout computed from metadata produces identical section sizes and offsets as layout from `CompressedTiles` for the same tile set

## 4. Streaming GMP Writer

- [ ] 4.1 Create `StreamingGMPWriter` class with a two-phase architecture: `compute_layout(img_file, tile_metadata_by_zoom, subdivisions)` returns a layout object with all offsets; `write_stream(f, img_file, tile_metadata_by_zoom, layout, subdivisions, downloader, processor)` streams JPEG data in batches.
- [ ] 4.2 The write_stream phase writes RGN2 records (which need bounds but not JPEG data) directly from `TileMetadata`. It then writes LBL28 offsets and LBL29 JPEG data in batches: for each batch of 500 tiles, read source → warp → write JPEG to IMG, accumulate LBL28 offsets.
- [ ] 4.3 Handle LBL28/LBL29 offset computation during streaming: since warped JPEG sizes may differ from source sizes, the write pass computes LBL28 offsets as a running counter during the write, then seeks back to write the LBL28 section after all LBL29 data is written.
- [ ] 4.4 Verify: `StreamingGMPWriter` produces bit-for-bit identical output to `GMPWriter` for small test cases (< 50 tiles across 3 zoom levels)

## 5. Pipeline Refactor: Metadata-Only Processing

- [ ] 5.1 Refactor `pipeline.py:build_layer()` to produce `dict[int, list[TileMetadata]]` instead of `compressed_tiles`. Replace the `BatchTileProcessor.process_zoom_level()` call with `compute_tile_metadata()` — no JPEG processing in the pipeline.
- [ ] 5.2 Remove `compressed_tiles` accumulation from the pipeline. The pipeline now produces metadata only, and the exporter handles JPEG processing during the write pass.
- [ ] 5.3 Update `export_from_tiles()` to accept `dict[int, list[TileMetadata]]` as primary input (keep `CompressedTiles` as legacy fallback with deprecation warning).
- [ ] 5.4 Verify: `just check types` passes, existing tests pass with new pipeline flow

## 6. Integration and Validation

- [ ] 6.1 Update `_write_with_splitting()` and `_compute_zoom_splits()` to work with `TileMetadata` — size estimation from `metadata.jpeg_size` instead of actual JPEG data
- [ ] 6.2 Run `just check && just check types && just test` — all pass
- [ ] 6.3 End-to-end validation: `cartoload build -S examples/configs/sources/swisstopo.yaml -L examples/configs/layers/switzerland.yaml -l ch_basemap_test -y 46.93459 -x 7.51105 -W 5 -H 5 -f --preview` produces valid IMG with streaming writer, output identical to previous writer
- [ ] 6.4 Memory validation: build with `-W 20 -H 20` (larger area, ~40K tiles) and verify peak memory stays under 500 MB (manual observation or `tracemalloc`)
