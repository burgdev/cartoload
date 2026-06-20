# GMP Container & Sub-Headers

This page describes the GMP container format, subfile organization, and all sub-headers (TRE, RGN, LBL, NET). For the outer file structure (header, FAT), see [Header & FAT](header-fat.md). For the tile data stored inside the GMP, see [Tile Storage](tile-storage.md).

## 3. Subfile Organization

### 3.1 Subfile Types in Raster Maps

Raster IMG files can contain either 2 subfiles (single-map) or many subfiles (multi-map):

**Single-map raster:**

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

| Parameter        | IOM (multi-map) | Single-map reference | cartoload output   |
| ---------------- | --------------- | ---------------------- | ------------------ |
| Display priority | 20              | 24                     | 20                 |
| Parameters       | 1 8 36 1        | 1 4 36 1               | 1 8 36 1           |
| TRE7 rec_size    | 4 (simple)      | 5 (extended)           | 4 (simple + sentinel) |
| TRE8 entries     | 2               | 1                      | 2                  |
| TRE5 data        | None (size=0)   | 3 bytes                | None (size=0)      |
| NET section      | Not present     | Present                | Present (stub)     |

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

After the 21-byte common header, the TRE sub-header uses the following layout. **All position values are GMP-relative offsets** (see [TRE Sections](tre-sections.md#51-tre-header-structure-raster-maps-273-bytes) for complete field reference):

| Offset | Size | Field                 | Description                                   |
| ------ | ---- | --------------------- | --------------------------------------------- |
| 21     | 3    | North bound           | 3-byte signed LE, map units                   |
| 24     | 3    | East bound            | 3-byte signed LE, map units                   |
| 27     | 3    | South bound           | 3-byte signed LE, map units                   |
| 30     | 3    | West bound            | 3-byte signed LE, map units                   |
| 33     | 4    | Map levels position   | uint32 LE, **GMP-relative** (see [TRE1 Map Levels](tre-sections.md#52-tre1--map-levels-zoom-level-table)) |
| 37     | 4    | Map levels size       | uint32 LE                                     |
| 41     | 4    | Subdivisions position | uint32 LE, **GMP-relative** (see [TRE2 Subdivisions](tre-sections.md#53-tre2--groupsubdivision-section)) |
| 45     | 4    | Subdivisions size     | uint32 LE                                     |
| 49     | 4    | Copyright position    | uint32 LE, **GMP-relative**                   |
| 53     | 4    | Copyright size        | uint32 LE                                     |
| 57     | 2    | Copyright item size   | uint16 LE (typically 3)                       |
| ...    | ...  | Remaining fields      | See [TRE Header Structure](tre-sections.md#51-tre-header-structure-raster-maps-273-bytes) for complete TRE header map   |

**3-byte signed map units:** `degrees × 2^24 / 360`. For example, latitude 47.65°:

```
int(47.65 * 2^24 / 360) = 2,225,653 = 0x21E825 → bytes 25 E8 21
```

**Display priority:** 20 (matching IOM reference, optimal for raster basemaps).

### 3.6 RGN Sub-Header (125 bytes)

After the 21-byte common header, the RGN sub-header uses the following layout. All position values are **GMP-relative** offsets. Field values are from the Oppmann PDF spec (2023-09-05) and verified against reference files.

| RGN Offset | Size | Field                   | Description / Reference Value                                  |
| ---------- | ---- | ----------------------- | -------------------------------------------------------------- |
| 0x15       | 4    | RGN1 position           | GMP-relative offset to section 1 data                          |
| 0x19       | 4    | RGN1 size               | Size of section 1 in bytes                                     |
| 0x1D       | 4    | RGN2 position           | GMP-relative offset to polygon/raster section                  |
| 0x21       | 4    | RGN2 size               | Size of polygon section in bytes                               |
| 0x25       | 4    | RGN2 ext: encoding flag | Known values: 0, 2. **Must be 2** for extended/raster maps.    |
| 0x29       | 4    | RGN2 ext: flags[0]      | 0x00000000 (always zero)                                       |
| 0x2D       | 4    | RGN2 ext: flags[1]      | 0x200000FF — polygon local flag bitmask                        |
| 0x31       | 4    | RGN2 ext: flags[2]      | 0x0003FCFD — polygon local flag bitmask                        |
| 0x35       | 4    | RGN2 ext: flags[3]      | 0x00000000 (always zero)                                       |
| 0x39       | 4    | RGN3 position           | GMP-relative offset to polyline section (= rgn2_pos + rgn2_size) |
| 0x3D       | 4    | RGN3 size               | 0 for raster maps                                              |
| 0x41       | 4    | RGN3 ext: reserved      | 0x00000000                                                     |
| 0x45       | 4    | RGN3 ext: flags[0]      | 0x00000000                                                     |
| 0x49       | 4    | RGN3 ext: flags[1]      | 0x2000003F — lines local flag bitmask                          |
| 0x4D       | 4    | RGN3 ext: flags[2]      | 0x00000FFD — lines local flag bitmask                          |
| 0x51       | 4    | RGN3 ext: flags[3]      | 0x00000000                                                     |
| 0x55       | 4    | RGN4 position           | GMP-relative offset to POI section (= rgn2_pos + rgn2_size)    |
| 0x59       | 4    | RGN4 size               | 0 for raster maps                                              |
| 0x5D       | 4    | RGN4 ext: reserved      | 0x00000000                                                     |
| 0x61       | 4    | RGN4 ext: flags[0]      | 0x00000000                                                     |
| 0x65       | 4    | RGN4 ext: flags[1]      | 0x20003FFF — points local flag bitmask   |
| 0x69       | 4    | RGN4 ext: flags[2]      | 0x0FFFF73F — points local flag bitmask   |
| 0x6D       | 4    | RGN4 ext: flags[3]      | 0x00000000                                                     |
| 0x71       | 4    | RGN5 position           | GMP-relative offset to dictionary section (= rgn2_pos + rgn2_size) |
| 0x75       | 4    | RGN5 size               | 0 for raster maps                                              |
| 0x79       | 4    | RGN5 ext: dict info     | 1 (controls Huffman table loading)         |

**Critical field: RGN+0x25.** The value 2 at this offset indicates extended polygon encoding. Without this field set correctly, Garmin device firmware will not parse the RGN2 section as extended/raster data. A value of 0 means standard (non-extended) polygon format.

**Local flag bitmasks:** The flags fields at 0x2D, 0x31, 0x49, 0x4D, 0x65, 0x69 are bitmasks that tell the device firmware which extended object types (type values >= 0x100) have local fields in each section.

**Section positions for empty sections:** RGN3, RGN4, and RGN5 positions are set to `rgn2_pos + rgn2_size` (immediately after the RGN2 data) with size=0, indicating no polyline, POI, or dictionary data.

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

### 10.2 Single-Map Raster Reference

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

### 10.3 Single-Map Raster Reference (East)

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
| Display priority   | 20 (matches IOM reference)               |
| TRE7 rec_size      | 4 (uint32 offset only + sentinel)        |
| TRE8 entries       | 2 (polyline 0x06 + polygon 0x0D)         |
| TRE5 data          | None (size=0)                            |
| TRE parameters     | `10 01 08 24 00 01 00 00` (matches IOM)  |


## 12. Format Variant Recommendation

### 12.1 Comparison: Single-Map vs Multi-Map Raster IMG

Based on analysis of both reference files, there are two distinct raster IMG format variants:

| Aspect                 | Single-Map (reference)         | Multi-Map (IOM)                   | Our Output                       |
| ---------------------- | ------------------------------ | --------------------------------- | -------------------------------- |
| GMP subfiles           | 1                              | 51 (one per geographic tile)      | 1 (single-map format)            |
| MPS subfile            | 98 bytes                       | 3,936 bytes (L-records for all)   | 98 bytes                         |
| File complexity        | Low — single container         | High — FAT chain traversal needed | Low — single container           |
| TRE7 rec_size          | 5 (extended)                   | 4 (simple)                        | 4 (simple + sentinel)            |
| TRE8 entries           | 1                              | 2                                 | 2                                |
| TRE5 data              | 3 bytes                        | None (size=0)                     | None (size=0)                    |
| RGN5 section           | Absent (size=0)                | Present (112 bytes)               | Absent (size=0)                  |
| NET section            | Present                        | Absent                            | Present (stub)                   |
| bits_field             | 0x2D (2-byte index)            | 0x2B (1-byte index)               | Variable (depends on tile count) |
| Max tiles per subfile  | 32,000+                        | < 256 per subfile                 | 32,000+                          |
| Block size             | 32,768                         | 2,048                             | 32,768                           |
| Display priority       | 24                             | 20                                | 20                               |
| TRE parameters         | `00 01 04 24 00 01 00 00`      | `10 01 08 24 00 01 00 00`         | `10 01 08 24 00 01 00 00`        |
| Cross-reference        | None needed                    | MPS L-records required            | None needed                      |
| Documentation coverage | Complete (all sections parsed) | Complete (validated against wiki) | Complete                         |

### 12.2 Recommendation: IOM-Compatible Format

**Our implementation targets the IOM parameter set** within a single-GMP container. Rationale:

1. **Device compatibility:** The IOM parameter set (priority 20, TRE7 rec_size=4, TRE8 with 2 entries, TRE parameters `10 01 08 24`) is proven to work on Garmin devices for both multi-map and single-map configurations. The single-map parameter set uses a different TRE7 format (rec_size=5 with flag bytes) that is less well understood.

2. **GPXSee compatibility:** The TRE7 rec_size=4 format with `_flags=0x01` is cleanly parsed by GPXSee: it reads exactly 4 bytes per entry (polygon offset only) and uses the sentinel entry for `setExtEnds()`.

3. **Simplicity:** Single GMP container = no FAT chain traversal, no multi-map MPS coordination. The writer generates exactly 2 subfiles (1 GMP + 1 MPS).

4. **Scalability:** A single GMP container handles 32,000+ tiles with no subfile splitting logic. The FAT system handles multi-part GMP subfiles automatically.

5. **Documentation coverage:** All sections are fully understood — TRE1 through TRE10, RGN1-RGN5, LBL1/LBL28/LBL29. Validated against both IOM reference and GPXSee source code.

6. **Implementation path:** Our writer uses single-map container format with IOM-compatible TRE parameters, confirmed working on GPXSee and Garmin devices.

**When to consider multi-map format:** Only if targeting very small block sizes (2,048 bytes) or if Garmin device compatibility testing reveals that multi-map is required for specific use cases. For all typical raster map use cases, single-map is preferred.
