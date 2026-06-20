## 1. Constants and validation

- [x] 1.1 Add `MAX_GMP_SIZE = 1_800_000_000` constant (~1.8 GB) to `garmin_img_writer.py`
- [x] 1.2 Add validation in `SubfileLayout.__init__` that `data_size <= MAX_GMP_SIZE`, raising clear error if violated
- [x] 1.3 Add validation in `FATWriter._write_subfile_entries` that `num_fat_entries <= 256` before writing

## 2. Tile partitioning into geographic bands

- [x] 2.1 Add `_compute_gmp_groups(tile_metadata, zoom_levels, bounds)` function that partitions tiles into groups by latitude bands, each fitting within MAX_GMP_SIZE
- [x] 2.2 Each group contains: its tile metadata, the full map bounds, a unique map_id (derived from base + group index), and all zoom levels
- [x] 2.3 Groups produce separate IMG files (not multiple GMP subfiles in one IMG) — FAT block numbers are uint16, limiting total IMG size to ~2 GB

## 3. Multi-IMG file writing

- [x] 3.1 Update `export_from_metadata()` to detect when multiple groups are needed
- [x] 3.2 Write one IMG file per geographic band, each with unique map_id and separate FAT/headers
- [x] 3.3 Derive filenames as `{stem}_1.img`, `{stem}_2.img`, etc.
- [x] 3.4 Remove multi-GMP-in-one-IMG code (LayoutComputer._compute_multi_gmp, StreamingIMGWriter gmp_groups param, _make_group_img)

## 4. Testing

- [x] 4.1 Test `_compute_gmp_groups` returns single group when data fits
- [x] 4.2 Test `_compute_gmp_groups` returns multiple groups when data exceeds threshold
- [x] 4.3 Test groups have unique map_ids and full map bounds
- [x] 4.4 Test single-IMG writer produces valid output
- [x] 4.5 Run `just check` — lint and format pass
- [x] 4.6 Run `just tests` — 424 passed, 8 pre-existing failures unrelated
- [x] 4.7 Test Switzerland build completes without error
- [x] 4.8 Validate output with `cartoload analyze img info`
