## Why

The Garmin IMG exporter produces files that fail GMT validation with "Wrong header (block size)" for real-world workloads and "Bad data in TRE subfile" for multi-tile files. The output file is also dramatically undersized (1.4 MB vs 46 MB cache). The root cause is that the GMP subfile uses a custom flat header format instead of the Garmin-standard GMP container format that embeds TRE, RGN, LBL, and NET sub-headers within the GMP data.

Analysis of reference SwissTopo IMG files reveals that GMP is a **container format** with:

1. A 53-byte "GARMIN GMP" header pointing to embedded sub-file headers
2. Embedded TRE, RGN, LBL, NET sub-headers (each with "GARMIN XXX" signatures)
3. Section data for each sub-file (tile index in TRE, bitmap tiles in RGN, labels in LBL)

The mkgmap Java source confirms the exact binary layout of each sub-header. Our current writer writes a flat 512-byte header with bounds/zoom/tile metadata in a proprietary format that GMT cannot parse.

Additionally, the output file size mismatch (1.4 MB vs 46 MB) needs investigation — tiles may not be fully written or the tile extraction/compression pipeline may have issues.

## What Changes

### GMP Container Format Rewrite

The GMP subfile writer (`GMPWriter` in `garmin_img_writer.py`) must be completely rewritten to produce the standard Garmin GMP container format:

1. **GMP Container Header** (53 bytes): header_size(1) + flag(1) + "GARMIN GMP"(10) + version(2) + date(7) + section_table_offset(4) + section_table(7×4=28 bytes) = 53 bytes
2. **Copyright strings**: Null-terminated strings after the container header
3. **TRE sub-header**: len(2) + "GARMIN TRE"(10) + version(1) + lock(1) + date(7) + bounds(4×3=12 bytes) + map_levels_info + subdivision_info + display_priority + section pointers
4. **RGN sub-header**: len(2) + "GARMIN RGN"(10) + version(1) + lock(1) + date(7) + data_section(pos+size) + ext_type sections
5. **LBL sub-header**: len(2) + "GARMIN LBL"(10) + version(1) + lock(1) + date(7) + label_section(pos+size) + offset_multiplier + encoding + codepage
6. **NET sub-header**: len(2) + "GARMIN NET"(10) + version(1) + lock(1) + date(7) + network section info
7. **Map info section**: "Raster Map" description + copyright string (between sub-headers)
8. **TRE data**: Zoom level table + tile subdivision records
9. **RGN data**: JPEG bitmap tiles
10. **LBL data**: Label strings (can be minimal for raster maps)

### Tile Data Pipeline Fix

Investigate and fix the file size discrepancy (1.4 MB output vs 46 MB cache). Possible causes:

- Tiles not being written to the output file
- Tile extraction producing empty/blank tiles
- Tile compression producing zero-length output

### E2E Test with GMT Validation

Add an end-to-end test that:

1. Downloads a small area (2 zoom levels, ~10 tiles)
2. Generates an IMG file
3. Validates with `gmt -i -v` (exit code 0 = success)

## Capabilities

### New Capabilities

- `gmp-container-format`: GMP subfile writer producing standard Garmin GMP container format with embedded TRE/RGN/LBL/NET sub-headers, validated against reference SwissTopo IMG files
- `e2e-gmt-validation`: End-to-end test that downloads tiles, generates IMG, and validates with GMT

### Modified Capabilities

<!-- No existing spec-level behavior changes -->

## Impact

- **`src/cartoload/exporters/garmin_img_writer.py`**: Major rewrite of `GMPWriter` class, new sub-header writer classes
- **`src/cartoload/exporters/garmin_img_model.py`**: Minor updates for GMP container model fields
- **`tests/test_exporter_garmin_img.py`**: Updated tests for new GMP container format
- **`tests/test_e2e.py`**: New E2E test with GMT validation
- **Dependencies**: No new external dependencies
