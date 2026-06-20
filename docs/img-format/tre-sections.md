# TRE Header Layout & Sections

This page covers the TRE sub-header layout, map levels (TRE1), subdivisions (TRE2), raster layer offsets (TRE7), object type parameters (TRE8), draw order, and attribution. The TRE section defines the spatial index that organizes tile data stored in [Tile Storage](tile-storage.md).

## 5. TRE Header Layout and Section Offsets

### 5.1 TRE Header Structure (Raster Maps, 273 bytes)

The TRE sub-header in raster maps uses an extended 273-byte format, significantly larger than vector maps (116-188 bytes). The layout below was verified against the QMapShack wiki analysis by Alex Whiter and confirmed with IOM.img and other reference files.

**Common sub-header prefix (21 bytes):**

| Offset | Size | Field         | Value              |
| ------ | ---- | ------------- | ------------------ |
| 0x00   | 2    | Header length | 273 (0x0111)       |
| 0x02   | 10   | Signature     | `GARMIN TRE`       |
| 0x0C   | 1    | Version       | 1                  |
| 0x0D   | 1    | Lock          | 0                  |
| 0x0E   | 7    | Date          | 7-byte Garmin date |

**Bounds and section descriptors:**

| TRE Offset | Size | Field                | Description                                                                                                                                                                                                                                               |
| ---------- | ---- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0x15       | 3    | North bound          | 3-byte signed LE, map units                                                                                                                                                                                                                               |
| 0x18       | 3    | East bound           | 3-byte signed LE, map units                                                                                                                                                                                                                               |
| 0x1B       | 3    | South bound          | 3-byte signed LE, map units                                                                                                                                                                                                                               |
| 0x1E       | 3    | West bound           | 3-byte signed LE, map units                                                                                                                                                                                                                               |
| 0x21       | 8    | TRE1 (levels)        | pos(4) + size(4) — **GMP-relative** offset to level data                                                                                                                                                                                                  |
| 0x29       | 8    | TRE2 (subdivisions)  | pos(4) + size(4) — **GMP-relative** offset to subdivision data                                                                                                                                                                                            |
| 0x31       | 10   | TRE3 (copyright)     | pos(4) + size(4) + item_size(2) — **GMP-relative**                                                                                                                                                                                                        |
| 0x3B       | 4    | Padding              | Zeros                                                                                                                                                                                                                                                     |
| 0x3F       | 1    | Flags                | 0x00 or 0x01                                                                                                                                                                                                                                              |
| 0x40       | 2    | Display priority     | uint16 LE (20 for IOM and our output, 24 for some references)                                                                                                                                                                                                     |
| 0x42       | 8    | Parameters           | 8-byte parameter block. IOM: `10 01 08 24 00 01 00 00`. Single-map: `00 01 04 24 00 01 00 00`. Our output matches IOM. Byte 0x42 is a flag (0x00=single-map, 0x10=IOM). Byte 0x44 is likely bits-per-coord (4=single-map, 8=IOM). Byte 0x45=0x24 (36) is a tile size constant. |
| 0x4A       | 14   | TRE4 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**                                                                                                                                                                                                |
| 0x58       | 14   | TRE5 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**                                                                                                                                                                                                |
| 0x66       | 14   | TRE6 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**                                                                                                                                                                                                |
| 0x74       | 4    | Map ID               | uint32 LE                                                                                                                                                                                                                                                 |
| 0x78       | 4    | Padding              | Zeros                                                                                                                                                                                                                                                     |
| 0x7C       | 14   | TRE7 (raster layers) | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**                                                                                                                                                                                                |
| 0x8A       | 14   | TRE8 (object types)  | pos(4) + size(4) + rec_size(2) + pad(6) — **GMP-relative**                                                                                                                                                                                                |
| 0x9A       | 16   | Map ID hash          | 16-byte hash value                                                                                                                                                                                                                                        |
| 0xAA       | 4    | Padding              | Zeros                                                                                                                                                                                                                                                     |
| 0xAE       | 14   | TRE9 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**                                                                                                                                                                                                |
| 0xBC       | 14   | TRE10 descriptor     | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**                                                                                                                                                                                                |
| 0xCA       | 5    | Padding              | Zeros                                                                                                                                                                                                                                                     |
| 0xCF       | 4    | Matching number      | uint32 LE                                                                                                                                                                                                                                                 |
| 0xD3       | rest | Map name             | Null-terminated ASCII string                                                                                                                                                                                                                              |

**Critical: GMP-Relative Offsets.** All `pos` values in the section descriptors above (TRE1 through TRE10) are offsets relative to the **start of the GMP data**, NOT relative to the TRE block start. This is different from what the 2005 Mechalas spec documents for vector maps, where positions are TRE-relative. For raster maps in GMP containers, positions are always GMP-relative.

### 5.2 TRE1 — Map Levels (Zoom Level Table)

TRE1 contains the zoom level definitions as an array of 4-byte records:

```
byte 0:   zoom_code — determines at which map scale this level is active
byte 1:   level_number (bits) — coordinate precision (shift = 24 - level_number)
bytes 2-3: number_of_subdivisions (uint16 LE)
```

**Critical:** Byte 0 is zoom_code, byte 1 is level_number. This is the OPPOSITE of what some documentation claims. Confirmed via reference binary analysis and GPXSee source (`trefile.cpp:107-111`):

```cpp
_levels[i].level = *zoom;       // byte0 = zoom_code
_levels[i].bits = *(zoom + 1);  // byte1 = level_number
```

**Level number (bits) and coordinate precision:**

The `level_number` field determines coordinate precision for subdivision width/height and RGN2 delta encoding. The shift value is `max(0, 24 - level_number)`. Higher level_number = less shift = better precision.

**Important:** For raster maps, the `level_number` must be high enough that the quantization step (2^shift × 360 / 2^24 degrees) is smaller than the tile size. Otherwise, GPXSee's `copyPolys()` boundingRect filtering will drop tiles because the single-point boundingRect (derived from delta << shift) can land outside the view rect.

**Level number remapping:** The writer remaps level_numbers from the actual zoom levels to the range `24 - N + 1 .. 24` (where N = number of zoom levels), ensuring the most detailed level has level_number=24 (shift=0, no quantization error). This matches patterns observed in reference files: 5 levels → level_numbers 20-24.

Example with 12 zoom levels (zooms 6-17):
- Config zoom levels: 6, 7, 8, ..., 17
- Remapped level_numbers: 13, 14, 15, ..., 24
- Shift values: 11, 10, 9, ..., 0

**Zoom code computation:**

- Zoom code 0 = most detailed (highest zoom level)
- Higher zoom codes = less detailed (overview levels)
- Only the first (most zoomed-out) level gets the inherited flag (0x80) per mkgmap
- Pattern: level 0 gets `0x80 + (N-1)`, remaining levels count down from `N-2` to `0`

**Observed values from reference files:**

| File               | Zoom Codes (byte 0)          | Level Numbers (byte 1) | Subdivisions     |
| ------------------ | ---------------------------- | ---------------------- | ---------------- |
| Single-map reference | 0x84, 0x83, 0x02, 0x01, 0x00 | 20, 21, 22, 23, 24   | 1, 3, 138, 156, 300 |
| IOM subfile 355951 | 0x87, 0x06, 0x05, ..., 0x00  | 17, 18, 19, ..., 24  | 1 each (8 total) |

Single-map reference decoded level 0: code=0x84 (inherited, bit 7 set + value 4), bits=20. GPXSee skips inherited levels for data rendering.

### 5.3 TRE2 — Group/Subdivision Section

TRE2 contains subdivision records that define the spatial index for map data. The record size depends on the zoom level: **16 bytes for non-last levels** and **14 bytes for the last (most detailed) level**. After all subdivision records, there are **4 trailing bytes** containing the total RGN2 data extent as uint32 LE.

**16-byte record (non-last zoom levels):**

| Offset | Size | Field             | Description                                            |
| ------ | ---- | ----------------- | ------------------------------------------------------ |
| 0      | 4    | RGN offset/flags  | uint32 LE: bits 31-28 = has-polygons/lines/points flags, bits 27-0 = RGN2 offset |
| 4      | 3    | Longitude center  | 3-byte signed LE, map units (degrees × 2^24 / 360)     |
| 7      | 3    | Latitude center   | 3-byte signed LE, map units (degrees × 2^24 / 360)     |
| 10     | 2    | Width             | uint16 LE: bit 15 = end of chain marker, bits 14-0 = encoded width |
| 12     | 2    | Height            | uint16 LE                                              |
| 14     | 2    | Next level index  | uint16 LE, **1-based** global subdivision number of first child at next zoom level |

**14-byte record (last zoom level — no next_level field):**

| Offset | Size | Field             | Description                                            |
| ------ | ---- | ----------------- | ------------------------------------------------------ |
| 0      | 4    | RGN offset/flags  | uint32 LE: bits 31-28 = has-polygons/lines/points flags, bits 27-0 = RGN2 offset |
| 4      | 3    | Longitude center  | 3-byte signed LE, map units                            |
| 7      | 3    | Latitude center   | 3-byte signed LE, map units                            |
| 10     | 2    | Width             | uint16 LE (no end-of-chain bit in last level)          |
| 12     | 2    | Height            | uint16 LE                                              |

**Trailing bytes:** 4 bytes (uint32 LE) containing total RGN2 data size. This is the sentinel value used by GPXSee to determine the end of the last subdivision's RGN2 segment.

**Width/height encoding:**

Width and height are encoded with a precision-reducing shift. The shift is `max(0, 24 - level_number)` where level_number comes from TRE1 byte 1 for this zoom level. The encoding formula:

```
shift = max(0, 24 - level_number)
mask = (1 << shift) - 1

width  = ((2 * (center_mu - west_mu) + 1) // 2 + mask) >> shift
height = ((2 * (center_mu - south_mu) + 1) // 2 + mask) >> shift

For non-last levels: width |= 0x8000 only on the LAST subdivision in each
chain (bit 15 = end of chain marker per PDF spec)
```

Where `center_mu`, `west_mu`, `south_mu` are the subdivision bounds in 24-bit map units (degrees × 2^24 / 360). The `+1 // 2` rounding ensures the encoded value rounds up to cover the full subdivision area.

**Decoding (in GPXSee):** The subdivision bounds are reconstructed from center + encoded width/height:
- West = center_lon - (width << shift)
- South = center_lat - (height << shift)

**TRE2 section size:** Sum of all record sizes (16 × non-last subdivs + 14 × last-level subdivs + 4 trailing bytes).

**Example from a single-map reference:**

```
Level 0 (overview): 1 subdiv, w=1, h=1, shift=4 → ~0.09° × 0.07° actual size
Level 4 (detail): 300 subdivs, larger w/h values, shift=0 → precise bounds
Total: 560 subdivisions across 5 levels
```

**Note:** The 3-byte coordinate encoding in TRE2 uses the older map units format (degrees × 2^24 / 360), distinct from the 4-byte signed int32 coordinates (degrees × 2^31 / 180) used in RGN2 compound records.

### 5.4 TRE7 — Raster Layer Section

TRE7 defines an offset table that maps subdivisions to their raster layer data in RGN2. Each entry corresponds to one subdivision and provides the byte offset into RGN2 where that subdivision's data begins. **Adjacent entries form segment boundaries** — subdivision N's data spans from offset[N] to offset[N+1] (see [RGN2 Segment Boundaries](tile-storage.md#454-rgn2-per-subdivision-segment-boundaries) for details).

The section descriptor at TRE+0x7C includes a `rec_size` field that determines the record format.

**TRE7 descriptor header (at TRE+0x7C):**

```
pos(4):     GMP-relative offset to TRE7 data
size(4):    Total size of TRE7 data
rec_size(2): Size of each record in bytes
pad(4):     Zeros
```

**TRE7 `_flags` field (at TRE+0x86):**

A 4-byte flags value that determines how each TRE7 entry is parsed. The flags indicate which offset types are present in each entry:

| Flag bit | Meaning when set                                   |
| -------- | -------------------------------------------------- |
| 0        | Polygons — entry contains uint32 polygon offset    |
| 1        | Lines — entry contains uint32 line offset          |
| 2        | Points — entry contains uint32 point offset        |

For extended-format references (`_flags = 0x00000481`), bit 0 (polygons) and bit 2 (points) are set, meaning `readExtEntry()` reads 4+4=8 bytes per entry. For IOM and our output (`_flags = 0x00000001`), only bit 0 (polygons) is set, reading just 4 bytes per entry.

**Record format:**

| Variant              | rec_size | Format                              |
| -------------------- | -------- | ----------------------------------- |
| Simple (IOM/ours)    | 4        | uint32 LE offset into RGN2          |
| Extended (rec_size=5) | 5        | uint32 LE offset + 1 byte flag      |

**Extended TRE7 entry flag byte:**

| Value | Meaning                               |
| ----- | ------------------------------------- |
| 0x01  | Empty/overview subdivision (no tiles) |
| 0x00  | Data subdivision (contains tile data) |

**Segment boundary interpretation:**

TRE7 has N+1 entries for N subdivisions. The extra entry is a **sentinel** containing the total RGN2 data extent. The segment for subdivision `i` spans:

```
start = TRE7[i].offset
end   = TRE7[i+1].offset
```

The sentinel is required by GPXSee's subdivision parser: it reads `diff = totalSubdivs - (size / recSize) + 1` to determine which subdivisions get TRE7 entries, and then reads one extra entry after the last subdivision to call `setExtEnds()` on it. Without the sentinel, `diff` would be 1, causing the first subdivision to be skipped, and the last subdivision's segment would have no end boundary.

These offsets are relative to the RGN2 base position stored at RGN header offset 0x1D. To get absolute GMP positions: `abs_pos = RGN2_base + TRE7[i].offset`.

**IOM subfile 00355951 example (rec_size=4):**

```
Offset table: [0, 46, 92, 138, 184, 243, 361, 420]
→ 8 entries pointing to raster layer descriptions in RGN2 for 8 zoom levels
```

**Single-map example (rec_size=5):**

```
748 entries with uint32 offset + 1 byte flag each
→ Points to raster layer descriptions for 560 groups across 5 zoom levels
+1 sentinel entry (all zeros) marking end of data
```

### 5.5 TRE8 — Object Type Parameters

TRE8 defines object type parameters used by the renderer. The section contains 3-byte records.

**TRE8 record format (3 bytes each):**

```
byte 0: object type code
byte 1: parameter 1
byte 2: parameter 2
```

**Observed values:**

| File               | Entries                                    | Description                            |
| ------------------ | ------------------------------------------ | -------------------------------------- |
| IOM subfile 355951 | 2 entries: `06 06 13` and `0D 06 01`       | Polyline (0x06) + Polygon (0x0D) types |
| Single-map reference     | 1 entry: `13 06 06`                        | Raster tiles only                      |
| Our output         | 2 entries: `06 06 13` and `0D 06 01`       | Matches IOM reference                  |

**TRE8 entry decoding:**

Each 3-byte record declares an object type: `byte 0 = type code, byte 1 = parameter, byte 2 = subtype/version`.

- Type `0x06` (polyline): Used for raster tile polylines. Parameter `0x06`, subtype `0x13` (= 19, the raster subtype identifier).
- Type `0x0D` (polygon): Used for DATA_BOUNDS polygons. Parameter `0x06`, subtype `0x01`.

Both types must be declared for the Garmin device to correctly parse raster tile data.

### 5.6 Multi-Resolution Pyramid

Single-map reference files use 5 zoom levels (20-24), forming a pyramid where each level covers the same geographic area with different tile counts and resolutions. IOM uses 8 zoom levels (17-24).

For our implementation, we support configurable zoom levels with the zoom_code specified per level.

## 5.7 JNX Format Comparison

JNX (used by Garmin BirdsEye and the original format) is a simpler raster map format. Some raster IMG files were converted from JNX using Garmin tools. Understanding JNX's approach helps explain why IMG raster requires careful subdivision handling.

**JNX tile positioning:** Each tile stores its own 32-bit bounding rectangle (north, south, east, west as int32 LE) with NO quantization or subdivision scheme. Tiles are independently positioned at full precision, making gap-free display trivial.

**IMG tile positioning:** Tiles are positioned relative to subdivision centers via 16-bit deltas with shift = `24 - level_number`. This introduces quantization at the subdivision level. The bitstream produces a full-tile boundingRect via 1 delta pair (+width, +height) from P0 to P1, used by `copyPolys()` for tile filtering. Absolute 32-bit bounds handle rendering.

**Key differences:**

| Aspect | JNX | IMG (raster) |
|--------|-----|--------------|
| Tile bounds | Independent 32-bit rect per tile | Subdivision-relative 16-bit deltas |
| Quantization | None | Shift = `24 - level_number` |
| Spatial indexing | Per-tile bounds | TRE2 subdivision grid |
| Tile filtering | Direct bounds comparison | `copyPolys()` via boundingRect |
| Rendering | Direct | Absolute 32-bit from readRasterInfo |
| Gap risk | None (full precision) | Quantization at low level_numbers |

**Why this matters for white lines:** JNX has no subdivision concept, so tiles are always gap-free. IMG's subdivision-relative encoding can produce white lines when: (1) subdivision bounds don't cover all tile positions, (2) boundingRect quantization exceeds tile extent, or (3) subdivision centers are misaligned with tile positions. Our implementation avoids these by using tile-derived subdivision bounds and centers, and by remapping level_numbers to ensure coordinate precision exceeds tile size.


## 7. Draw Order and Attribution

### 7.1 Display Priority

The TRE sub-header contains a display priority field:

- **Value: 20** (matching IOM reference, optimal for raster basemaps)
- Determines rendering order when multiple maps overlap
- Higher values are drawn on top
- Some references use 24 (drawn above vector overlays), IOM uses 20 (drawn below)

### 7.2 Map Metadata

| Field       | Location              | Max Length  | Encoding  |
| ----------- | --------------------- | ----------- | --------- |
| Map name    | Header 0x49 + MPS     | 20/32 bytes | ASCII     |
| Description | GMP "Raster Map\0"    | Variable    | ASCII     |
| Copyright   | GMP copyright strings | Variable    | CP-1252   |
| Map ID      | FAT entry name        | 8 bytes     | Hex ASCII |

### 7.3 Map ID

- 8-character hexadecimal identifier (e.g., `09C102B0`)
- Used as the GMP subfile name in the FAT directory
- Unique per map file
