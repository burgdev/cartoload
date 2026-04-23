## 1. GMP Container Header Writer

- [x] 1.1 Rewrite `_write_gmp_header()` to produce 53-byte "GARMIN GMP" container header: header_size(1)=0x35 + flag(1)=0x00 + "GARMIN GMP"(10) + version(2)=1 + date(7) + section_table_offset(4)=0x19 + section_offsets(7×4=28, all zeros initially)
- [x] 1.2 Write copyright strings after container header (null-terminated, padded to reach TRE sub-header offset)
- [x] 1.3 Add helper `_compute_gmp_layout()` that calculates exact byte offsets for all sub-headers and data sections, then patches the section offsets into the container header

## 2. TRE Sub-Header Writer

- [x] 2.1 Implement `_build_tre_subheader()` writing common header (21 bytes): header_length(uint16 LE) + "GARMIN TRE"(10) + version(1)=1 + lock(1)=0 + date(7)
- [x] 2.2 Write TRE-specific fields after common header: bounds as 4×3-byte signed LE map units (max_lat, max_lon, min_lat, min_lon where map_unit = deg × 2^24 / 360)
- [x] 2.3 Write map_levels section info (position + size), subdivisions section info (position + size), copyright section info, POI flags, display priority (24 for raster), and polyline/polygon/points section info (all zeros for raster)
- [x] 2.4 Write map info strings after TRE header: "Raster Map\0" + copyright string + "CP 1252\0" + encoding info

## 3. RGN Sub-Header Writer

- [x] 3.1 Implement `_build_rgn_subheader()` with 125-byte header: common header (21 bytes) + data_section(position+size=8 bytes) + ext_type sections (all zeros, 96 bytes)
- [x] 3.2 Write RGN data section with per-subdivision structured records (reference: 1582 bytes for ~32K tiles — NOT the actual JPEG data)
- [x] 3.3 Write RGN ext_type_areas section (minimal/zero for simplified raster — not needed for GMT validation)

## 4. LBL and NET Sub-Header Writers

- [x] 4.1 Implement `_build_lbl_subheader()` with common header + label_section(position+size) + offset_multiplier(1)=1 + encoding(1)=6 + places section (zeros) + codepage(2)=1252 + sort ids (zeros)
- [x] 4.1a LBL labels section content: write tile filenames as null-terminated strings (e.g., "0.jpg", "1.jpg") — these serve as tile labels referenced by the label section
- [x] 4.2 Implement `_build_net_subheader()` with common header + network section info (all zeros) — minimal stub for raster maps

## 5. GMP Data Layout Integration

- [x] 5.1 Rewrite `GMPWriter.write()` to compose the full GMP data in correct order: container header → copyright strings → TRE sub-header (with map info strings) → RGN sub-header → LBL sub-header → NET sub-header → TRE data sections → RGN data sections → LBL labels (tile filenames) → tile index table (uint32 array) → JPEG tile data
- [x] 5.2 Update `LayoutComputer._compute_gmp_size()` to account for all sub-headers, section padding, data sections, tile index table, and JPEG data
- [x] 5.3 Implement tile index table writer: array of uint32 LE offsets, each pointing to a JPEG tile's start position within the GMP data area. Offsets are relative to the first JPEG's absolute file position
- [x] 5.4 JPEG tiles are written as standard JFIF JPEG files concatenated sequentially in the tile data area at the end of the GMP subfile

## 6. Update Tests

- [x] 6.1 Update `TestIMGHeaderSerialization` and `TestIMGFileWrite` for new GMP layout (section offsets, sub-header signatures)
- [x] 6.2 Add test verifying "GARMIN GMP" signature at correct offset in GMP data
- [x] 6.3 Add test verifying TRE sub-header has "GARMIN TRE" signature and correct bounds in 3-byte map units
- [x] 6.4 Add test verifying RGN sub-header has "GARMIN RGN" signature and data section info
- [x] 6.5 Add test verifying LBL sub-header has "GARMIN LBL" signature
- [x] 6.6 Add test verifying NET sub-header has "GARMIN NET" signature
- [x] 6.7 Run full test suite and fix all failures — **63/63 tests passing**

## 7. GMT Validation and E2E Test

- [x] 7.1 Generate a multi-tile multi-zoom IMG file and validate with `gmt -i -v` — must return exit code 0. **Result: PASS** — GMT correctly reads header, GMP subfile, bounds, zoom levels, raster map type, MPS subfile.
- [x] 7.2 Add E2E test that downloads small area (2 zoom levels), generates IMG, and validates with GMT (skip if GMT not installed). **Implemented as `test_write_validates_with_gmt` (marked `@pytest.mark.gmt`).**
- [ ] 7.3 Investigate and fix the 1.4 MB vs 46 MB file size discrepancy if still present after GMP rewrite — **DEFERRED**: The GMP writer correctly includes all tiles. The size issue is in the tile extraction/download pipeline, not the IMG writer. Will be addressed as part of pipeline integration testing.
