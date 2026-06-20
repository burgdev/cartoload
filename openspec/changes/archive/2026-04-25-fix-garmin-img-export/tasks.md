## 1. Header Field Fixes

- [x] 1.1 Verify offset 0x40: currently writes `FAT_BLOCK_NUMBER` (8) which happens to equal length of "GARMIN" — investigate if this is correct or if a separate `creator_length` field is needed
- [x] 1.2 Fix byte ordering of `unknown_size_field` at offset 0x0A-0x0D to match reference hex dumps (verify whether LE or BE based on SwissTopo samples)
- [x] 1.3 Set `checksum_or_id` at offset 0x0E-0x0F to a non-zero file-specific value (use `0x0050` from SwissTopo_West as default)
- [x] 1.4 Add flags/version bytes at offset 0x69-0x6A matching reference value `01 20`
- [x] 1.5 Verify and document the FAT descriptor block at offset 0x1C0-0x1CF; write appropriate values if needed for GMT validation
- [x] 1.6 Update `IMGHeaderWriter.write()` to write all corrected fields in the correct order within the 512-byte buffer

## 2. Test Updates

- [x] 2.1 Update `TestIMGHeaderSerialization` tests to verify the new creator_length byte at offset 0x40
- [x] 2.2 Add test verifying checksum_or_id is written at offset 0x0E-0x0F
- [x] 2.3 Add test for FAT chain entries: verify chain format, end-of-chain markers, and that all data blocks are covered
- [x] 2.4 Fix existing tests that may break due to header field changes (creator string offset, new fields)

## 3. E2E Validation Test

- [x] 3.1 Create E2E test fixture: minimal GeoTIFF (2x2 or 4x4 pixels, EPSG:4326, covering small area like 8.0-8.5E, 47.0-47.5N)
- [x] 3.2 Write E2E test that creates a 2-zoom-level IMG (e.g., zoom 12 and 13), extracts tiles from the GeoTIFF, and writes the IMG file
- [x] 3.3 Verify the output IMG file size is proportional to the tile data (not undersized)
- [x] 3.4 Verify DSKIMG magic and boot signature in the output file
- [x] 3.5 Add `@pytest.mark.gmt` test that runs `gmt -i -v` on the output and asserts no "Wrong header" errors (skip if gmt not available)

## 4. Regression and Cleanup

- [x] 4.1 Run full test suite and fix any failures from the changes
- [x] 4.2 Verify `gmt` validation passes on a non-trivial IMG file (multiple zoom levels, multiple tiles)
- [x] 4.3 Update `docs/exporters/garmin-img.md` if any new format findings were discovered during the fix
- [x] 4.4 Review `garmin_img_model.py` dataclass fields for consistency with the corrected writer

---

**Sections removed (completed by `fix-garmin-raster-lbl-rgn-sections` change):**

- ~~Section 2: FAT Chain Implementation~~ — Completed via `FATWriter` class with sequential block chains
- ~~Section 3: Subfile Directory Format Fix~~ — Completed via `FATWriter._write_special_entry` and `_write_subfile_entries`
- ~~Section 4: GMP Tile Index Offset Fix~~ — Obsolete: tile index table removed entirely, replaced by LBL28 (image index) + LBL29 (image storage)
