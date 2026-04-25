# Garmin Raster IMG Format Specification

This document describes the Garmin raster `.img` file format based on analysis of SwissTopo sample files using GMapTool (gmt), hex dump analysis, mkgmap source code, the John Mechalas IMG format specification (2005), and the Willink/Pinns "Exploring Garmin's IMG Format" (2015).

**Status:** Verified against reference files. GMT validation passes. Implementation in `src/cartoload/exporters/garmin_img_writer.py`.

**Important:** The Garmin IMG format was originally designed for **vector maps**. The raster variant (used by SwissTopo and this project) reuses the same container structure (header, FAT, GMP subfile) but uses **different subdivision and RGN data formats** than the well-documented vector format. The vector format details (polyline/polygon encoding, point structures, label encoding) are documented for reference but are NOT used by raster maps.

**Primary references:**

- `imgformat-1.0.pdf` (John Mechalas, 2005) — comprehensive vector IMG format specification
- `expl_img2015.pdf` (N. Willink, 2015) — "Exploring Garmin's IMG Format: TRE, RGN, LBL, NET, NOD & DEM"

Raster-specific discoveries are marked as such.

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

Raster IMG files can contain either 2 subfiles (single-map) or many subfiles (multi-map):

**Single-map raster (SwissTopo format):**

| Subfile | Type | Count | Description                         |
| ------- | ---- | ----- | ----------------------------------- |
| GMP     | Map  | 1     | Main container with all raster data |
| MPS     | Meta | 1     | Map source metadata (98 bytes)      |

**Multi-map raster (IOM format):**

| Subfile | Type | Count | Description                           |
| ------- | ---- | ----- | ------------------------------------- |
| GMP     | Map  | 51    | Each subfile covers a geographic tile |
| MPS     | Meta | 1     | Map source metadata (3936 bytes)      |

Subfile names in the FAT directory:

- GMP subfiles: map ID as 8-char uppercase hex (e.g., `00355951`)
- MPS subfile: `MAPSOURC`

### 3.1.1 Multi-Map Organization

Multi-map IMG files (like IOM.img) split the coverage area into multiple GMP subfiles, each representing one geographic tile. The MPS subfile contains reference records for all maps.

**IOM.img example:**

```
FAT entries: 51 GMP subfiles + 1 MPS subfile
Each GMP subfile: ~660KB with 8 zoom levels, covering ~7×5 km area
MPS subfile: 3936 bytes with L-records for all 51 maps
```

**MPS multi-map reference format:**

- Contains L-records listing all maps with Product ID (PID) and Family ID (FID)
- IOM.img: PID=1, FID=2150 for all 51 maps

**Multi-map vs single-map parameter differences:**

| Parameter        | IOM (multi-map) | SwissTopo (single-map) |
| ---------------- | --------------- | ---------------------- |
| Display priority | 20              | 24                     |
| Parameters       | 1 8 36 1        | 1 4 36 1               |
| TRE7 rec_size    | 4 (simple)      | 5 (extended)           |
| TRE8 entries     | 2               | 1                      |
| NET section      | Not present     | Present                |
| RGN5             | 112 bytes       | 0 bytes                |

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

After the 21-byte common header, the TRE sub-header uses the following layout. **All position values are GMP-relative offsets** (see Section 5.1 for complete field reference):

| Offset | Size | Field                 | Description                                   |
| ------ | ---- | --------------------- | --------------------------------------------- |
| 21     | 3    | North bound           | 3-byte signed LE, map units                   |
| 24     | 3    | East bound            | 3-byte signed LE, map units                   |
| 27     | 3    | South bound           | 3-byte signed LE, map units                   |
| 30     | 3    | West bound            | 3-byte signed LE, map units                   |
| 33     | 4    | Map levels position   | uint32 LE, **GMP-relative** (see Section 5.2) |
| 37     | 4    | Map levels size       | uint32 LE                                     |
| 41     | 4    | Subdivisions position | uint32 LE, **GMP-relative** (see Section 5.3) |
| 45     | 4    | Subdivisions size     | uint32 LE                                     |
| 49     | 4    | Copyright position    | uint32 LE, **GMP-relative**                   |
| 53     | 4    | Copyright size        | uint32 LE                                     |
| 57     | 2    | Copyright item size   | uint16 LE (typically 3)                       |
| ...    | ...  | Remaining fields      | See Section 5.1 for complete TRE header map   |

**3-byte signed map units:** `degrees × 2^24 / 360`. For example, latitude 47.65°:

```
int(47.65 * 2^24 / 360) = 2,225,653 = 0x21E825 → bytes 25 E8 21
```

**Display priority:** 24 (standard for raster basemaps).

### 3.6 RGN Sub-Header (125 bytes)

After the 21-byte common header, the RGN sub-header uses the following layout (positions are **GMP-relative** offsets):

| RGN Offset | Size | Field              | Description                      |
| ---------- | ---- | ------------------ | -------------------------------- |
| 0x15       | 8    | RGN1 position/size | pos(4) + size(4) — standard data |
| 0x1D       | 8    | RGN2 position/size | pos(4) + size(4) — raster layers |
| 0x25       | 20   | Flags/padding      | Zeros                            |
| 0x39       | 8    | RGN3 position/size | pos(4) + size(4)                 |
| 0x41       | 20   | Flags/padding      | Zeros                            |
| 0x55       | 8    | RGN4 position/size | pos(4) + size(4)                 |
| 0x5D       | 20   | Flags/padding      | Zeros                            |
| 0x71       | 8    | RGN5 position/size | pos(4) + size(4)                 |
| 0x79+      |      | RGNEXT header      | Extended data                    |

**Note:** All `pos` values in the RGN sub-header are GMP-relative offsets, matching the TRE header convention.

### 3.7 LBL Sub-Header (596 bytes)

After the 21-byte common header:

| Offset | Size | Field             | Description                                |
| ------ | ---- | ----------------- | ------------------------------------------ |
| 21     | 4    | Labels position   | uint32 LE, relative to LBL start           |
| 25     | 4    | Labels size       | uint32 LE                                  |
| 29     | 1    | Offset multiplier | 1                                          |
| 30     | 1    | Encoding          | 9 (8-bit, 1 byte per character)            |
| 31+    | ...  | Remaining fields  | Places section, codepage, sort IDs         |
| 0xAA   | 2    | Codepage          | uint16 LE, 1252 (Windows Western European) |

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

#### 4.5.1 RGN2 — Raster Layer Descriptions

RGN2 contains compound records that describe the raster tiles for each subdivision. The data is a sequence of mixed record types:

**Record types within RGN2:**

| Marker | Type                  | Description                                            |
| ------ | --------------------- | ------------------------------------------------------ |
| `0x0D` | POI-like record       | Variable-length, starts with `0D xx` where xx = length |
| `0x06` | Polyline-like         | Fixed 8-byte record: `06 xx` + 6 bytes of data         |
| `0xBC` | Boundary marker       | 3 bytes: `BC 00 00`                                    |
| `0xDE` | Ext boundary marker   | 3 bytes: `DE 00 00`                                    |
| `0xE0` | Raster tile (Type E0) | Tile bounds, JPEG size, image index (see below)        |

A typical RGN2 subdivision starts with boundary/preamble records followed by one or more Type E0 raster tile records.

#### 4.5.2 Type E0 Raster Tile Record

Each Type E0 record describes one raster tile's geographic bounds, JPEG size, and reference to the image data in LBL29 via LBL28 index.

**Type E0 Record Format (8-bit index, bits_field=0x2B, total 23 bytes):**

```
Offset | Size | Field           | Description
-------|------|-----------------|------------------------------------------
0      | 1    | Marker          | 0xE0 (Type E0 marker byte)
1      | 1    | bits_field      | 0x2B
2      | 1    | image_index     | uint8 — zero-based index into LBL28 offset array
3      | 16   | Coordinates     | 4 × int32 LE: lat_min, lon_min, lat_max, lon_max
19     | 4    | block_size      | uint32 LE, JPEG file size in bytes
```

**Type E0 Record Format (16-bit index, bits_field=0x25 or 0x2D, total 24 bytes):**

```
Offset | Size | Field           | Description
-------|------|-----------------|------------------------------------------
0      | 1    | Marker          | 0xE0 (Type E0 marker byte)
1      | 1    | bits_field      | 0x25 or 0x2D
2      | 2    | image_index     | uint16 LE — zero-based index into LBL28 offset array
4      | 16   | Coordinates     | 4 × int32 LE: lat_min, lon_min, lat_max, lon_max
20     | 4    | block_size      | uint32 LE, JPEG file size in bytes
```

**Field order is critical:** `image_index` must immediately follow `bits_field`, before the coordinates. Some implementations incorrectly place it at the end of the record, which causes GMT to report zero bitmaps.

**bits_field encoding:**

| Value  | Index size | Use case                            |
| ------ | ---------- | ----------------------------------- |
| `0x2B` | 1 byte     | < 256 tiles total                   |
| `0x25` | 2 bytes    | >= 256 tiles (SwissTopo-like maps)  |
| `0x2D` | 2 bytes    | >= 256 tiles (alternative encoding) |

**image_index:** Zero-based index into the LBL28 offset array. LBL28[image_index] points to the JPEG for this tile in LBL29.

**Coordinate encoding:** Uses 32-bit signed Garmin map units (degrees × 2^31 / 180), distinct from the 3-byte coords used in TRE header bounds.

**RGN data section size:** N × record_size, where N = total tile count and record_size = 23 or 24 bytes depending on bits_field.

#### 4.5.3 RGN5 — Metadata Section

RGN5 is a smaller metadata section observed in IOM.img but not present in SwissTopo_West.

| File               | RGN5 Size | Content                                          |
| ------------------ | --------- | ------------------------------------------------ |
| IOM subfile 355951 | 112 bytes | Starts with `DF 14 06 02 20 0B`, purpose unclear |
| SwissTopo_West     | 0 bytes   | Not present (size=0)                             |

The RGN5 section may contain rendering hints or extended metadata for the raster layer. For writer implementation, it can safely be omitted (size=0), as SwissTopo_West validates correctly without it.

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

## 5. TRE Header Layout and Section Offsets

### 5.1 TRE Header Structure (Raster Maps, 273 bytes)

The TRE sub-header in raster maps uses an extended 273-byte format, significantly larger than vector maps (116-188 bytes). The layout below was verified against the QMapShack wiki analysis by Alex Whiter and confirmed with both IOM.img and SwissTopo_West.img reference files.

**Common sub-header prefix (21 bytes):**

| Offset | Size | Field         | Value              |
| ------ | ---- | ------------- | ------------------ |
| 0x00   | 2    | Header length | 273 (0x0111)       |
| 0x02   | 10   | Signature     | `GARMIN TRE`       |
| 0x0C   | 1    | Version       | 1                  |
| 0x0D   | 1    | Lock          | 0                  |
| 0x0E   | 7    | Date          | 7-byte Garmin date |

**Bounds and section descriptors:**

| TRE Offset | Size | Field                | Description                                                    |
| ---------- | ---- | -------------------- | -------------------------------------------------------------- |
| 0x15       | 3    | North bound          | 3-byte signed LE, map units                                    |
| 0x18       | 3    | East bound           | 3-byte signed LE, map units                                    |
| 0x1B       | 3    | South bound          | 3-byte signed LE, map units                                    |
| 0x1E       | 3    | West bound           | 3-byte signed LE, map units                                    |
| 0x21       | 8    | TRE1 (levels)        | pos(4) + size(4) — **GMP-relative** offset to level data       |
| 0x29       | 8    | TRE2 (subdivisions)  | pos(4) + size(4) — **GMP-relative** offset to subdivision data |
| 0x31       | 10   | TRE3 (copyright)     | pos(4) + size(4) + item_size(2) — **GMP-relative**             |
| 0x3B       | 4    | Padding              | Zeros                                                          |
| 0x3F       | 1    | Flags                | 0x00 or 0x01                                                   |
| 0x40       | 2    | Display priority     | uint16 LE (20 for IOM, 24 for SwissTopo)                       |
| 0x42       | 8    | More flags           | Typically zeros                                                |
| 0x4A       | 14   | TRE4 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**     |
| 0x58       | 14   | TRE5 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**     |
| 0x66       | 14   | TRE6 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**     |
| 0x74       | 4    | Map ID               | uint32 LE                                                      |
| 0x78       | 4    | Padding              | Zeros                                                          |
| 0x7C       | 14   | TRE7 (raster layers) | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**     |
| 0x8A       | 14   | TRE8 (object types)  | pos(4) + size(4) + rec_size(2) + pad(6) — **GMP-relative**     |
| 0x9A       | 16   | Map ID hash          | 16-byte hash value                                             |
| 0xAA       | 4    | Padding              | Zeros                                                          |
| 0xAE       | 14   | TRE9 descriptor      | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**     |
| 0xBC       | 14   | TRE10 descriptor     | pos(4) + size(4) + rec_size(2) + pad(4) — **GMP-relative**     |
| 0xCA       | 5    | Padding              | Zeros                                                          |
| 0xCF       | 4    | Matching number      | uint32 LE                                                      |
| 0xD3       | rest | Map name             | Null-terminated ASCII string                                   |

**Critical: GMP-Relative Offsets.** All `pos` values in the section descriptors above (TRE1 through TRE10) are offsets relative to the **start of the GMP data**, NOT relative to the TRE block start. This is different from what the 2005 Mechalas spec documents for vector maps, where positions are TRE-relative. For raster maps in GMP containers, positions are always GMP-relative.

### 5.2 TRE1 — Map Levels (Zoom Level Table)

TRE1 contains the zoom level definitions as an array of 4-byte records:

```
byte 0:   level_number
byte 1:   zoom_code
bytes 2-3: number_of_subdivisions (uint16 LE)
```

**Observed values from reference files:**

| File               | Levels                                               | Zoom Codes                     | Subdivisions     |
| ------------------ | ---------------------------------------------------- | ------------------------------ | ---------------- |
| IOM subfile 355951 | 0x87(=135), 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00 | 17, 18, 19, 20, 21, 22, 23, 24 | 1 each (8 total) |
| SwissTopo_West     | 0x84, 0x83, 0x02, 0x01, 0x00                         | 20, 21, 22, 23, 24             | 1 each (5 total) |

**Zoom code interpretation:**

- Zoom code 0 = most detailed (highest zoom level)
- Higher zoom codes = less detailed (overview levels)
- The level_number values (0x84, 0x87, etc.) may encode additional flags in their upper bits

**Comparison with vector format:** Vector maps use a different 4-byte record format where byte 0 contains zoom/inherited flags (bits 0-3: zoom level, bit 7: inherited), byte 1 is bits_per_coord, and bytes 2-3 are subdivision count. Raster maps repurpose these fields.

### 5.3 TRE2 — Group/Subdivision Section

TRE2 contains level group records that define the spatial subdivision hierarchy. In raster maps, these are **16-byte records** (not the 14-byte vector format).

**16-byte raster group record format:**

| Offset | Size | Field             | Description                                            |
| ------ | ---- | ----------------- | ------------------------------------------------------ |
| 0      | 3    | RGN offset        | 3-byte LE offset into RGN2 data for this group         |
| 3      | 1    | Object types      | Flags indicating contained object types                |
| 4      | 3    | Longitude center  | 3-byte signed LE, map units (degrees × 2^24 / 360)     |
| 7      | 3    | Latitude center   | 3-byte signed LE, map units (degrees × 2^24 / 360)     |
| 10     | 2    | Flags             | uint16 LE                                              |
| 12     | 2    | Subdivision count | uint16 LE, number of child subdivisions                |
| 14     | 2    | Next level index  | uint16 LE, 1-based index into next zoom level's groups |

**Example from IOM subfile 00355951:**

```
Group 0: rgn_off=46, obj=0x00, lon=-4.50°, lat=54.22°, subdivs=1, next=0
```

**Example from SwissTopo_West:**

```
Group 0: rgn_off=0, obj=0x00, lon=7.47°, lat=46.83°, subdivs=560, next=0
(560 groups covering Switzerland, ~45.8°N to ~47.6°N, ~5.9°E to ~8.4°E)
```

**Note:** The 3-byte coordinate encoding in TRE2 uses the older map units format (degrees × 2^24 / 360), distinct from the 4-byte signed int32 coordinates (degrees × 2^31 / 180) used in Type E0 records within RGN2.

### 5.4 TRE7 — Raster Layer Section

TRE7 defines an offset table that maps zoom levels to their raster layer descriptions in RGN2. The section descriptor at TRE+0x7C includes a `rec_size` field that determines the record format.

**TRE7 descriptor header (at TRE+0x7C):**

```
pos(4):     GMP-relative offset to TRE7 data
size(4):    Total size of TRE7 data
rec_size(2): Size of each record in bytes
pad(4):     Zeros
```

**Record format:**

| Variant              | rec_size | Format                         |
| -------------------- | -------- | ------------------------------ |
| Simple (IOM)         | 4        | uint32 LE offset into RGN2     |
| Extended (SwissTopo) | 5        | uint32 LE offset + 1 byte flag |

**IOM subfile 00355951 example (rec_size=4):**

```
Offset table: [0, 46, 92, 138, 184, 243, 361, 420]
→ 8 entries pointing to raster layer descriptions in RGN2 for 8 zoom levels
```

**SwissTopo_West example (rec_size=5):**

```
748 entries with uint32 offset + 1 byte flag each
→ Points to raster layer descriptions for 560 groups across 5 zoom levels
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

| File               | Entries                              | Description                            |
| ------------------ | ------------------------------------ | -------------------------------------- |
| IOM subfile 355951 | 2 entries: `13 06 06` and `01 06 0D` | Raster tiles (type 0x13) + DATA_BOUNDS |
| SwissTopo_West     | 1 entry: `13 06 06`                  | Raster tiles only                      |

### 5.6 Multi-Resolution Pyramid

SwissTopo files use 5 zoom levels (20-24), forming a pyramid where each level covers the same geographic area with different tile counts and resolutions. IOM uses 8 zoom levels (17-24).

For our implementation, we support configurable zoom levels with the zoom_code specified per level.

## 6. Vector vs Raster Format Differences

This section provides a brief comparison of vector vs raster format differences. For detailed vector format documentation, see **Appendix A** (from Willink/Pinns `expl_img2015.pdf` and Mechalas `imgformat-1.0.pdf`). Raster maps use the same container structure but different internal formats.

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

**Raster maps use value 9 (8-bit encoding) with plain ASCII tile filenames — no bit-packing needed. The codepage is specified separately at LBL offset 0xAA as uint16 LE value 1252.**

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

### 10.1 IOM.img (Isle of Man, Multi-Map Raster)

| Property         | Value                                                 |
| ---------------- | ----------------------------------------------------- |
| File size        | 33,462,272 bytes (31.9 MB)                            |
| Block size       | 2,048 bytes (E1=0x09, E2=0x02)                        |
| Subfiles         | 51 GMP + 1 MPS (multi-map format)                     |
| Map name         | OS Map - Isle of Man                                  |
| Map ID           | PID=1, FID=2150                                       |
| Zoom levels      | 8 levels per subfile (level 0x87 to 0x00, zoom 17-24) |
| Display priority | 20                                                    |
| TRE7 rec_size    | 4 (simple uint32 offsets)                             |
| TRE8 entries     | 2 (raster tiles + DATA_BOUNDS)                        |
| RGN5             | 112 bytes (starts with DF 14 06 02 20 0B)             |
| NET section      | Not present                                           |

**Primary analysis target:** Subfile 00355951 — fully validated against QMapShack wiki analysis by Alex Whiter.

### 10.2 SwissTopo_West.img (Single-Map Raster)

| Property         | Value                                |
| ---------------- | ------------------------------------ |
| File size        | 1,495,072,768 bytes (1.39 GB)        |
| Header date      | 16.04.2022 15:03:56                  |
| Map name         | Svizzera_W Raster Map                |
| Map ID           | 09C102B0                             |
| FAT              | 1000h - 1200h - 20000h, block 32768  |
| Zoom levels      | [20,21,22,23,24], zoom [84,83,2,1,0] |
| Bitmaps          | 32,443 tiles, ~1.49 GB               |
| Subfiles         | 2 (GMP + MPS)                        |
| Display priority | 24                                   |
| TRE7 rec_size    | 5 (uint32 + 1 byte flag)             |
| TRE8 entries     | 1 (raster tiles only)                |
| RGN5             | 0 bytes (not present)                |
| NET section      | Present                              |

### 10.3 SwissTopo_Est.img

| Property    | Value                               |
| ----------- | ----------------------------------- |
| File size   | 1,421,049,856 bytes (1.32 GB)       |
| Header date | 20.04.2022 17:10:22                 |
| Map name    | Svizzera_E Raster Map               |
| Map ID      | 013202B4                            |
| FAT         | 1000h - 1200h - 18000h, block 32768 |
| Bitmaps     | 28,737 tiles, ~1.42 GB              |

### 10.4 Our Implementation Output

| Property           | Value                                    |
| ------------------ | ---------------------------------------- |
| GMT validation     | Exit code 0 (pass)                       |
| Single-tile IMG    | 98,304 bytes, GMT reads correctly        |
| Multi-tile IMG     | 98,304 bytes (3 zooms, 21 tiles), passes |
| GMP subfile name   | Map ID as hex (e.g., "09C102B0")         |
| Character encoding | CP-1252                                  |

## 12. Format Variant Recommendation

### 12.1 Comparison: Single-Map vs Multi-Map Raster IMG

Based on analysis of both reference files, there are two distinct raster IMG format variants:

| Aspect                 | Single-Map (SwissTopo)         | Multi-Map (IOM)                   |
| ---------------------- | ------------------------------ | --------------------------------- |
| GMP subfiles           | 1                              | 51 (one per geographic tile)      |
| MPS subfile            | 98 bytes                       | 3,936 bytes (L-records for all)   |
| File complexity        | Low — single container         | High — FAT chain traversal needed |
| TRE7 rec_size          | 5 (extended)                   | 4 (simple)                        |
| TRE8 entries           | 1                              | 2                                 |
| RGN5 section           | Absent (size=0)                | Present (112 bytes)               |
| NET section            | Present                        | Absent                            |
| bits_field             | 0x2D (2-byte index)            | 0x2B (1-byte index)               |
| Max tiles per subfile  | 32,000+                        | < 256 per subfile                 |
| Block size             | 32,768                         | 2,048                             |
| Display priority       | 24                             | 20                                |
| Cross-reference        | None needed                    | MPS L-records required            |
| Documentation coverage | Complete (all sections parsed) | Complete (validated against wiki) |

### 12.2 Recommendation: Single-Map Format

**Target the SwissTopo single-GMP format** for the writer implementation. Rationale:

1. **Simplicity:** One GMP container = no FAT chain traversal, no multi-map MPS coordination, no subfile cross-referencing. The writer generates exactly 2 subfiles (1 GMP + 1 MPS).

2. **Scalability:** A single GMP container handles 32,000+ tiles (1.4 GB+) with no subfile splitting logic. The FAT system handles multi-part GMP subfiles automatically via part numbers.

3. **Documentation coverage:** All sections are fully understood for single-map format — TRE1 through TRE10, RGN1-RGN5, LBL1/LBL28/LBL29. The QMapShack wiki analysis covers both variants.

4. **Device compatibility:** SwissTopo single-map format is confirmed working on Fenix 6. Both formats work, but single-map is the standard for professional maps.

5. **Implementation path:** Our current writer already uses single-map format. The multi-map format adds complexity with no benefit for most use cases (region splitting is better handled by splitting into separate .img files, as SwissTopo does with West/East).

**When to consider multi-map format:** Only if targeting very small block sizes (2,048 bytes) or if Garmin device compatibility testing reveals that multi-map is required for specific use cases. For all typical raster map use cases, single-map is preferred.

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

## Appendix A: Vector IMG Format Reference

This appendix documents the Garmin **vector** IMG format from the Willink/Pinns PDF (`expl_img2015.pdf`) and Mechalas spec (`imgformat-1.0.pdf`). Vector maps use the same container structure (header, FAT, GMP) as raster maps but have fundamentally different internal data formats. This reference is provided for understanding hybrid raster+vector map possibilities.

### A.1 Vector TRE Subdivision Format

Vector subdivisions define the spatial index for map data. Each map level groups subdivisions together, and each subdivision contains pointers to element data (POIs, polylines, polygons) stored in the RGN subfile.

**Subdivision record sizes:**

| Level        | Record Size | Description                            |
| ------------ | ----------- | -------------------------------------- |
| Lowest level | 14 bytes    | No next-level linkage field            |
| Other levels | 16 bytes    | Includes 2-byte next-level subdivision |

**Subdivision record layout:**

| Offset | Size | Field                  | Description                                                     |
| ------ | ---- | ---------------------- | --------------------------------------------------------------- |
| 0      | 3    | RGN data pointer       | Offset in RGN subfile to this subdivision's element data        |
| 3      | 1    | Object types           | Bit flags indicating contained element types (see table below)  |
| 4      | 3    | Longitude center       | 3-byte signed map units (degrees × 2^24 / 360)                  |
| 7      | 3    | Latitude center        | 3-byte signed map units                                         |
| 10     | 2    | Width                  | Bits 0-14: width, Bit 15: terminating flag for last subdivision |
| 12     | 2    | Height                 | In map units                                                    |
| 14     | 2    | Next level subdivision | 1-based index (only present in non-lowest-level records)        |

**Object type codes** (byte at offset 3):

| Code | POIs | Indexed POIs | Polylines | Polygons | Pointers in RGN |
| ---- | ---- | ------------ | --------- | -------- | --------------- |
| 0x10 | Yes  |              |           |          | 0               |
| 0x20 |      | Yes          |           |          | 0               |
| 0x40 |      |              | Yes       |          | 0               |
| 0x80 |      |              |           | Yes      | 0               |
| 0xC0 |      | Yes          |           | Yes      | 1               |
| 0xD0 | Yes  | Yes          |           | Yes      | 2               |
| 0xE0 |      | Yes          | Yes       | Yes      | 2               |
| 0xF0 | Yes  | Yes          | Yes       | Yes      | 3               |

The number of pointers is (number of element types present) minus 1, because the first element group starts immediately after the pointers. Each pointer is 2 bytes.

**Map levels:** Defined in TRE at offset 0x21. Each map level record specifies the zoom level, bits-per-coordinate resolution, and number of subdivisions at that level. Higher map levels have more subdivisions with finer detail.

**Subdivision addressing:** The 3-byte RGN data pointer at offset 0 is added to the RGN1 base offset (found at RGN header + 0x15) to get the absolute position of the subdivision's element data.

### A.2 Vector RGN Bitstream Encoding

The RGN subfile stores all vector element data (POIs, polylines, polygons) as bitstreams with variable-length encoding.

**RGN sub-file header layout:**

| RGN Offset | Size | Field         | Description                       |
| ---------- | ---- | ------------- | --------------------------------- |
| 0x00       | 2    | Header length |                                   |
| 0x02       | 10   | Signature     | `GARMIN RGN`                      |
| 0x15       | 4    | RGN1 pointer  | Offset to first subdivision data  |
| 0x19       | 4    | RGN1 size     | Length of RGN1 block              |
| 0x1D       | 4    | RGN2 pointer  | Extended polygons (types 0x100+)  |
| 0x21       | 4    | RGN2 size     |                                   |
| 0x39       | 4    | RGN3 pointer  | Extended polylines (types 0x100+) |
| 0x3D       | 4    | RGN3 size     |                                   |
| 0x55       | 4    | RGN4 pointer  | Extended POIs (types 0x100+)      |
| 0x59       | 4    | RGN4 size     |                                   |

**Element data layout within each subdivision:**

Each subdivision's RGN data segment contains element groups in a fixed order:

1. **Pointers** (2 bytes each) — one fewer than the number of element types present
2. **POIs** — variable-length records (see below)
3. **Indexed POIs** — variable-length records
4. **Polylines** — variable-length bitstream records
5. **Polygons** — variable-length bitstream records

**POI record format (no subtype):**

```
type(1) + lbl_I(1) + lbl_II(1) + lbl_III(1) + longitude(2) + latitude(2)
= 8 bytes
```

**POI record format (with subtype):** If bit 7 of `lbl_III` is set, a subtype byte follows the coordinates:

```
type(1) + lbl_I(1) + lbl_II(1) + lbl_III(1) + longitude(2) + latitude(2) + subtype(1)
= 9 bytes
```

Note: The Mechalas spec incorrectly states that the subtype flag is in bit 8 of the first byte. Willink/Pinns corrects this: the flag is bit 7 of the **fourth** byte (lbl_III).

**Polyline record format (9-byte fixed header):**

```
type(1) + lbl_I(1) + lbl_II(1) + lbl_III(1) + lon_delta(2) + lat_delta(2) + length(1)
```

If bit 7 of the type byte is set, the length field is 2 bytes (total header = 10 bytes). The length covers the variable-length coordinate bitstream that follows.

**Polygon record format:** Same as polyline but without the length byte. The polygon's extent is determined from the coordinate bitstream.

**Coordinate bitstream encoding:**

Coordinates are encoded as bitstreams with variable bits-per-coordinate (specified in the map level definition). Key rules:

1. The first byte of the bitstream is a special flags byte:
   - Bit 0: if set, the first coordinate is a negative delta
   - Bit 1: if set, the second coordinate is a negative delta
   - Bits 2-7: reserved or additional flags

2. Subsequent coordinate deltas are encoded using `bits_per_coord` bits each, packed MSB-first.

3. A special bit pattern (`x...x1` where all preceding bits are 0 except the last) signals the end of the coordinate stream.

4. **Left-shifting:** For lower zoom levels with fewer bits_per_coord, coordinates are left-shifted to reduce precision. The shift amount is `(24 - bits_per_coord)`.

### A.3 Vector LBL Label Encoding

Labels in vector IMG files use compact bit-packed encoding rather than plain ASCII (which raster maps use).

**Encoding modes:**

| Value | Mode   | Bits per character | Use case                |
| ----- | ------ | ------------------ | ----------------------- |
| 6     | 6-bit  | 6                  | Standard (most common)  |
| 9     | 8-bit  | 8                  | International maps      |
| 10    | 10-bit | 10                 | Extended character sets |

**6-bit encoding (most common):**

1. Each character is encoded as a 6-bit value (0-63)
2. Characters are packed MSB-first into bytes
3. The character value maps to letters A-Z, digits, and special characters
4. Value encoding: character index = bit-reversed 6-bit value (read bits right-to-left)
5. **Label termination:** If the 6-bit value is > 0x2F, the label ends. Any remaining bits in the current byte are discarded, and the next label starts at the next byte boundary.

**Special character codes:**

| Code  | Meaning                                    |
| ----- | ------------------------------------------ |
| 0x1B  | Symbol prefix — next value is a symbol     |
| 0x1C  | Lowercase prefix — next value is lowercase |
| >0x2F | Label terminator                           |

**LBL pointer structure:**

Labels are referenced via 3-byte pointers from element records (POIs, polylines, polygons). The pointer format:

```
byte 0-1: offset in LBL1 (low bits)
byte 2:   offset in LBL1 (high bits, only bits 0-5 used)
          bit 6: reserved
          bit 7: if set, pointer goes to NET1 first, then to LBL1
```

If bit 7 of the third byte is set, the pointer targets NET1 instead of LBL1 directly. In NET1, a 3-byte pointer to LBL1 is found at the indicated offset.

**LBL header offset table:**

| LBL Offset | Size | Content          |
| ---------- | ---- | ---------------- |
| 0x1F       | 2    | Country records  |
| 0x2D       | 2    | Region records   |
| 0x3B       | 2    | City records     |
| 0x49       | 2    | POI records      |
| 0x57       | 2    | POI LBL6 pointer |
| 0x64       | 2    | ZIP/Post codes   |
| 0x80       | 2    | Highway records  |

### A.4 NET/NOD Overview

**NET sub-file (road network):**

NET stores highway definitions and routing-related data. Key features:

- NET1 block starts at NET + 0x15
- Highway entries contain up to 4 label pointers (3 bytes each), terminated by bit 7 set in the last pointer's third byte
- Highway length encoding varies: if bit 7 of the first byte is set, the road has additional properties
- Connected to the NOD subfile for routing information

**NOD sub-file (routing nodes):**

NOD provides the routing graph structure for navigable roads:

- NOD1: Contains routing node entries with:
  - Pointer to routing information (3 bytes)
  - Flags byte (direction, connectivity)
  - Direction coordinates (longitude/latitude deltas)
  - Node bytes referencing Tables A and B
- NOD2: Contains Tables A and B that define the routing graph connectivity
- Used only for routable maps — **absent in pure raster maps**

**Why NET/NOD are absent in raster maps:** Raster maps contain no routable road network data. They display pre-rendered imagery tiles without searchable vector features. The routing graph is entirely a vector concept.

### A.5 Hybrid Raster+Vector Considerations

Official Garmin maps (like SwissTopo Pro) combine raster and vector data in a single IMG file. Understanding which sections are shared vs. format-specific is key to implementing hybrid maps.

**Shared sections (used by both raster and vector):**

| Section        | Purpose                              | Notes                                               |
| -------------- | ------------------------------------ | --------------------------------------------------- |
| IMG header     | File structure metadata              | Identical format                                    |
| FAT            | Block allocation and subfile listing | Identical format                                    |
| GMP container  | Wraps TRE/RGN/LBL/NET sub-headers    | Same 53-byte header                                 |
| TRE sub-header | Bounds, map levels, subdivisions     | Different sizes: 273B (raster) vs 116-188B (vector) |
| LBL sub-header | Label/image metadata                 | Different sizes: 596B (raster) vs 170-236B (vector) |

**Raster-specific sections:**

| Section | Purpose                               |
| ------- | ------------------------------------- |
| TRE7    | Raster layer offset table             |
| TRE8    | Object type parameters (raster tiles) |
| RGN2    | Type E0 raster tile records           |
| LBL28   | Image index (JPEG offset table)       |
| LBL29   | Image storage (concatenated JPEGs)    |

**Vector-specific sections:**

| Section        | Purpose                           |
| -------------- | --------------------------------- |
| RGN bitstreams | POI/polyline/polygon coordinates  |
| NET            | Road network definitions          |
| NOD            | Routing graph nodes               |
| LBL1           | 6-bit/8-bit/10-bit encoded labels |
| RGN2 (vector)  | Extended polygons (types 0x100+)  |
| RGN3           | Extended polylines (types 0x100+) |
| RGN4           | Extended POIs (types 0x100+)      |

**Hybrid creation strategies:**

1. **GMapTool merge:** Create raster IMG (cartoload) and vector IMG (mkgmap) separately, then merge with GMapTool. This is the simplest approach and matches how Garmin's own tools work.

2. **Direct hybrid writing:** Write both raster and vector subfiles into a single GMP container. This requires understanding how Garmin combines the two sets of TRE/RGN/LBL data — likely using separate TRE sections for raster and vector data within the same GMP subfile.

3. **mkgmap integration:** Use mkgmap for vector generation and add raster tiles as a post-processing step. mkgmap's Java codebase (`uk.me.parabola.imgfmt`) provides a reference for the vector format.

**Existing vector IMG tools:**

| Tool       | Language | Type         | License    | Notes                            |
| ---------- | -------- | ------------ | ---------- | -------------------------------- |
| mkgmap     | Java     | OSM → IMG    | GPL        | Most mature, actively maintained |
| cGPSmapper | Binary   | .mp → IMG    | Freeware   | Well-documented, stable          |
| sendmap    | Binary   | IMG uploader | Freeware   | Uploads to Garmin devices        |
| GPSMapEdit | GUI      | Map editor   | Commercial | Visual editing, exports .mp      |

---

**Analysis based on:**

- IOM: IOM.img (33,462,272 bytes / 31.9 MB, 51 GMP subfiles + 1 MPS)
- SwissTopo_West: my_SwissTopo_West.img (1,495,072,768 bytes / 1.4 GB)
- SwissTopo_Est: my_SwissTopo_Est.img (1,421,049,856 bytes / 1.4 GB)
- GMapTool (gmt) v0.8.220.853b output
- QMapShack wiki — Alex Whiter's raster IMG analysis (IOM subfile 00355951)
- mkgmap source code (`uk.me.parabola.imgfmt` package)
- Hexadecimal dumps of headers and GMP container sections
- `scripts/img_analysis.py` — custom analysis tool with FAT chain traversal and GMP-relative offset parsing
- Willink/Pinns "Exploring Garmin's IMG Format" (2015) — see `expl_img2015.pdf` in this directory
- **Device tested:** Garmin Fenix 6 (confirmed working with reference files)

**Last updated:** 2026-04-23
