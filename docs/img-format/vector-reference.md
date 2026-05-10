# Vector IMG Format Reference

This page documents the Garmin **vector** IMG format for reference and comparison. Vector maps use the same container structure as raster maps but have fundamentally different internal data formats. cartoload currently only generates raster IMG files.

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

**Raster maps use the same TRE2 subdivision record structure** as vector maps (16-byte for non-last levels, 14-byte for last level), but with different object type flags and a focus on raster tile assignment rather than vector elements.

Our implementation generates spatial subdivisions using a geographic grid with tile-derived bounds:

1. **Grid computation:** For each zoom level, `grid_side = max(2, int(n_tiles**0.25))` determines the grid dimensions
2. **Tile assignment:** Each tile is assigned to a grid cell based on its center position
3. **Subdivision bounds:** Computed from the min/max of assigned tiles' geographic bounds (not grid cell boundaries)
4. **Subdivision center:** Computed from the midpoint of the tile-derived bounds (not grid cell center) — this minimizes delta magnitudes for header and bitstream encoding
5. **Empty cells:** Skipped (no subdivision created)
6. **Width/height encoding:** Uses shift = `max(0, 24 - level_number)` with `((2*(center - bound) + 1)//2 + mask) >> shift`
7. **has_children flag:** Bit 15 of width field set for all non-last levels

The level_number values are remapped to `24-N+1..24` to ensure coordinate precision exceeds tile size (see [TRE1 Map Levels](tre-sections.md#52-tre1--map-levels-zoom-level-table)).

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
Raster maps use 273-byte TRE headers (seen in reference files) — a newer extended format not documented in the 2005 Mechalas spec.

LBL header variants (vector): 170, 196, 208, 236 bytes.
Raster maps use 596-byte LBL headers.


## 11. Implementation Files

| File                                           | Purpose                                           |
| ---------------------------------------------- | ------------------------------------------------- |
| `src/cartoload/exporters/garmin_img_model.py`  | Data model (dataclasses for IMG structure)        |
| `src/cartoload/exporters/garmin_img_writer.py` | Binary writer (header, FAT, GMP container, tiles) |
| `src/cartoload/exporters/garmin_img.py`        | Exporter class (pipeline integration)             |
| `tests/test_exporter_garmin_img.py`            | Test suite (136 tests, all passing)               |
| `src/cartoload/analysis/img_parser.py`        | IMG binary parser (FAT, GMP, TRE, RGN, LBL)      |
| `src/cartoload/analysis/img_export.py`         | GeoTIFF export tool for visual validation          |

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

Official Garmin maps (like Garmin professional maps) combine raster and vector data in a single IMG file. Understanding which sections are shared vs. format-specific is key to implementing hybrid maps.

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
- Single-map reference: single_map_west.img (1,495,072,768 bytes / 1.4 GB)
- Single-map reference: single_map_east.img (1,421,049,856 bytes / 1.4 GB)
- GMapTool (gmt) v0.8.220.853b output
- QMapShack wiki — Alex Whiter's raster IMG analysis (IOM subfile 00355951)
- mkgmap source code (`uk.me.parabola.imgfmt` package)
- Hexadecimal dumps of headers and GMP container sections
- `cartoload analyze img info` — built-in CLI for inspecting IMG files with FAT chain traversal and GMP-relative offset parsing
- Willink/Pinns "Exploring Garmin's IMG Format" (2015) — see `expl_img2015.pdf` in this directory
- GPXSee source code (`/home/tobias/git/tmp/GPXSee/src/map/IMG/`) — C++ reference parser for TRE/RGN/LBL files, critical for understanding RGN2 segment boundaries and raster type decoding
- mkgmap source code (`/home/tobias/git/tmp/mkgmap-r4924`) — Java reference implementation for IMG writing (vector-focused but core format logic applies)
- **Device tested:** Garmin Fenix 6 (confirmed working with reference files)

**Last updated:** 2026-05-09
