# Design: Fix Garmin IMG Bitmap Detection and Codepage

## Changes

### 1. Fix Type E0 record field order in `_write_type_e0_record()` (DONE)

**File:** `src/cartoload/exporters/garmin_img_writer.py`

Moved `image_index` to immediately after `bits_field`, before coordinates.
Record size: 23 bytes (8-bit index, bits_field=0x2B) or 24 bytes (16-bit index, bits_field=0x25).

### 2. Fix LBL encoding byte (DONE)

**File:** `src/cartoload/exporters/garmin_img_writer.py`, function `_build_lbl_subheader()`

Research showed SwissTopo reference actually uses encoding=9, not 6.
The encoding byte stays at 9; the real fix for codepage display was adding the
codepage uint16 at offset 0xAA (change #3 below).

### 3. Add codepage field to LBL header (DONE)

Added at LBL offset 0xAA:

```python
struct.pack_into("<H", buf, 0xAA, 1252)
```

### 4. Write TRE map name (DONE)

Added map name at TRE+0xD3 (null-terminated ASCII):

```python
name_str = img_file.header.map_name or "Raster Map"
name_bytes = name_str.encode("ascii")[:TRE_HEADER_LENGTH - 0xD3 - 1]
buf[0xD3 : 0xD3 + len(name_bytes)] = name_bytes
buf[0xD3 + len(name_bytes)] = 0x00
```

### 5. Fix LBL raster section descriptor offsets (CRITICAL FIX)

**File:** `src/cartoload/exporters/garmin_img_writer.py`, function `_build_lbl_subheader()`

**Root cause of bitmaps not being detected.** The raster image table (LBL28) and
raster image data (LBL29) descriptors were being written at wrong offsets in the
LBL sub-header.

Discovered by:

1. Binary comparison with IOM reference file's LBL header
2. GPXSee source code (`lblfile.cpp`) which reads raster sections at `LBL+0x184`

**Old (wrong) offsets:**

```python
# LBL28 at 0x108/0x10C — these offsets are in the "places section" area, not raster
struct.pack_into("<I", buf, 0x108, lbl28_pos)
struct.pack_into("<I", buf, 0x108 + 4, lbl28_size)
# LBL29 at 0x116/0x11A
struct.pack_into("<I", buf, 0x116, lbl29_pos)
struct.pack_into("<I", buf, 0x116 + 4, lbl29_size)
```

**Correct offsets (verified from IOM reference and GPXSee `lblfile.cpp`):**

```python
# Raster table (LBL28) at 0x184/0x188/0x18C
struct.pack_into("<I", buf, 0x184, lbl28_pos)   # raster table offset
struct.pack_into("<I", buf, 0x188, lbl28_size)   # raster table size
struct.pack_into("<H", buf, 0x18C, 4)            # record size: uint32 offsets
# 0x18E: flags (4 bytes, 0 for raster maps) — already zero

# Raster image data (LBL29) at 0x192/0x196
struct.pack_into("<I", buf, 0x192, lbl29_pos)    # raster data offset
struct.pack_into("<I", buf, 0x196, lbl29_size)   # raster data size
```

**GPXSee reads this as (from `lblfile.cpp`):**

```cpp
if (hdrLen >= 0x19A) {
    // At LBL + 0x184:
    readUInt32(hdl, offset);     // 0x184: raster table offset
    readUInt32(hdl, size);       // 0x188: raster table size
    readUInt16(hdl, recordSize); // 0x18C: record size
    readUInt32(hdl, flags);      // 0x18E: flags
    readUInt32(hdl, _img.offset);// 0x192: raster data offset
    readUInt32(hdl, _img.size);  // 0x196: raster data size
}
```

**The LBL header must be >= 0x19A (410) bytes** for GPXSee/GMT to read the raster
section. Our LBL_HEADER_LENGTH of 596 bytes is sufficient.

## Verification Results

GMT output after all fixes:

```
Bitmaps 140, size 93520 (4)
CP 1252
```

All 76 tests pass, 2 skipped (obsolete tile index tests).
