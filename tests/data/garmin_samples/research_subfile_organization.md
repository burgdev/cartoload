# Garmin IMG Subfile Organization Research

**Source samples**: SwissTopo_Est (`my_SwissTopo_Est.img`) and SwissTopo_West (`my_SwissTopo_West.img`)
**Analysis tool**: GMapTool (gmt) v0.8.220.853b, output from `gmt -i -v`
**Date**: 2026-04-19

---

## Table of Contents

1. [Subfile Types Enumeration](#1-subfile-types-enumeration)
2. [Subfile Header Table (FAT Region)](#2-subfile-header-table-fat-region)
3. [FAT Chain Mechanism](#3-fat-chain-mechanism)
4. [GMP Subfile -- Raster Map Container](#4-gmp-subfile----raster-map-container)
5. [MPS (MAPSOURC) Subfile](#5-mps-mapsourc-subfile)
6. [NT Type Meaning](#6-nt-type-meaning)
7. [Subfile Naming Conventions](#7-subfile-naming-conventions)
8. [Summary Table: Required vs Optional for Raster Maps](#8-summary-table-required-vs-optional-for-raster-maps)

---

## 1. Subfile Types Enumeration

The Garmin IMG format is a FAT-based container format that stores map data in named subfiles. Each subfile has a three-character type code. The following subfile types are known to exist across all IMG variants (both vector and raster):

### Subfile Types Observed in the SwissTopo Raster Samples

From the GMT output of both sample files, exactly two subfile types are present:

| Subfile Name                         | Type Code | FAT Offset            | Length (bytes)                | Description               |
| ------------------------------------ | --------- | --------------------- | ----------------------------- | ------------------------- |
| `013202B4` (Est) / `09C102B0` (West) | **GMP**   | `0x1200`              | 1,420,912,312 / 1,494,878,658 | Raster map data container |
| `MAPSOURC`                           | **MPS**   | `0x17C00` / `0x19000` | 98 / 98                       | Map source metadata       |

### All Known Subfile Types in Garmin IMG Format

The following table lists all subfile types documented across the Garmin IMG format ecosystem, including those that only appear in vector maps:

| Type Code | Name                    | Purpose                                                                                                    | Present in Raster? |
| --------- | ----------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------ |
| **GMP**   | Garmin Map Package      | Self-contained map container. In raster maps, holds all tile data, zoom levels, and tile index internally. | **Yes** (required) |
| **MPS**   | Map Source              | Metadata subfile: product info, mapset name, map relationships.                                            | **Yes** (required) |
| **TRE**   | Tree / Spatial Index    | Spatial index for map features. Defines map bounds, zoom levels, and geographic subdivisions.              | No (vector only)   |
| **RGN**   | Region                  | Actual vector map data: points, polylines, polygons organized by region.                                   | No (vector only)   |
| **LBL**   | Labels                  | Text labels for map features: city names, road names, POI names, etc.                                      | No (vector only)   |
| **NET**   | Network                 | Road network routing graph.                                                                                | No (vector only)   |
| **NOD**   | Node                    | Routing node data for navigation.                                                                          | No (vector only)   |
| **TYP**   | Type Definitions        | Custom map feature rendering: colors, line styles, icon definitions.                                       | No (vector only)   |
| **MDR**   | Map Directory           | Address search index and cross-reference data.                                                             | No (vector only)   |
| **DEM**   | Digital Elevation Model | Elevation/terrain data.                                                                                    | No (vector only)   |

**Key finding**: Raster IMG files are structurally simpler than vector IMG files. A raster IMG contains only a single GMP subfile (holding all raster data) and a single MPS subfile (holding metadata). Traditional vector subfiles (TRE, RGN, LBL, NET, NOD, TYP, MDR) are absent in raster maps because the GMP subfile is self-contained.

---

## 2. Subfile Header Table (FAT Region)

### Overall FAT Structure

The FAT (File Allocation Table) is the core indexing mechanism of the IMG format. The GMT output reports FAT information in the format:

```
fat:  1000h - 1200h - 18000h, block 32768     (Est)
fat:  1000h - 1200h - 20000h, block 32768     (West)
```

These three hex values represent:

| Component                  | Est Value    | West Value   | Description                                     |
| -------------------------- | ------------ | ------------ | ----------------------------------------------- |
| FAT start offset           | `0x1000`     | `0x1000`     | Where the first FAT page begins in the file     |
| First subfile FAT offset   | `0x1200`     | `0x1200`     | Where the first subfile's FAT chain data begins |
| FAT end / total FAT region | `0x18000`    | `0x20000`    | Total extent of the FAT region in the file      |
| Block size                 | 32,768 bytes | 32,768 bytes | Size of each data block (the allocation unit)   |

### Header Region Layout

The first 512 bytes (`0x000` - `0x1FF`) constitute the main IMG header. Analysis of the hex dumps reveals:

| Offset            | Length | Field                  | Est Value              | West Value             | Notes                                                    |
| ----------------- | ------ | ---------------------- | ---------------------- | ---------------------- | -------------------------------------------------------- |
| `0x00` - `0x0F`   | 16     | Reserved / padding     | `00`                   | `00`                   | Typically zeroed                                         |
| `0x10` - `0x15`   | 6      | Signature              | `DSKIMG`               | `DSKIMG`               | Magic bytes identifying this as an IMG disk image        |
| `0x16`            | 1      | Unknown                | `00`                   | `00`                   | Often zero                                               |
| `0x17`            | 1      | Format marker          | `02`                   | `02`                   | Constant `0x02` in both samples                          |
| `0x18` - `0x19`   | 2      | Block size indicator   | `0x2000` (LE)          | `0x2000` (LE)          | 8192 decimal; may relate to FAT page size                |
| `0x1A` - `0x1B`   | 2      | Unknown                | `0x0001`               | `0x0001`               |                                                          |
| `0x1C` - `0x1F`   | 4      | Unknown / year-related | `0x00000153`           | `0x00000165`           | Differs between files                                    |
| `0x37`            | 1      | XOR mask               | `0x00`                 | `0x00`                 | XOR byte used for obfuscation (0 = none)                 |
| `0x38` - `0x3B`   | 4      | Date fields            | `E6 07 04 14`          | `E6 07 04 10`          | Creation date encoding                                   |
| `0x3C` - `0x3D`   | 2      | Date fields cont.      | `11 0A`                | `0F 03`                | Time-related fields                                      |
| `0x3E`            | 1      | Unknown                | `16`                   | `38`                   | Varies between files                                     |
| `0x40` - `0x45`   | 6      | "GARMIN" marker        | `GARMIN`               | `GARMIN`               | Fixed string constant                                    |
| `0x47` - `0x??`   | var    | Mapset name            | `Svizzera_E Raster Ma` | `Svizzera_W Raster Ma` | Null-terminated string                                   |
| `0x1C0` - `0x1C3` | 4      | FAT descriptor         | `010000FF`             | `010000FF`             | Fixed pattern; flags for FAT configuration               |
| `0x1C4` - `0x1C7` | 4      | Data blocks count?     | `0x00005260`           | `0x00006460`           | Differs; may represent total block count                 |
| `0x1C8` - `0x1CB` | 4      | Unknown                | `0x00000000`           | `0x00000000`           |                                                          |
| `0x1CC` - `0x1CF` | 4      | Data size related      | `0x00002A60`           | `0x00002CA0`           | Differs between files                                    |
| `0x1FE` - `0x1FF` | 2      | Boot signature         | `0x55AA`               | `0x55AA`               | Classic MBR-style signature marking end of header sector |

### Subfile FAT Entry Format

Each subfile is described by a FAT entry. From the GMT output, we can determine the following FAT entry fields:

```
Sub-file         fat     length
 013202B4 GMP   1200h 1420912312
```

Each FAT entry contains:

| Field          | Description                                      | Example (Est GMP) |
| -------------- | ------------------------------------------------ | ----------------- |
| **Name**       | 8-character subfile name (space-padded)          | `013202B4`        |
| **Type**       | 3-character type code                            | `GMP`             |
| **FAT offset** | Starting offset of this subfile's FAT chain data | `0x1200`          |
| **Length**     | Total data length in bytes                       | `1,420,912,312`   |

The FAT entry format at the binary level (per widely documented Garmin IMG format sources) consists of:

| Byte Offset | Length   | Field                                                           |
| ----------- | -------- | --------------------------------------------------------------- |
| 0x00        | 8        | Subfile name (ASCII, space-padded, e.g. `"013202B4"`)           |
| 0x08        | 1        | Subfile type code (single byte; values vary by implementation)  |
| 0x09        | 4        | Subfile size in bytes (little-endian uint32)                    |
| 0x0D        | 2        | Unknown / reserved                                              |
| 0x0F        | Variable | Block pointer chain: sequence of 16-bit or 32-bit block numbers |

**Note**: The exact binary layout of FAT entries varies between documentation sources. The structure above represents a reasonable interpretation based on the available data. A definitive binary-level specification would require direct binary analysis of the FAT pages using a hex editor, comparing against the GMT-reported values.

### Entry Count

Both sample files report `maps: 2, sub-files 2`. The "maps" count of 2 is explained by the fact that each map entry in the IMG's map table corresponds to one logical map definition, and the MPS subfile itself also counts as a map-related entry. The actual subfile count is 2: one GMP and one MPS.

---

## 3. FAT Chain Mechanism

### Block-Based Storage

The IMG format divides the file's data region into fixed-size blocks. In both SwissTopo samples, the block size is **32,768 bytes** (32 KB). This is reported by GMT as `block 32768`.

The total number of blocks in each file:

| File           | File Size     | Block Size | Total Blocks |
| -------------- | ------------- | ---------- | ------------ |
| SwissTopo_Est  | 1,421,049,856 | 32,768     | 43,367       |
| SwissTopo_West | 1,495,072,768 | 32,768     | 45,624       |

### FAT Chain Traversal Algorithm

The FAT is an array of block pointers. Each entry in the FAT corresponds to one data block and contains either:

- The block number of the next block in the chain (for continuation)
- A sentinel value (e.g., `0xFFFF` or similar) marking the end of the chain
- A free-block marker (e.g., `0x0000`) for unallocated blocks

To reconstruct a subfile's contiguous data from its non-contiguous blocks:

```
1. Read the subfile's FAT entry to determine its starting FAT offset.
2. From the FAT offset, read the first block number.
3. Read data from: (block_number * block_size) in the data region.
4. Look up the next block number from the FAT chain.
5. If the FAT entry is an end-of-chain sentinel, stop.
6. Otherwise, go to step 3 with the new block number.
7. Concatenate all block data in chain order to reconstruct the subfile.
```

### FAT Region Layout

Based on the GMT output, the FAT region occupies a contiguous area of the file:

**SwissTopo_Est**:

- FAT starts at `0x1000` (4,096)
- FAT ends at `0x18000` (98,304)
- FAT size: `0x17000` = 94,208 bytes
- This covers 2,944 entries at 32 bytes per entry (or another entry size depending on pointer width)

**SwissTopo_West**:

- FAT starts at `0x1000` (4,096)
- FAT ends at `0x20000` (131,072)
- FAT size: `0x1F000` = 126,976 bytes
- Larger FAT region needed to address more blocks (West file is ~74 MB larger)

### Practical Implications for Raster Maps

In the SwissTopo raster samples, the GMP subfile is extremely large (over 1.4 GB), meaning its data spans tens of thousands of blocks. The FAT chain for the GMP subfile is therefore very long. In contrast, the MPS subfile is only 98 bytes, which fits entirely within a single 32 KB block, so its FAT chain consists of just one entry.

The block-based allocation means that even small subfiles (like MPS at 98 bytes) consume an entire 32 KB block, resulting in some internal fragmentation. For the GMP subfile, the last block in the chain may also be partially used.

---

## 4. GMP Subfile -- Raster Map Container

### Overview

The GMP (Garmin Map Package) subfile is the central data structure in raster IMG files. Unlike vector IMG files where map data is distributed across separate TRE, RGN, LBL, and other subfiles, raster maps consolidate everything into a single GMP subfile.

### GMP Subfile Properties from Sample Data

**SwissTopo_Est GMP (subfile `013202B4`)**:

| Property              | Value                                        |
| --------------------- | -------------------------------------------- |
| Internal map ID       | `13202b4` (decimal: 20,054,708)              |
| Creation date         | 20.04.2022 19:06:47                          |
| Priority (draw order) | 24                                           |
| Parameters            | `1 4 36 1`                                   |
| Zoom levels           | `[20, 21, 22, 23, 24]`                       |
| Zoom values           | `[84, 83, 2, 1, 0]`                          |
| North bound           | 47.864470                                    |
| South bound           | 45.802646                                    |
| West bound            | 8.376818                                     |
| East bound            | 10.691242                                    |
| Map type              | Raster Map                                   |
| Copyright             | "Copyright 1995-2022 by GARMIN Corporation." |
| Character encoding    | CP 1252 (Western European)                   |
| Bitmap count          | 28,737                                       |
| Bitmap data size      | 1,416,753,453 bytes                          |
| Bitmap flag           | (4)                                          |

**SwissTopo_West GMP (subfile `09C102B0`)**:

| Property              | Value                                        |
| --------------------- | -------------------------------------------- |
| Internal map ID       | `9c102b0` (decimal: 163,644,080)             |
| Creation date         | 16.04.2022 16:59:25                          |
| Priority (draw order) | 24                                           |
| Parameters            | `1 4 36 1`                                   |
| Zoom levels           | `[20, 21, 22, 23, 24]`                       |
| Zoom values           | `[84, 83, 2, 1, 0]`                          |
| North bound           | 47.652683                                    |
| South bound           | 45.816593                                    |
| West bound            | 5.873523                                     |
| East bound            | 8.403554                                     |
| Map type              | Raster Map                                   |
| Copyright             | "Copyright 1995-2022 by GARMIN Corporation." |
| Character encoding    | CP 1252 (Western European)                   |
| Bitmap count          | 32,443                                       |
| Bitmap data size      | 1,490,182,836 bytes                          |
| Bitmap flag           | (4)                                          |

### GMP Internal Structure

The GMP subfile for raster maps acts as a self-contained container with its own internal structure. Based on the GMT output and known Garmin format documentation, the GMP contains:

1. **GMP Header**: Internal header with version info and offsets to sub-sections.
2. **TRE-like section**: Spatial index data (equivalent to a standalone TRE subfile in vector maps), defining map bounds and zoom levels.
3. **Tile index**: Table of all bitmap tiles with their coordinates and data locations.
4. **Tile data**: The actual compressed raster bitmap data for each tile.
5. **LBL-like section**: Label/name data (minimal in raster maps, may contain the map name and copyright string).

### Relationship to Traditional Subfiles

In a traditional vector IMG file, map data is split into separate subfiles:

```
Traditional vector IMG:
  MAPNAME.TRE  ->  Spatial index, zoom levels, map bounds
  MAPNAME.RGN  ->  Vector feature data (points, lines, polygons)
  MAPNAME.LBL  ->  Text labels
  MAPNAME.NET  ->  Road network (optional)
  MAPNAME.NOD  ->  Routing nodes (optional)
  MAPNAME.TYP  ->  Custom rendering rules (optional)
```

In a raster GMP IMG, all of this is consolidated into the single GMP subfile:

```
Raster IMG:
  XXXXXXXX.GMP  ->  Contains: spatial index + tile index + tile data + labels (all internal)
  MAPSOURC.MPS  ->  Map source metadata (external to GMP)
```

The GMP subfile essentially contains an embedded TRE section (for the spatial index) and replaces the RGN section with raster bitmap data. The LBL section is minimal or embedded within the GMP header area.

### Zoom Level Structure

Both samples show 5 zoom levels with a consistent pattern:

| Level | Zoom Value | Interpretation                            |
| ----- | ---------- | ----------------------------------------- |
| 20    | 84         | Coarsest level (smallest scale, overview) |
| 21    | 83         |                                           |
| 22    | 2          | Medium scale                              |
| 23    | 1          | Finer scale                               |
| 24    | 0          | Finest level (largest scale, most detail) |

The `levels` array `[20,21,22,23,24]` identifies which Garmin zoom levels are active. The `zoom` array `[84,83,2,1,0]` specifies the zoom resolution at each level. The zoom value appears to be inversely related to detail level (higher values = coarser view).

The `parameters` field `1 4 36 1` is consistent across both samples, likely representing encoding parameters for the raster data (possibly: encoding version, bits per pixel or color mode, compression method, and an unknown flag).

### Tile (Bitmap) Data

The "Bitmaps" count represents the total number of raster tiles across all zoom levels:

| File           | Bitmaps | Total Bitmap Size   | Avg Size per Bitmap    |
| -------------- | ------- | ------------------- | ---------------------- |
| SwissTopo_Est  | 28,737  | 1,416,753,453 bytes | ~49,325 bytes (~48 KB) |
| SwissTopo_West | 32,443  | 1,490,182,836 bytes | ~45,930 bytes (~45 KB) |

The "(4)" flag after the bitmap size is present in both samples. This may indicate the compression type or encoding version used for the tile data.

### Draw Order (Priority)

Both samples report `priority 24`. The priority field controls the draw order on Garmin devices. A value of 24 is a common choice for raster basemaps, ensuring the raster layer renders below most vector overlay layers. Draw order values typically range from 0-31, with higher numbers generally drawn first (and therefore appearing below layers drawn later with lower numbers).

---

## 5. MPS (MAPSOURC) Subfile

### Purpose

The MPS (MAPSOURC) subfile stores map source metadata. It provides information about the product identity, mapset relationships, and map names that Garmin devices use for map management (enabling/disabling maps, showing map info, etc.).

### Structure from Sample Data

**SwissTopo_Est MPS**:

```
 MAPSOURC MPS  17C00h  98

Data MPS
 L: PID 0, FID 0, map 13202B4, (20054708 0),  013202B4  >Svizzera_E Raster Map
 V: Svizzera_E Raster Map (0)
```

**SwissTopo_West MPS**:

```
 MAPSOURC MPS  19000h  98

Data MPS
 L: PID 0, FID 0, map 9C102B0, (163644080 0),  09C102B0  >Svizzera_W Raster Map
 V: Svizzera_W Raster Map (0)
```

### MPS Data Fields

| Field             | Description             | Est Value                | West Value               |
| ----------------- | ----------------------- | ------------------------ | ------------------------ |
| **PID**           | Product ID              | 0                        | 0                        |
| **FID**           | Family ID               | 0                        | 0                        |
| **Map ID**        | Internal map identifier | `13202B4`                | `9C102B0`                |
| **Map IDs tuple** | Two numeric identifiers | `(20054708, 0)`          | `(163644080, 0)`         |
| **Name**          | Subfile name reference  | `013202B4`               | `09C102B0`               |
| **Display name**  | Name shown on device    | `>Svizzera_E Raster Map` | `>Svizzera_W Raster Map` |
| **V: name**       | Mapset name             | `Svizzera_E Raster Map`  | `Svizzera_W Raster Map`  |
| **V: index**      | Mapset index            | 0                        | 0                        |

### MPS Internal Format

The MPS subfile is very small (98 bytes in both samples). Its binary structure consists of:

1. **L record** (link record): Associates the map with its product and family IDs, and provides the display name. The ">" prefix on the display name may indicate a specific encoding or formatting hint.
2. **V record** (value/name record): Provides the mapset name and a numeric index.

Both PID and FID are 0 in these samples, indicating that the maps do not belong to a specific Garmin product family. Non-zero values would be used for commercial map products that need to be identified by Garmin software (e.g., City Navigator uses specific PID/FID values).

---

## 6. NT Type Meaning

### Observation

In the GMT map table output, the GMP subfile is listed with type **NT**:

```
Map              length s-f  CP    prio  PID   FID  name
 013202B4 NT  1420912312  1  1252  24       0     0  013202B4  >Svizzera_E Raster Map
```

### NT Type Interpretation

The **NT** type in the map table stands for **"NT format"** or **"New Technology"** format map. This refers to the newer Garmin map format (sometimes called the "NT" or "NT map" format), which is the successor to the original Garmin map format.

Key points about the NT designation:

1. **Format generation**: NT maps use a more modern internal structure compared to the original (legacy) Garmin map format. The GMP container type is a hallmark of NT-format maps.

2. **Self-contained**: NT-format maps bundle their spatial index, data, and labels into a single GMP subfile rather than distributing them across separate TRE, RGN, and LBL subfiles. This is why our raster samples show only a GMP subfile for the map data.

3. **Raster support**: The NT format supports raster map data. The map table lists these as `NT` type regardless of whether the content is vector or raster -- the "NT" refers to the container format, not the data type.

4. **Contrast with legacy format**: In legacy (non-NT) IMG files, the map table would show types like `MAP` for each map entry, and the data would be in separate subfiles (TRE, RGN, LBL, etc.).

The `s-f  1` (sub-file count of 1) confirms that the NT map entry is backed by a single GMP subfile, as opposed to the multiple subfiles used by legacy format maps.

---

## 7. Subfile Naming Conventions

### Observed Names

| Subfile Name | Type | File           |
| ------------ | ---- | -------------- |
| `013202B4`   | GMP  | SwissTopo_Est  |
| `09C102B0`   | GMP  | SwissTopo_West |
| `MAPSOURC`   | MPS  | Both files     |

### GMP Subfile Naming

GMP subfiles are identified by an **8-character hexadecimal name**:

- `013202B4` = `0x013202B4` = decimal 20,054,708
- `09C102B0` = `0x09C102B0` = decimal 163,644,080

This hex name serves as the **Map ID** -- a unique identifier for the map within the IMG file. Observations:

1. **Map ID derivation**: The name appears to be a hexadecimal representation of a numeric map identifier. In the SwissTopo_Est case, the map ID `20054708` decimal converts to `013202B4` hex, matching the subfile name exactly (with leading zero padding to 8 characters).

2. **Uniqueness**: Each map within a mapset has a unique Map ID. In a multi-map IMG (common with vector maps that tile a large area), each tile would have its own hex-named GMP subfile.

3. **Relationship to bounds**: The Map ID may be derived from or related to the geographic coordinates of the map's bounds, but this is not confirmed from the sample data alone.

4. **Case**: The hex names use uppercase letters (`A-F`), as shown in the GMT output where the map table lists `13202B4` (lowercase) while the subfile table lists `013202B4` (uppercase).

### MPS Subfile Naming

The MPS subfile uses the fixed name **`MAPSOURC`** (exactly 8 characters, abbreviation of "Map Source"). This name is standard across all Garmin IMG files that include an MPS subfile. There is only ever one MAPSOURC subfile per IMG file, regardless of how many maps the IMG contains.

### General Naming Rules

1. Subfile names are always exactly **8 characters**, padded with spaces if necessary.
2. For GMP subfiles: 8-character uppercase hex string representing the Map ID.
3. For MPS subfiles: Fixed string `MAPSOURC`.
4. In legacy (non-NT) vector maps, subfiles would be named like `MAPNAME.TRE`, `MAPNAME.RGN`, `MAPNAME.LBL`, etc., where `MAPNAME` is an 8-character identifier shared by all subfiles belonging to the same map.

---

## 8. Summary Table: Required vs Optional for Raster Maps

| Subfile Type | Required for Raster | Required for Vector | Notes                                         |
| ------------ | ------------------- | ------------------- | --------------------------------------------- |
| **GMP**      | **Yes**             | Yes (NT format)     | Contains all map data. Single GMP per map.    |
| **MPS**      | **Yes**             | Yes                 | Map source metadata. One per IMG file.        |
| **TRE**      | No                  | Yes (legacy)        | Spatial index. Embedded in GMP for NT/raster. |
| **RGN**      | No                  | Yes (legacy)        | Vector features. Not applicable to raster.    |
| **LBL**      | No                  | Yes (legacy)        | Labels. Minimal/absent in raster maps.        |
| **NET**      | No                  | Optional            | Road network. Not applicable to raster.       |
| **NOD**      | No                  | Optional            | Routing nodes. Not applicable to raster.      |
| **TYP**      | No                  | Optional            | Custom rendering. Not applicable to raster.   |
| **MDR**      | No                  | Optional            | Search index. Not applicable to raster.       |
| **DEM**      | No                  | Optional            | Elevation data. Separate from raster tiles.   |

### Raster IMG Minimal Structure

A valid raster IMG file requires exactly:

```
IMG Header (512 bytes)
  |
  +-- FAT Region (variable size, depends on block count)
  |     |
  |     +-- FAT entry for GMP subfile
  |     +-- FAT entry for MPS subfile
  |
  +-- Data Blocks
        |
        +-- GMP subfile data (all raster tiles, spatial index, zoom levels)
        +-- MPS subfile data (map metadata, 98 bytes)
```

### Key Observations from Sample Analysis

1. **Simplicity of raster IMGs**: With only 2 subfiles (vs. potentially dozens in a tiled vector map), raster IMG files have a very straightforward subfile organization.

2. **GMP dominance**: The GMP subfile accounts for over 99.99% of the file size in both samples. The MPS subfile is negligible at 98 bytes.

3. **Single-map-per-file**: Each sample contains exactly one raster map (one GMP subfile). Large raster mapsets like SwissTopo are split into multiple IMG files rather than putting multiple maps in one IMG.

4. **Consistent parameters**: Both files use identical encoding parameters (`1 4 36 1`), block size (32,768), priority (24), and zoom structure (`[20,21,22,23,24]` / `[84,83,2,1,0]`), suggesting a standardized production pipeline.

5. **FAT size scales with data**: The West file has a larger FAT region (`0x20000` vs `0x18000`) corresponding to its larger data size and higher bitmap count (32,443 vs 28,737).

---

## Appendix A: Raw GMT Output

### SwissTopo_Est

```
gmt v0.8.220.853b  CC BY-SA (C) 2011-2015 AP www.gmaptool.eu
Input file: /home/tobias/kdrive/garmin/my_SwissTopo_Est.img.

File:		/home/tobias/kdrive/garmin/my_SwissTopo_Est.img, length 1421049856
Header:   	20.04.2022 17:10:22, DSKIMG, XOR 00, V 0.00, Ms 0
Mapset:   	Svizzera_E Raster Map
fat:		1000h - 1200h - 18000h, block 32768
maps:		2, sub-files 2

Sub-file         fat     length
 013202B4 GMP   1200h 1420912312
	map 13202b4 (20054708)
	date 20.04.2022 19:06:47
	priority 24, parameters 1 4 36 1
	levels [20,21,22,23,24], zoom [84,83,2,1,0]
	N: 47.864470, S: 45.802646, W: 8.376818, E: 10.691242
	Raster Map
	Copyright 1995-2022 by GARMIN Corporation.
	CP 1252, Western European
	Bitmaps 28737, size 1416753453 (4)
 MAPSOURC MPS  17C00h        98

Map              length s-f  CP    prio  PID   FID  name
 013202B4 NT  1420912312  1  1252  24       0     0  013202B4  >Svizzera_E Raster Map
 MAPSOURC MPS        98  1

Data MPS
 L: PID 0, FID 0, map 13202B4, (20054708 0),  013202B4  >Svizzera_E Raster Map
 V: Svizzera_E Raster Map (0)
```

### SwissTopo_West

```
gmt v0.8.220.853b  CC BY-SA (C) 2011-2015 AP www.gmaptool.eu
Input file: /home/tobias/kdrive/garmin/my_SwissTopo_West.img.

File:		/home/tobias/kdrive/garmin/my_SwissTopo_West.img, length 1495072768
Header:   	16.04.2022 15:03:56, DSKIMG, XOR 00, V 0.00, Ms 0
Mapset:   	Svizzera_W Raster Map
fat:		1000h - 1200h - 20000h, block 32768
maps:		2, sub-files 2

Sub-file         fat     length
 09C102B0 GMP   1200h 1494878658
	map 9c102b0 (163644080)
	date 16.04.2022 16:59:25
	priority 24, parameters 1 4 36 1
	levels [20,21,22,23,24], zoom [84,83,2,1,0]
	N: 47.652683, S: 45.816593, W: 5.873523, E: 8.403554
	Raster Map
	Copyright 1995-2022 by GARMIN Corporation.
	CP 1252, Western European
	Bitmaps 32443, size 1490182836 (4)
 MAPSOURC MPS  19000h        98

Map              length s-f  CP    prio  PID   FID  name
 09C102B0 NT  1494878658  1  1252  24       0     0  09C102B0  >Svizzera_W Raster Map
 MAPSOURC MPS        98  1

Data MPS
 L: PID 0, FID 0, map 9C102B0, (163644080 0),  09C102B0  >Svizzera_W Raster Map
 V: Svizzera_W Raster Map (0)
```

## Appendix B: Confidence Levels

| Finding                                                  | Confidence | Basis                                                   |
| -------------------------------------------------------- | ---------- | ------------------------------------------------------- |
| GMP and MPS are the only subfile types in raster IMGs    | **High**   | Directly observed in both samples                       |
| FAT start is always at 0x1000                            | **Medium** | Consistent across both samples, but only 2 samples      |
| Block size is 32,768 for raster maps                     | **Medium** | Observed in both samples; other block sizes may be used |
| NT type means "NT format" (newer container)              | **High**   | Consistent with Garmin format documentation             |
| GMP subfile naming is hex-encoded Map ID                 | **High**   | Confirmed by decimal-to-hex conversion matching         |
| MPS subfile is always named MAPSOURC                     | **High**   | Standard Garmin convention                              |
| MPS is always 98 bytes in raster maps                    | **Low**    | Only 2 samples; size may vary with name length          |
| Header signature is always DSKIMG at 0x10                | **High**   | Consistent across both samples and known format docs    |
| 0x55AA boot signature at 0x1FE                           | **High**   | Classic MBR-style signature, both samples               |
| Draw order (priority) 24 is standard for raster basemaps | **Medium** | Both samples agree, but other values may work           |
| Parameters `1 4 36 1` are encoding settings              | **Low**    | Inferred; exact meaning uncertain                       |
| Zoom values [84,83,2,1,0] represent resolution levels    | **Medium** | Pattern is clear but exact mapping needs verification   |
