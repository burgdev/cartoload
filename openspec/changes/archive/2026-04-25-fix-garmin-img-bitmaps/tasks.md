# Tasks: Fix Garmin IMG Bitmap Detection and Codepage

## Tasks

- [x] 1. Fix Type E0 record field order in `_write_type_e0_record()` — move `image_index` write to immediately after `bits_field`, before coordinates
- [x] 2. Fix LBL encoding byte from 9 to 6 in `_build_lbl_subheader()` — **corrected**: SwissTopo reference actually uses encoding=9; real fix is adding codepage uint16 (1252) at LBL offset 0xAA
- [x] 3. Research: hex-dump SwissTopo reference LBL header to find codepage field offset; add codepage uint16 (1252) to `_build_lbl_subheader()` if found — found at offset 0xAA
- [x] 4. Write map name to TRE header at offset 0xD3 in `_build_tre_subheader()`
- [x] 5. Fix `img_analysis.py` TRE7 parser to use rec_size from descriptor instead of hardcoded 4-byte parsing
- [x] 6. Update doc `garmin-img.md` Section 4.5.2 to clarify exact byte layout of Type E0 record with offset table showing both 8-bit and 16-bit index variants
- [x] 7. Run `cartoload build --layer ch_basemap_test`, verify GMT shows bitmaps, CP 1252, and correct map name
- [x] 8. Run full test suite and fix any broken byte-level assertions

## Key Finding: LBL Raster Section Descriptor Offsets

The root cause of bitmaps not being detected was that the LBL sub-header was writing
the raster image table (LBL28) and raster image data (LBL29) descriptors at the wrong
offsets within the LBL header.

**Wrong offsets** (old code):

- LBL28: offset 0x108 (position) + 0x10C (size)
- LBL29: offset 0x116 (position) + 0x11A (size)

**Correct offsets** (verified from IOM reference and GPXSee source `lblfile.cpp`):

- Raster table (LBL28): offset **0x184** (position) + **0x188** (size) + **0x18C** (recordSize=4)
- Raster image data (LBL29): offset **0x192** (position) + **0x196** (size)

GPXSee reads the raster section at `LBL+0x184` with the following layout:

```
LBL+0x184: uint32 raster_table_offset
LBL+0x188: uint32 raster_table_size
LBL+0x18C: uint16 record_size (always 4 for uint32 offsets)
LBL+0x18E: uint32 flags (0 for raster maps)
LBL+0x192: uint32 raster_image_data_offset
LBL+0x196: uint32 raster_image_data_size
```

The LBL header must be at least 0x19A (410) bytes for GPXSee/GMT to read the raster
section. Our LBL_HEADER_LENGTH of 596 bytes is sufficient.

## Verification Results

GMT output after fix:

```
Bitmaps 140, size 93520 (4)
CP 1252
```

All 76 tests pass, 2 skipped (obsolete tile index tests).
