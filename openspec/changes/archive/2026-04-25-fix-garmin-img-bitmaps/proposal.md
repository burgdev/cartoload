# Proposal: Fix Garmin IMG Bitmap Detection and Codepage

## Problem

GMT (GMapTool) reports our generated IMG files with:

- **No bitmaps detected** — `Bitmaps` line is completely missing from GMT output
- **CP 0** instead of `CP 1252, Western European`
- **Empty map name** — shows `>-` instead of the actual map name

The raster tiles (JPEG data) are correctly stored in LBL29 with valid JPEG markers and correct LBL28 offsets. The problem is in the metadata structures that _reference_ the tiles.

## Root Cause Analysis

Traced through the actual bytes of our output file and compared with the format spec in `docs/exporters/garmin-img.md`.

### Bug 1: Type E0 record field order (Critical)

`_write_type_e0_record()` in `garmin_img_writer.py` writes fields in the wrong order:

```
DOC spec:  marker | bits | image_index | lat_min | lon_min | lat_max | lon_max | block_size
Our code:  marker | bits | lat_min     | lon_min | lat_max | lon_max | block_size | image_index
```

The `image_index` is written at the END instead of immediately after `bits_field`. This shifts all subsequent fields, causing GMT to read garbage coordinates, wrong block sizes, and invalid image indices — making it impossible to find any bitmaps.

### Bug 2: LBL encoding byte wrong (High)

`_build_lbl_subheader()` sets `buf[30] = 9` (8-bit international encoding) but the doc specifies value `6` for CP1252 raster maps (Section 3.7 and 6.5). GMT cannot determine the correct codepage from value 9.

### Bug 3: Missing codepage field (Medium)

The LBL header likely needs an explicit uint16 codepage field (value 1252 = 0x04E4) at some offset. Our implementation leaves this area as zeros. This needs verification against the SwissTopo reference file.

### Bug 4: TRE map name empty (Low)

The TRE header has a map name field at offset 0xD3 (null-terminated ASCII). Our code never writes to it. GMT shows `>-` (empty name default).

## Scope

Fix the 4 bugs identified above in `garmin_img_writer.py` and update the doc if needed.

## Out of Scope

- Changes to tile extraction or JPEG encoding (working correctly)
- Changes to FAT, header, or MPS structures (working correctly)
- Multi-map format support
- Analysis tool fixes (separate concern)

## Success Criteria

- GMT reports `Bitmaps N, size S (4)` with correct count and total size
- GMT reports `CP 1252, Western European`
- GMT shows actual map name (not `>-`)
- Existing tests continue to pass
- Output file renders correctly on Garmin devices (manual verification)
