# Tile Storage Format

This page describes how raster tiles are stored inside the GMP subfile: JPEG data, LBL28/LBL29 index and storage, RGN2 compound records, and the DeltaStream bitstream encoding. For the spatial index that organizes tiles, see [TRE Sections](tre-sections.md). For the GMP container that holds all this data, see [GMP Container](gmp-container.md).

## 4. Tile Storage Format

### 4.1 JPEG Tile Data

**Tiles are stored as standard JFIF JPEG files**, concatenated sequentially at the end of the GMP subfile. Each tile begins with the JPEG start-of-image marker `FFD8FFE0` followed by `JFIF`.

Verified from reference files:

- Tile sizes range from ~10KB to ~65KB each
- All 32,254 tiles in reference files verified to have valid JPEG start markers

### 4.2 LBL Labels (Tile Filenames)

The LBL labels section stores tile filenames as null-terminated ASCII strings:

```
"0.jpg\0" "1.jpg\0" "2.jpg\0" ...
```

These serve as tile labels referenced by the LBL section.

### 4.3 LBL28 (Image Index)

The LBL28 section contains an array of uint32 little-endian offsets pointing to JPEG images in LBL29. Each offset is relative to the start of the LBL29 section.

**Format:**

```
LBL28: [offset_0][offset_1][offset_2]...[offset_N-1]
  where each offset is uint32 LE (4 bytes)
  offset_0 = 0 (first JPEG starts at LBL29 beginning)
  offset_i = cumulative size of all JPEGs before index i
```

**Example:** For 3 JPEGs of sizes [880, 920, 1024] bytes:

```
LBL28: [0x00000000][0x00000370][0x00000708]
       (0, 880, 1800 in decimal)
```

**LBL28 section size:** N × 4 bytes where N = total tile count

**LBL sub-header raster table descriptor (at LBL header offset 0x184):**

| Offset | Size | Field             | Description                                  |
| ------ | ---- | ----------------- | -------------------------------------------- |
| 0x184  | 4    | raster_table_pos  | uint32 LE, GMP-relative offset to LBL28 data |
| 0x188  | 4    | raster_table_size | uint32 LE, total LBL28 section size (N × 4)  |
| 0x18C  | 2    | record_size       | uint16 LE, always 4 (uint32 offsets)         |
| 0x18E  | 4    | flags             | uint32 LE, 0 for raster maps                 |

Verified from IOM reference file and GPXSee source (`lblfile.cpp`). The LBL header
must be ≥ 0x19A (410) bytes for raster readers to find this section.

### 4.4 LBL29 (Image Storage)

The LBL29 section contains concatenated JPEG files with no padding or delimiters between files. JPEGs are stored in the same order as tiles are traversed: sequentially by zoom level, then sequentially within each zoom level.

**Format:**

```
LBL29: [JPEG_0][JPEG_1][JPEG_2]...[JPEG_N-1]
  where each JPEG is a complete JFIF JPEG file
  starting with FFD8FFE0 marker followed by "JFIF"
```

**LBL29 section size:** Sum of all JPEG file sizes

**LBL sub-header raster image data descriptor (at LBL header offset 0x192):**

| Offset | Size | Field            | Description                                  |
| ------ | ---- | ---------------- | -------------------------------------------- |
| 0x192  | 4    | raster_data_pos  | uint32 LE, GMP-relative offset to LBL29 data |
| 0x196  | 4    | raster_data_size | uint32 LE, total LBL29 section size          |

**Relationship:** LBL28[i] contains the byte offset within LBL29 where JPEG tile i begins. Reading LBL29 from offset LBL28[i] yields the i-th JPEG tile.

### 4.5 RGN Data Sections

The RGN data in raster maps is organized into multiple sub-sections. The most important for raster maps are **RGN2** (containing raster tile records) and **RGN5** (metadata).

#### 4.5.1 RGN2 — Raster Tile Compound Records

RGN2 raster tiles are stored as **42-byte compound records**, one per tile. Each record is a single structure containing a polyline-like preamble and a raster tile descriptor. The record is NOT split into separate preamble + E0 records.

**42-byte compound record layout:**

```
Offset | Size | Field           | Description
-------|------|-----------------|------------------------------------------
0      | 1    | type            | 0x06 (polyline-like type for extended objects)
1      | 1    | subtype         | 0xB3 (raster: subtype=0x13 | has_label=0x20 | has_class=0x80)
2      | 2    | lon_delta       | int16 LE — offset from subdivision center (in level-shifted units)
4      | 2    | lat_delta       | int16 LE — offset from subdivision center (in level-shifted units)
6      | 1    | bitstream_len   | VUInt32 = 0x11 (encoded as single byte: 8<<1|1)
7      | 8    | bitstream       | 8-byte DeltaStream bitstream (see Section 4.5.2)
15     | 3    | label_ptr       | uint24 (3 fixed bytes) — conditional on subtype & 0x20
18     | 1    | class_flags     | 0xE0 (flags>>5 = 7, triggers readRasterInfo in GPXSee)
19     | 1    | raster_size_enc | VUInt32 = 0x2D (encoded as single byte: 22<<1|1)
20     | 2    | image_id        | uint16 LE — index into LBL28 offset array
22     | 4    | top             | int32 LE — north bound in 32-bit Garmin units (deg × 2^31 / 180)
26     | 4    | right           | int32 LE — east bound in 32-bit Garmin units
30     | 4    | bottom          | int32 LE — south bound in 32-bit Garmin units
34     | 4    | left            | int32 LE — west bound in 32-bit Garmin units
38     | 4    | jpeg_size       | uint32 LE — JPEG file size in bytes
Total: 42 bytes
```

**Type decoding:** `0x10000 | (0x06 << 8) | (0xB3 & 0x1F) = 0x10613`, matching GPXSee's `isRaster()` check.

**Subtype byte 0xB3 encoding:**

| Bit(s) | Value | Meaning                                            |
| ------ | ----- | -------------------------------------------------- |
| 0-4    | 0x13  | Raster subtype identifier (19 decimal)             |
| 5      | 0x20  | Has label pointer (3-byte uint24 follows bitstream) |
| 6      | 0x00  | Unused                                             |
| 7      | 0x80  | Has class fields (triggers `readRasterInfo` in GPXSee) |

**Lon/lat delta encoding:**

The lon_delta and lat_delta fields are int16 values in **level-shifted map units**. The shift is `max(0, 24 - level_number)` where level_number comes from TRE1 byte 1. The actual offset in 24-bit map units is `delta << shift`. GPXSee reconstructs the tile's boundingRect as a single point at `subdiv_center + (delta << shift)`.

**Warning:** The boundingRect is a rectangle [P0, P1] covering the full tile extent, reconstructed by GPXSee's `copyPolys()` from header deltas (positioning P0) plus bitstream deltas (extending to P1). If the quantization step (2^shift × 360 / 2^24 degrees) is too large, the boundingRect may not accurately cover the tile, causing tiles to be incorrectly filtered out. This is why level_number must be >= 20 for detailed zoom levels (see [TRE1 Map Levels](tre-sections.md#52-tre1--map-levels-zoom-level-table)).

**VUInt32 encoding:** Variable-length unsigned 32-bit integer. Single-byte encoding: `(value << 1) | 1`. Examples: 0→0x01, 8→0x11, 22→0x2D.

**Label pointer:** Fixed 3-byte uint24 value (NOT VUInt32). Read when `subtype & 0x20` is set.

**Coordinate encoding:** Uses 32-bit signed Garmin map units (degrees × 2^31 / 180), distinct from the 3-byte coords used in TRE header bounds.

**RGN data section size:** N × 42 bytes, where N = total tile count.

#### 4.5.2 DeltaStream Bitstream Encoding

The 8-byte bitstream in each RGN2 raster record encodes coordinate deltas following GPXSee's `DeltaStream` format. The bitstream is consumed by `extPolyObjects()` which calls `stream.init(info, false, true)` with `extended=true`.

**Info byte (byte 0):**

```
Low nibble (bits 0-3): lon_baseSize
High nibble (bits 4-7): lat_baseSize
```

The `baseSize` determines the number of bits per delta via GPXSee's `bitSize()` formula:
- `baseSize <= 9`: bits = 2 + baseSize
- `baseSize > 9`: bits = 2 + 2*baseSize - 9
- Plus +1 for fixed-sign mode (sign=0, `variableSign = !sign = true`)

**Bit layout (bytes 1-7, LSB-first packing):**

```
[lon_sign(1)][lat_sign(1)][extended(1)][lon_delta(bits)][lat_delta(bits)]
```

Where:
- `lon_sign` = 0 (fixed sign, positive delta)
- `lat_sign` = 0 (fixed sign, positive delta)
- `extended` = 0 (consumed by `stream.init()` but not used for raster)
- `lon_delta` = tile width in level-shifted map units
- `lat_delta` = tile height in level-shifted map units

**Delta computation:**
1. Header delta positions P0 at tile bottom-left: `lon_delta = (tile_left - subdiv_center) >> shift`, `lat_delta = (tile_bottom - subdiv_center) >> shift`
2. Bitstream encodes the extent from bottom-left to top-right: `width_ls = (tile_right - tile_left + mask) >> shift + 1`, `height_ls = (tile_top - tile_bottom + mask) >> shift + 1`
3. GPXSee recovers two points: P0 at `center + (header_delta << shift)` and P1 at `P0 + (bitstream_delta << shift)`
4. `boundingRect` = [P0, P1] covering the full tile extent

**baseSize calculation:** For a given max delta value, compute the minimum `baseSize` that can represent it. The required bits per delta = `bitSize(baseSize)`, and the total bitstream must fit in the 56 available bits (7 data bytes × 8 bits) after consuming sign+extended bits (3 bits). With a single delta pair: `3 + 2 × bitSize ≤ 56`, allowing baseSize up to 23.

**Packing order:** Bits are packed LSB-first into bytes (GPXSee's `BitStream1` reads from bit 0 of each byte). The first bit written goes into bit 0 of byte 1.

**Why this matters:** The `boundingRect` derived from the decoded delta pair is used by GPXSee's `copyPolys()` for tile filtering. If the bitstream is incorrectly encoded (wrong bitSize, missing extended bit, or wrong packing order), the boundingRect will be wrong, causing tiles to be incorrectly excluded — appearing as white grid lines at subdivision boundaries.

**Reference implementations:** Some reference files use 3 delta pairs tracing the tile outline (+w,0), (0,+h), (-w,0) with different sign modes per axis. IOM uses 0 delta pairs (single-point boundingRect). Both produce valid files. Our implementation uses 1 pair (+w, +h) for full tile coverage with the simplest encoding.

**GPXSee parsing flow:**

```
extPolyObjects() reads compound record:
  1. type(1) + subtype(1) → decode to 0x10613 → isRaster = true
  2. lon_delta(2) + lat_delta(2) → compute boundingRect point
  3. bitstream_len(VUInt32) + bitstream(8 bytes)
  4. label_ptr(uint24, if subtype & 0x20)
  5. class_flags(1) → readClassFields() → readRasterInfo()
  6. raster_size_enc(VUInt32) + image_id(2) + bounds(16) + jpeg_size(4)

copyPolys() filters: rect.intersects(boundingRect)
  → boundingRect covers full tile [bottom-left, top-right]
  → tiles with boundingRect outside view rect are excluded

drawPolygons() renders: uses poly.raster.rect()
  → absolute 32-bit bounds from readRasterInfo
```

#### 4.5.3 RGN5 — Metadata Section

RGN5 is a smaller metadata section observed in IOM.img but not present in single-map references.

| File               | RGN5 Size | Content                                          |
| ------------------ | --------- | ------------------------------------------------ |
| IOM subfile 355951 | 112 bytes | Starts with `DF 14 06 02 20 0B`, purpose unclear |
| Single-map reference     | 0 bytes   | Not present (size=0)                             |

The RGN5 section may contain rendering hints or extended metadata for the raster layer. For writer implementation, it can safely be omitted (size=0), as reference files validate correctly without it.

#### 4.5.4 RGN2 Per-Subdivision Segment Boundaries

RGN2 data is not a flat byte stream — it is logically divided into per-subdivision segments whose boundaries are defined by the **TRE7 offset table**. This is how Garmin devices and GPXSee locate individual subdivision data within RGN2.

**Segment boundary semantics:**

TRE7 entries (one per subdivision) contain offsets into the RGN2 section. Adjacent entries form start/end pairs:

```
Subdivision 0:  RGN2 offset[0]  →  RGN2 offset[1]
Subdivision 1:  RGN2 offset[1]  →  RGN2 offset[2]
Subdivision 2:  RGN2 offset[2]  →  RGN2 offset[3]
...
Subdivision N:  RGN2 offset[N]  →  RGN2 offset[N+1]  (sentinel)
```

The sentinel entry (all zeros) at the end of TRE7 provides the end boundary for the last real subdivision. Each subdivision's RGN2 data starts at its TRE7 offset and ends at the next entry's offset.

**Extended offsets in RGN sub-header:** The RGN2 base position (at RGN offset 0x1D) is added to the TRE7 offsets to compute the absolute GMP-relative position. GPXSee reads these via:

1. `subdivInit()` — reads TRE7 entries and stores `extPolygonsOffset` / `extPolygonsEnd` per subdivision
2. `segments()` — uses the subdivision's polygon offset and end to define a byte range within the RGN2 section
3. `extPolyObjects()` — parses the polyline preambles and E0 records within that byte range

**TRE7 `_flags` field (at TRE offset 0x86):**

The TRE sub-header contains a 4-byte flags field at offset 0x86 that determines how TRE7 entries are parsed:

| Flag bit | Meaning when set                                 |
| -------- | ------------------------------------------------ |
| 0        | Polygons present — read uint32 offset for polygons |
| 1        | Lines present — read uint32 offset for lines     |
| 2        | Points present — read uint32 offset for points   |

Some reference files have `_flags = 0x00000481` (bits 0 and 2 set). Bit 0 = polygons present as uint32, bit 2 = points present as uint32. IOM and our output use `_flags = 0x00000001` (only bit 0 set = polygons only). GPXSee's `readExtEntry()` reads entries conditionally based on which bits are set:

```cpp
if (_flags & 1) { readUInt32(hdl, polygons); rb += 4; }  // polygons offset
if (_flags & 2) { readUInt32(hdl, lines);    rb += 4; }  // lines offset
if (_flags & 4) { readUInt32(hdl, points);   rb += 4; }  // points offset
```

For extended-format files (rec_size=5, flags=0x481), each TRE7 entry is: `[uint32 rgn2_offset][uint8 flag]`. The flag byte is 0x01 for empty/overview subdivisions and 0x00 for data subdivisions. For IOM and our output (rec_size=4, flags=0x01), each entry is just `[uint32 rgn2_offset]` with no flag byte, plus a sentinel entry at the end containing the total RGN2 data extent.

**Complete RGN2 raster parsing flow (as implemented by GPXSee):**

```
TRE header → read _flags at TRE+0x86
           → read TRE7 section descriptor at TRE+0x7C
           → iterate TRE7 entries using readExtEntry()
           → store extPolygonsOffset/End per subdivision

RGN header → read _polygons section at RGN+0x1D (this IS RGN2)

Per subdivision:
  segment_start = _polygons.offset + extPolygonsOffset
  segment_end   = _polygons.offset + extPolygonsEnd
  parse extPolyObjects() within [segment_start, segment_end)
    → read type byte (0x06) + subtype (0xB3)
    → decode: type = 0x10000 | (0x06 << 8) | (0xB3 & 0x1F) = 0x10613
    → isRaster(0x10613) = true
    → compute boundingRect: single point at subdiv_center + (delta << shift)
    → readClassFields() + readRasterInfo()
    → read image_id (variable size from LBL) + bounds (4×uint32)
    → fetch JPEG from LBL29 via LBL28 index
```

**BoundingRect filtering (critical for tile display):**

GPXSee uses a two-stage filtering process for raster tiles:
1. **R-tree query:** Find subdivisions whose bounds (from TRE2 width/height) overlap the view rect
2. **copyPolys() filter:** Check if each tile's boundingRect intersects the view rect

The boundingRect is computed by GPXSee as a rectangle [P0, P1]: P0 is at `subdiv_center + (lon_delta << shift), subdiv_center + (lat_delta << shift)` from the header deltas, and P1 extends from P0 by the bitstream deltas (+width, +height). The absolute 32-bit tile bounds (from readRasterInfo) are used only for rendering, NOT for filtering.

If the boundingRect point (quantized by the shift) falls outside the view, the tile is excluded even though the actual raster image would be visible. This is why level_number must be high enough for the quantization step to be smaller than tile size.

**Implication for the writer:** The RGN2 data must be laid out so that each subdivision's records occupy a contiguous byte range, and the TRE7 offsets must correctly delimit these ranges. If TRE7 offsets are wrong or overlapping, the device will parse garbage data and fail to display tiles.

### 4.6 Complete GMP Data Layout

**Updated Structure (with LBL28/LBL29 and Type E0 records):**

```
Offset from GMP start  | Section            | Size
-----------------------|--------------------|----------------------------------
0x000                  | GMP Container Hdr  | 53 bytes
+53                    | Copyright strings  | Variable, null-terminated
+copyright             | TRE sub-header     | 273 bytes
+273                   | Map info strings   | Variable ("Raster Map\0" + copyright)
+map_info              | RGN sub-header     | 125 bytes
+125                   | LBL sub-header     | 596 bytes (includes LBL28/LBL29 descriptors)
+596                   | NET sub-header     | 100 bytes
+100                   | TRE data sections  | 6B copyright + subdiv + map_levels
+tre_data              | RGN data section   | N × 42 bytes (compound raster records)
+rgn_data              | LBL labels         | N × ~6 bytes (tile filenames "0.jpg\0"...)
+lbl_labels            | LBL28 section      | N × 4 bytes (image index offsets)
+lbl28                 | LBL29 section      | Sum of JPEG sizes (image storage)
```

**Reference single-map file (32,443 tiles):**

```
Offset from GMP start  | Section            | Size (actual)
-----------------------|--------------------|----------------------------------
0x000                  | GMP Container Hdr  | 53 bytes
0x035                  | Copyright strings  | ~180 bytes
0x0E8                  | TRE sub-header     | 273 bytes
0x1F8                  | Map info strings   | ~55 bytes
0x22F                  | RGN sub-header     | 125 bytes
0x2F6                  | LBL sub-header     | 596 bytes
0x54A                  | NET sub-header     | 100 bytes
~0x5AD                 | TRE data sections  | ~9KB
~0x2B00                | RGN data (Type E0) | ~1,582 bytes (inferred)
~0x3140                | LBL labels         | ~389KB (32K filenames)
~0xA8C00               | LBL28 (img index)  | ~126KB (32,443 × 4)
~0xC8000               | LBL29 (img storage)| ~1.4GB (JPEG tiles)
```
