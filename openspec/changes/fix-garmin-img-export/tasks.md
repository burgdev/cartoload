## 1. Header Field Fixes

- [ ] 1.1 Add `creator_length` field to `IMGHeader` dataclass and write it at offset 0x40 (1 byte, value = length of creator string, default 6 for "GARMIN")
- [ ] 1.2 Fix byte ordering of `unknown_size_field` at offset 0x0A-0x0D to match reference hex dumps (verify whether LE or BE based on SwissTopo samples)
- [ ] 1.3 Set `checksum_or_id` at offset 0x0E-0x0F to a non-zero file-specific value (use `0x0050` from SwissTopo_West as default)
- [ ] 1.4 Add flags/version bytes at offset 0x69-0x6A matching reference value `01 20`
- [ ] 1.5 Verify and document the FAT descriptor block at offset 0x1C0-0x1CF; write appropriate values if needed for GMT validation
- [ ] 1.6 Update `IMGHeaderWriter.write()` to write all corrected fields in the correct order within the 512-byte buffer

## 2. FAT Chain Implementation

- [ ] 2.1 Create `FATChainWriter` class that takes a list of `SubfileLayout` objects and generates FAT entries for sequential block chains
- [ ] 2.2 Implement chain entry format: each 4-byte entry contains the next block number (LE uint32), with 0xFFFFFFFF for end-of-chain and 0x00000000 for unused/reserved blocks
- [ ] 2.3 Reserve blocks 0-2 (or appropriate range) for header, FAT region, and subfile directory (mark as reserved in FAT)
- [ ] 2.4 Write FAT entries for GMP subfile chain: blocks from `gmp_layout.start_block` to `gmp_layout.start_block + num_gmp_blocks - 1`
- [ ] 2.5 Write FAT entries for MPS subfile chain: blocks from `mps_layout.start_block` to `mps_layout.start_block + num_mps_blocks - 1`
- [ ] 2.6 Integrate `FATChainWriter` into `IMGWriter.write()` to replace the zero-filled FAT placeholder

## 3. Subfile Directory Format Fix

- [ ] 3.1 Verify subfile directory entry binary layout against GMT expectations by comparing output with SwissTopo reference files
- [ ] 3.2 Fix the subfile name field (ensure 8-byte field at correct offset within entry, null-padded)
- [ ] 3.3 Fix the subfile type field (ensure 3-byte ASCII at correct offset)
- [ ] 3.4 Verify start_block and length fields are at the correct offsets within the 512-byte entry
- [ ] 3.5 Ensure directory entries are properly terminated/padded if fewer entries than allocated space

## 4. GMP Tile Index Offset Fix

- [ ] 4.1 Calculate the correct base offset for tile data within the GMP subfile (GMP_HEADER_SIZE + zoom_table_size + draw_order_size + tile_index_size)
- [ ] 4.2 Update `_build_tile_records()` to compute tile offsets starting from the correct base offset instead of 0
- [ ] 4.3 Verify that tile data offsets, when added to the GMP subfile start position in the IMG file, point to valid JPEG data (FF D8 marker)
- [ ] 4.4 Update `_write_tile_index()` to write the corrected offsets

## 5. Test Updates

- [ ] 5.1 Update `TestIMGHeaderSerialization` tests to verify the new creator_length byte at offset 0x40
- [ ] 5.2 Add test verifying checksum_or_id is written at offset 0x0E-0x0F
- [ ] 5.3 Add test for FAT chain entries: verify chain format, end-of-chain markers, and that all data blocks are covered
- [ ] 5.4 Add test for GMP tile index offsets: verify first tile offset equals GMP_HEADER_SIZE + zoom_table_size + draw_order_size + tile_index_size
- [ ] 5.5 Update `TestSubfileDirectorySerialization` tests if entry layout changes
- [ ] 5.6 Fix existing tests that may break due to header field changes (creator string offset, new fields)

## 6. E2E Validation Test

- [ ] 6.1 Create E2E test fixture: minimal GeoTIFF (2x2 or 4x4 pixels, EPSG:4326, covering small area like 8.0-8.5E, 47.0-47.5N)
- [ ] 6.2 Write E2E test that creates a 2-zoom-level IMG (e.g., zoom 12 and 13), extracts tiles from the GeoTIFF, and writes the IMG file
- [ ] 6.3 Verify the output IMG file size is proportional to the tile data (not undersized)
- [ ] 6.4 Verify DSKIMG magic and boot signature in the output file
- [ ] 6.5 Add `@pytest.mark.gmt` test that runs `gmt -i -v` on the output and asserts no "Wrong header" errors (skip if gmt not available)

## 7. Regression and Cleanup

- [ ] 7.1 Run full test suite and fix any failures from the changes
- [ ] 7.2 Verify `gmt` validation passes on a non-trivial IMG file (multiple zoom levels, multiple tiles)
- [ ] 7.3 Update `docs/exporters/garmin-img.md` if any new format findings were discovered during the fix
- [ ] 7.4 Review `garmin_img_model.py` dataclass fields for consistency with the corrected writer
