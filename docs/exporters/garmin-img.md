# Garmin Raster IMG Format Specification

This document describes the Garmin raster `.img` file format based on analysis of SwissTopo sample files using GMapTool (gmt), hex dump analysis, mkgmap source code, and the John Mechalas IMG format specification (2005).

**Status:** Verified against reference files. GMT validation passes. Implementation in `src/cartoload/exporters/garmin_img_writer.py`.

**Important:** The Garmin IMG format was originally designed for **vector maps**. The raster variant (used by SwissTopo and this project) reuses the same container structure (header, FAT, GMP subfile) but uses **different subdivision and RGN data formats** than the well-documented vector format. The vector format details (polyline/polygon encoding, point structures, label encoding) are documented for reference but are NOT used by raster maps.

**Primary reference:** `imgformat-1.0.pdf` (John Mechalas, 2005) — comprehensive vector IMG format specification. Raster-specific discoveries are marked as such.

## 1. File Header Structure

The IMG file begins with a 512-byte header containing metadata and file system information.

### 1.1 Header Field Reference

| Offset      | Size | Field              | Description                                                                                     |
| ----------- | ---- | ------------------ | ----------------------------------------------------------------------------------------------- |
| 0x00        | 1    | XOR byte           | Encryption key (0x00 = no encryption)                                                           |
| 0x01-0x07   | 7    | Reserved           | Zero padding                                                                                    |
| 0x08-0x09   | 2    | Map version        | Typically 0x0000                                                                                |
| 0x0A-0x0B   | 2    | Update month/year  | Update marker (0x0020 observed)                                                                 |
| 0x0E        | 1    | MapSource flag     | 0 = Garmin map                                                                                  |
| 0x0F        | 1    | Checksum           | Sum of all bytes 0x00-0x0E, then `(-sum) & 0xFF`. Note: MapSource does not validate this field. |
| 0x10        | 6    | Magic signature    | `DSKIMG` (ASCII)                                                                                |
| 0x16        | 1    | Unknown            | Always 0x00                                                                                     |
| 0x17        | 1    | Format version     | Always 0x02                                                                                     |
| 0x18-0x19   | 2    | Sectors per track  | 0x0020                                                                                          |
| 0x1A-0x1B   | 2    | Heads per cylinder | 0x0001                                                                                          |
| 0x39-0x3E   | 6    | Creation date      | `year_LE(2) + month(1) + day(1) + hour(1) + min(1) + sec(1)`                                    |
| 0x40        | 1    | FAT block number   | Physical block number of FAT start (8 = 0x1000)                                                 |
| 0x41-0x48   | 8    | Creator string     | `GARMIN\0\0` (null-padded to 8 bytes)                                                           |
| 0x49-0x5C   | 20   | Map description    | ASCII, space-padded (20 bytes)                                                                  |
| 0x5D-0x5E   | 2    | Heads (copy)       | 0x0001                                                                                          |
| 0x5F-0x60   | 2    | Sectors (copy)     | 0x0020                                                                                          |
| 0x61        | 1    | Block size exp E1  | 0x09 (base = 2^9 = 512)                                                                         |
| 0x62        | 1    | Block size exp E2  | 0x06 (block_size = 512 × 2^6 = 32768)                                                           |
| 0x63-0x64   | 2    | Total block count  | Total data blocks, or 0xFFFF if overflow                                                        |
| 0x1BE-0x1CD | 16   | Partition entry    | MBR-style partition table entry                                                                 |
| 0x1FE-0x1FF | 2    | Boot signature     | 0xAA55 (standard x86 boot sector signature)                                                     |

### 1.2 Creation Date Encoding

**Offset: 0x39-0x3E** — 6 bytes, little-endian (confirmed by Mechalas spec):

```
byte 0-1: year   (uint16 LE)
byte 2:   month  (0-11, NOT 1-12 as in some references)
byte 3:   day    (1-31)
byte 4:   hour   (0-23)
byte 5:   second (0-59)
```

Note: offset 0x3E stores seconds, not minutes. The header does not include minutes. The Mechalas spec confirms: year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1) at 0x39-0x3F but some references show only 6 bytes (0x39-0x3E).

### 1.3 Block Size Calculation

```
BLOCK_SIZE = 512 × 2^E2 = 512 × 2^6 = 32768 bytes
```

The FAT block size is always 512 bytes. The data block size is 32768 bytes.

### 1.4 Partition Table

At offset 0x1BE, a standard MBR partition table entry:

- 0x1BE: Boot indicator (0x00 = not bootable)
- 0x1BF-0x1C1: Start CHS
- 0x1C2: System type (0xFF = auto-detect)
- 0x1C3-0x1C5: End CHS
- 0x1C6-0x1C9: Relative sectors (LBA start, uint32 LE)
- 0x1CA-0x1CD: Total sectors (uint32 LE)

## 2. FAT (File Allocation Table) Structure

### 2.1 FAT Layout

GMT reports format: `fat: <start> - <directory> - <extent>`

- **FAT start offset:** 0x1000 (4096 bytes from file start)
- **Physical block number:** 8 (stored in header at 0x40)
- **FAT entry size:** 512 bytes each

### 2.2 FAT Entry Format (512 bytes)

| Offset | Size | Field        | Description                                                                                       |
| ------ | ---- | ------------ | ------------------------------------------------------------------------------------------------- |
| 0x00   | 1    | Flag         | 0x01=active, 0x00=terminator                                                                      |
| 0x01   | 8    | Subfile name | 8-char name, space-padded (e.g., "09C102B0")                                                      |
| 0x09   | 3    | Subfile type | ASCII type code (e.g., "GMP", "MPS")                                                              |
| 0x0C   | 4    | Subfile size | uint32 LE, only valid in part 0                                                                   |
| 0x10   | 1    | Flag2        | 0x00=normal, 0x03=special directory entry                                                         |
| 0x11   | 1    | Part number  | 0 for first part, increments for multi-part (uint16 per spec, but high byte always 0 in practice) |
| 0x12   | 14   | Reserved     | Zeros                                                                                             |
| 0x20   | 480  | Block table  | 240 × uint16 LE block numbers (0xFFFF = unused)                                                   |

### 2.3 Special Directory FAT Entry

The first FAT entry is a special directory entry that covers the blocks from offset 0 through the start of the data region:

- Name: 8 spaces
- Type: 3 spaces
- Flag2: 0x03 (special)
- Block table: sequential block numbers 0..N (header + FAT blocks)

### 2.4 Subfile FAT Entries

Each subfile gets one or more FAT entries:

- Name: For GMP subfiles, this is the map ID as 8-char uppercase hex (e.g., `09C102B0`). For MPS, it's `MAPSOURC`.
- Large subfiles span multiple FAT entries (part 0, 1, 2...) each holding up to 240 block pointers.
- Block pointers are physical block numbers (offset / BLOCK_SIZE), not FAT indices.

## 3. Subfile Organization

### 3.1 Subfile Types in Raster Maps

Raster IMG files contain exactly 2 subfiles:

1. **GMP (Garmin Map)** — Main container holding all raster data, tile index, zoom levels
2. **MPS (MAPSOURC)** — Map source metadata (98 bytes)

Subfile names in the FAT directory:

```
Sub-file         fat     length
 09C102B0 GMP   1200h   <GMP size>
 MAPSOURC MPS   xxxxx        98
```

The GMP subfile name is the map ID (8-char hex), NOT "GMP".

### 3.2 GMP Container Format

The GMP subfile is a **container** that embeds standard Garmin sub-file headers (TRE, RGN, LBL, NET). This is the same format used by vector maps, but adapted for raster tiles.

**GMP Container Layout:**

```
[GMP Container Header: 53 bytes]
[Copyright strings: null-terminated]
[TRE Sub-Header: 273 bytes]
[Map Info Strings: "Raster Map\0" + copyright\0"]
[RGN Sub-Header: 125 bytes]
[LBL Sub-Header: 596 bytes]
[NET Sub-Header: 100 bytes]
[TRE Data Sections: copyright, subdivisions, map_levels]
[RGN Data Section: subdivision records]
[LBL Labels: tile filenames as null-terminated strings]
[Tile Index Table: N × uint32 offsets]
[JPEG Tile Data: concatenated JFIF JPEGs]
```

### 3.3 GMP Container Header (53 bytes)

| Offset | Size | Field                | Value / Description                        |
| ------ | ---- | -------------------- | ------------------------------------------ |
| 0x00   | 1    | Header size          | 0x35 (53)                                  |
| 0x01   | 1    | Flag                 | 0x00                                       |
| 0x02   | 10   | Signature            | `GARMIN GMP`                               |
| 0x0C   | 2    | Version              | 1 (uint16 LE)                              |
| 0x0E   | 7    | Creation date        | 7-byte Garmin date                         |
| 0x15   | 4    | Section table offset | 0 (sections start at end of header)        |
| 0x19   | 28   | Section offsets      | 7 × uint32 LE: TRE, RGN, LBL, NET, 0, 0, 0 |

### 3.4 Common Sub-Header Format (21 bytes)

All sub-section headers (TRE, RGN, LBL, NET) share a common 21-byte prefix:

| Offset | Size | Field         | Description                                |
| ------ | ---- | ------------- | ------------------------------------------ |
| 0      | 2    | Header length | uint16 LE, total length of this sub-header |
| 2      | 10   | Type string   | `GARMIN TRE`, `GARMIN RGN`, etc.           |
| 12     | 1    | Version       | Always 1                                   |
| 13     | 1    | Lock          | 0 = unlocked                               |
| 14     | 7    | Date          | 7-byte Garmin date                         |

### 3.5 TRE Sub-Header (273 bytes)

After the 21-byte common header:

| Offset | Size | Field                 | Description                               |
| ------ | ---- | --------------------- | ----------------------------------------- |
| 21     | 3    | North bound           | 3-byte signed LE, map units               |
| 24     | 3    | East bound            | 3-byte signed LE, map units               |
| 27     | 3    | South bound           | 3-byte signed LE, map units               |
| 30     | 3    | West bound            | 3-byte signed LE, map units               |
| 33     | 4    | Map levels position   | uint32 LE, relative to TRE start          |
| 37     | 4    | Map levels size       | uint32 LE                                 |
| 41     | 4    | Subdivisions position | uint32 LE, relative to TRE start          |
| 45     | 4    | Subdivisions size     | uint32 LE                                 |
| 49     | 4    | Copyright position    | uint32 LE, relative to TRE start          |
| 53     | 4    | Copyright size        | uint32 LE                                 |
| 57     | 2    | Copyright item size   | uint16 LE (typically 3)                   |
| ...    | ...  | Remaining fields      | POI flags, display priority, section info |

**3-byte signed map units:** `degrees × 2^24 / 360`. For example, latitude 47.65°:

```
int(47.65 * 2^24 / 360) = 2,225,653 = 0x21E825 → bytes 25 E8 21
```

**Display priority:** 24 (standard for raster basemaps).

### 3.6 RGN Sub-Header (125 bytes)

After the 21-byte common header:

| Offset | Size | Field             | Description                      |
| ------ | ---- | ----------------- | -------------------------------- |
| 21     | 4    | Data position     | uint32 LE, relative to RGN start |
| 25     | 4    | Data size         | uint32 LE                        |
| 29+    | ...  | Ext type sections | Zeros for raster maps            |

### 3.7 LBL Sub-Header (596 bytes)

After the 21-byte common header:

| Offset | Size | Field             | Description                        |
| ------ | ---- | ----------------- | ---------------------------------- |
| 21     | 4    | Labels position   | uint32 LE, relative to LBL start   |
| 25     | 4    | Labels size       | uint32 LE                          |
| 29     | 1    | Offset multiplier | 1                                  |
| 30     | 1    | Encoding          | 6 (CP1252)                         |
| 31+    | ...  | Remaining fields  | Places section, codepage, sort IDs |

**Labels content:** Tile filenames as null-terminated strings (e.g., `"0.jpg"`, `"1.jpg"`, ...).

### 3.8 NET Sub-Header (100 bytes)

Minimal stub for raster maps. Contains the 21-byte common header, with all NET-specific fields set to zero (no network/routing data needed for raster maps).

### 3.9 MPS Subfile (98 bytes)

| Offset | Size | Field      | Description           |
| ------ | ---- | ---------- | --------------------- |
| 0x00   | 2    | Signature  | `MP`                  |
| 0x02   | 32   | Map name   | Null-terminated ASCII |
| 0x22   | 2    | Product ID | uint16 LE             |
| 0x24   | 2    | Family ID  | uint16 LE             |
| 0x26   | 4    | Map ID     | uint32 LE             |

## 4. Tile Storage Format

### 4.1 JPEG Tile Data

**Tiles are stored as standard JFIF JPEG files**, concatenated sequentially at the end of the GMP subfile. Each tile begins with the JPEG start-of-image marker `FFD8FFE0` followed by `JFIF`.

Verified from SwissTopo reference files:

- Tile sizes range from ~10KB to ~65KB each
- All 32,254 tiles in SwissTopo_West verified to have valid JPEG start markers

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

**LBL sub-header fields:**

- Position (offset 37-40): uint32 LE, relative to LBL sub-header start
- Size (offset 41-44): uint32 LE

### 4.4 LBL29 (Image Storage)

The LBL29 section contains concatenated JPEG files with no padding or delimiters between files. JPEGs are stored in the same order as tiles are traversed: sequentially by zoom level, then sequentially within each zoom level.

**Format:**

```
LBL29: [JPEG_0][JPEG_1][JPEG_2]...[JPEG_N-1]
  where each JPEG is a complete JFIF JPEG file
  starting with FFD8FFE0 marker followed by "JFIF"
```

**LBL29 section size:** Sum of all JPEG file sizes

**LBL sub-header fields:**

- Position (offset 45-48): uint32 LE, relative to LBL sub-header start
- Size (offset 49-52): uint32 LE

**Relationship:** LBL28[i] contains the byte offset within LBL29 where JPEG tile i begins. Reading LBL29 from offset LBL28[i] yields the i-th JPEG tile.

### 4.5 RGN Data Section (Type E0 Records)

The RGN data section contains Type E0 records for raster tiles. Each Type E0 record describes one raster tile's geographic bounds, JPEG size, and reference to the image data in LBL29 via LBL28 index.

**Type E0 Record Format:**

```
Offset | Size | Field           | Description
-------|------|-----------------|------------------------------------------
0      | 1    | Marker          | 0xE0 (Type E0 marker byte)
1      | 1    | bits_field      | 0x2B for <256 tiles, 0x25 for ≥256 tiles
2      | 4    | lat_min         | int32 LE, Garmin map units (degrees × 2^31 / 180)
6      | 4    | lon_min         | int32 LE, Garmin map units
10     | 4    | lat_max         | int32 LE, Garmin map units
14     | 4    | lon_max         | int32 LE, Garmin map units
18     | 4    | block_size      | uint32 LE, JPEG file size in bytes
22     | 1-2  | image_index     | uint8 (if bits_field=0x2B) or uint16 LE (if bits_field=0x25)
```

**Total record size:** 23 bytes (8-bit index) or 24 bytes (16-bit index)

**bits_field encoding:**

- `0x2B`: Indicates 8-bit image index (1 byte follows), used when total tiles < 256
- `0x25`: Indicates 16-bit image index (2 bytes follow), used when total tiles ≥ 256

**image_index:** Zero-based index into the LBL28 offset array. LBL28[image_index] points to the JPEG for this tile in LBL29.

**Coordinate encoding:** Uses 32-bit signed Garmin map units (degrees × 2^31 / 180), distinct from the 3-byte coords used in TRE header bounds.

**RGN data section size:** N × record_size, where N = total tile count and record_size = 23 or 24 bytes depending on bits_field.

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
+tre_data              | RGN data section   | N × (23 or 24) bytes (Type E0 records)
+rgn_data              | LBL labels         | N × ~6 bytes (tile filenames "0.jpg\0"...)
+lbl_labels            | LBL28 section      | N × 4 bytes (image index offsets)
+lbl28                 | LBL29 section      | Sum of JPEG sizes (image storage)
```

**Reference SwissTopo_West (32,443 tiles):**

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

## 5. Zoom Level Encoding

### 5.1 Zoom Level Table Structure

From GMT output for SwissTopo reference files:

```
levels [20,21,22,23,24], zoom [84,83,2,1,0]
```

Each zoom level record is 4 bytes stored in the TRE map_levels section:

```
byte 0: level_number (e.g., 20, 21, 22, 23, 24)
byte 1: zoom_code    (e.g., 84, 83, 2, 1, 0)
bytes 2-3: number_of_subdivisions (uint16 LE)
```

### 5.2 Zoom Code Interpretation

The zoom codes correspond to Garmin's internal scale system:

- Zoom code 0 = most detailed (highest zoom level)
- Zoom code 84 = least detailed (overview)
- The pattern appears to be: higher level numbers → lower zoom codes → more detail

### 5.3 Multi-Resolution Pyramid

SwissTopo files use 5 zoom levels (20-24), forming a pyramid where each level covers the same geographic area with different tile counts and resolutions.

For our implementation, we support configurable zoom levels with the zoom_code specified per level.

## 6. Vector vs Raster Format Differences

This section documents the vector IMG format (from Mechalas spec and mkgmap) for reference. Raster maps use the same container structure but different internal formats.

### 6.1 Vector Map Level Definition (NOT used by raster)

In vector maps, each map level record is 4 bytes:

```
byte 0: zoom/inherited flags
  bits 0-3: zoom level (0-15, 0 = most detailed)
  bits 3-6: unknown (always 0?)
  bit 7: inherited flag
byte 1: bits_per_coord (max 24, resolution = 2^(24-bits))
bytes 2-3: number of subdivisions (uint16 LE)
```

More bits per coordinate = more detail. 24 bits = full resolution (~7.8 feet), 23 bits = half, etc.

### 6.2 Vector Subdivision Format (NOT used by raster)

Vector subdivisions are 14 bytes (lowest level) or 16 bytes (other levels):

| Offset | Size | Field                  | Description                                                         |
| ------ | ---- | ---------------------- | ------------------------------------------------------------------- |
| 0      | 3    | RGN data pointer       | Offset in RGN subfile                                               |
| 3      | 1    | Object types           | Bit flags: 0x10=points, 0x20=indexed, 0x40=polylines, 0x80=polygons |
| 4      | 3    | Longitude center       | 3-byte signed map units                                             |
| 7      | 3    | Latitude center        | 3-byte signed map units                                             |
| 10     | 2    | Width                  | Bits 0-14: width in map units, Bit 15: terminating flag             |
| 12     | 2    | Height                 | In map units                                                        |
| 14     | 2    | Next level subdivision | 1-based index (NOT present in lowest level)                         |

Actual area size = (width*2 + 1) × (height*2 + 1) map units around center.

### 6.3 Raster Subdivision Format (our implementation)

**Raster maps use a different subdivision format** than vector maps. This was confirmed by analyzing SwissTopo reference files:

- The first subdivision in SwissTopo_West has `obj_types=0x0F` (bits 0-3 set), not the vector format's 0x10/0x20/0x40/0x80 bit flags.
- This indicates raster-specific subdivision records that reference bitmap tiles rather than vector elements.

Our current implementation writes simplified subdivision records (8 bytes per zoom level, zero-filled). This passes GMT validation but may need refinement for actual Garmin device rendering.

### 6.4 Vector RGN Data Segment Layout (NOT used by raster)

Each RGN data segment corresponds to one subdivision and contains:

1. Pointers to element groups (2 bytes each, one fewer than element types)
2. Element groups in order: points, indexed points, polylines, polygons
3. No pointer for the first element group (starts right after pointers)

### 6.5 LBL Label Encoding (vector only)

Vector maps use compact bit-stream label encoding:

- **6-bit encoding** (value 6 at LBL 0x1E): US maps, 6 bits per character
- **8-bit encoding** (value 9): International maps
- **10-bit encoding** (value 10): Extended character sets

Characters are packed MSB-first. Special codes exist for symbols (0x1B prefix), lowercase (0x1C prefix), and highway shields.

**Raster maps use value 6 (CP1252 encoding) but store plain ASCII tile filenames — no bit-packing needed.**

### 6.6 TRE Header Variants (vector)

Known TRE header lengths for vector maps: 116, 120, 154, 188 bytes.
Raster maps use 273-byte TRE headers (seen in SwissTopo reference files) — a newer extended format not documented in the 2005 Mechalas spec.

LBL header variants (vector): 170, 196, 208, 236 bytes.
Raster maps use 596-byte LBL headers.

## 7. Draw Order and Attribution

### 7.1 Display Priority

The TRE sub-header contains a display priority field:

- **Value: 24** (based on reference SwissTopo files)
- Determines rendering order when multiple maps overlap
- Higher values are drawn on top

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

## 8. Size Constraints and Limits

### 8.1 File Size Limits

| Constraint           | Value                | Notes                 |
| -------------------- | -------------------- | --------------------- |
| Maximum file size    | 4 GB (4,294,967,296) | Limited by 32-bit FAT |
| Data block size      | 32,768 bytes         | 512 × 2^6             |
| FAT entry size       | 512 bytes            |                       |
| Blocks per FAT entry | 240                  | After 32-byte header  |
| Max tile size        | 3,670,016 bytes      | 3.5 MB compressed     |

### 8.2 FAT Block Capacity

Each FAT entry holds 240 block pointers (240 × 32KB = 7.5MB per FAT entry). For large files:

- 1.4 GB GMP ≈ 45,623 data blocks ≈ 191 FAT entries
- SwissTopo_West FAT extent: 0x20000 (131,072 bytes = 256 FAT entries)

### 8.3 Map Splitting

When approaching 4 GB, split into multiple `.img` files by geographic region (e.g., SwissTopo splits into West/East). Each file is self-contained with no cross-file references.

## 9. Garmin Date Format

### 9.1 6-byte Header Date (at offset 0x39)

```
bytes 0-1: year   (uint16 LE)
byte 2:    month  (1-12)
byte 3:    day    (1-31)
byte 4:    hour   (0-23)
byte 5:    second (0-59)
```

### 9.2 7-byte Sub-Header Date (in common headers)

Same as 6-byte but with an additional byte for day-of-week (or padding):

```
bytes 0-1: year   (uint16 LE)
byte 2:    month  (1-12)
byte 3:    day    (1-31)
byte 4:    hour   (0-23)
byte 5:    minute (0-59)
byte 6:    second (0-59)
byte 7:    dow    (0, padding)
```

## 10. Reference File Analysis

### 10.1 SwissTopo_West.img

| Property    | Value                                |
| ----------- | ------------------------------------ |
| File size   | 1,495,072,768 bytes (1.39 GB)        |
| Header date | 16.04.2022 15:03:56                  |
| Map name    | Svizzera_W Raster Map                |
| Map ID      | 09C102B0                             |
| FAT         | 1000h - 1200h - 20000h, block 32768  |
| Zoom levels | [20,21,22,23,24], zoom [84,83,2,1,0] |
| Bitmaps     | 32,443 tiles, ~1.49 GB               |
| Subfiles    | 2 (GMP + MPS)                        |

### 10.2 SwissTopo_Est.img

| Property    | Value                               |
| ----------- | ----------------------------------- |
| File size   | 1,421,049,856 bytes (1.32 GB)       |
| Header date | 20.04.2022 17:10:22                 |
| Map name    | Svizzera_E Raster Map               |
| Map ID      | 013202B4                            |
| FAT         | 1000h - 1200h - 18000h, block 32768 |
| Bitmaps     | 28,737 tiles, ~1.42 GB              |

### 10.3 Our Implementation Output

| Property           | Value                                    |
| ------------------ | ---------------------------------------- |
| GMT validation     | Exit code 0 (pass)                       |
| Single-tile IMG    | 98,304 bytes, GMT reads correctly        |
| Multi-tile IMG     | 98,304 bytes (3 zooms, 21 tiles), passes |
| GMP subfile name   | Map ID as hex (e.g., "09C102B0")         |
| Character encoding | CP-1252                                  |

## 11. Implementation Files

| File                                           | Purpose                                           |
| ---------------------------------------------- | ------------------------------------------------- |
| `src/cartoload/exporters/garmin_img_model.py`  | Data model (dataclasses for IMG structure)        |
| `src/cartoload/exporters/garmin_img_writer.py` | Binary writer (header, FAT, GMP container, tiles) |
| `src/cartoload/exporters/garmin_img.py`        | Exporter class (pipeline integration)             |
| `tests/test_exporter_garmin_img.py`            | Test suite (63 tests, all passing)                |

### Key Writer Classes

- **`IMGHeaderWriter`** — Writes 512-byte file header with checksum
- **`FATWriter`** — Manages FAT entries (special directory + subfile entries)
- **`GMPWriter`** — Writes GMP container with all sub-headers and tile data
- **`MPSWriter`** — Writes 98-byte MPS metadata subfile
- **`TileEncoder`** — JPEG-encodes NumPy tile arrays
- **`TileExtractor`** — Extracts tiles from GeoTIFF via gdal_translate
- **`LayoutComputer`** — First-pass size computation and offset assignment

---

**Analysis based on:**

- SwissTopo_West: my_SwissTopo_West.img (1,495,072,768 bytes / 1.4 GB)
- SwissTopo_Est: my_SwissTopo_Est.img (1,421,049,856 bytes / 1.4 GB)
- GMapTool (gmt) v0.8.220.853b output
- mkgmap source code (`uk.me.parabola.imgfmt` package)
- Hexadecimal dumps of headers and GMP container sections
- **Device tested:** Garmin Fenix 6 (confirmed working with reference files)

**Last updated:** 2026-04-22
