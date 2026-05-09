# Garmin IMG Format Resources and Tools

This document provides a curated list of resources, tools, libraries, and documentation for working with Garmin IMG files, including both vector and raster formats.

## Existing Tools for Creating Garmin IMG Files

### Vector Map Creation Tools

#### 1. mkgmap (Open Source)

- **Purpose:** Converts OpenStreetMap (OSM) data to Garmin IMG format
- **Type:** Command-line tool, Java-based
- **License:** GPL
- **Homepage:** <http://www.mkgmap.org.uk/>
- **Repository:** <https://svn.mkgmap.org.uk/mkgmap/>
- **Use Case:** Creating vector maps from OSM data for Garmin devices
- **Capabilities:**
  - Reads OSM XML/PBF files
  - Generates routable vector maps
  - Supports custom styles and type files
  - Can create multi-tile maps
  - Actively maintained by OSM community
- **Limitations:** Vector-only, does not support raster tiles

**Key Features:**

- Style customization for map rendering
- Address search support
- Multiple language support
- Turn-by-turn navigation data

#### 2. cGPSmapper (Commercial/Freeware)

- **Developer:** Stanislaw Kozicki
- **Type:** Command-line compiler
- **License:** Freeware for personal use, commercial license available
- **Website:** <http://cgpsmapper.com/>
- **Use Case:** Compiling Polish (.mp) format files to Garmin IMG
- **Capabilities:**
  - Creates vector maps from Polish text format
  - Supports custom TYP files for styling
  - Can generate routable maps
  - Well-documented format specifications
- **Format:** Uses Polish (.mp) text-based intermediate format
- **Status:** Mature, stable, but updates are infrequent

**Polish Format (.mp):**

- Human-readable text format
- Defines points, polylines, polygons
- Header sections for metadata
- Widely documented and reverse-engineered

#### 3. GPSMapEdit (Commercial)

- **Type:** GUI map editor
- **License:** Commercial (paid)
- **Website:** <http://www.gpsmaped.com/>
- **Use Case:** Visual map editing and IMG creation
- **Capabilities:**
  - Graphical map editor
  - Exports to cGPSmapper format (.mp)
  - Can import various GIS formats
  - Type file (.TYP) editor included
- **Workflow:** Edit visually → Export to .mp → Compile with cGPSmapper

#### 4. splitter (OSM Tool)

- **Purpose:** Splits large OSM datasets into tiles for mkgmap
- **Type:** Command-line tool, Java-based
- **License:** GPL
- **Use Case:** Pre-processing large OSM extracts before mkgmap compilation
- **Repository:** <https://svn.mkgmap.org.uk/splitter/>

### Raster Map Creation Tools

#### 5. GMapTool (gmt)

- **Purpose:** IMG file inspection, manipulation, and basic creation
- **Type:** GUI and command-line tool
- **License:** Freeware
- **Website:** <http://www.gmaptool.eu/>
- **Use Case:** Analyzing existing IMG files, merging maps, basic operations
- **Capabilities:**
  - Detailed IMG file inspection (header, subfiles, metadata)
  - Map splitting and merging
  - Limited raster map support
  - Can extract subfiles and tiles
- **Limitations:** Primarily a reader/inspector, not a full writer

**Note:** GMapTool was used to analyze the SwissTopo samples in this project.

#### 6. JNX2IMG / IMG2JNX

- **Purpose:** Convert between Garmin's JNX and IMG raster formats
- **Type:** Command-line utilities
- **Use Case:** Converting raster maps between formats
- **Note:** JNX is Garmin's modern raster format (BirdsEye), simpler than IMG
- **Availability:** Various third-party implementations

**JNX Format:**

- Simpler raster format than IMG
- JPEG tiles with metadata
- Better documented
- Preferred for modern Garmin devices (BirdsEye compatible)

#### 7. Mobile Atlas Creator (MOBAC)

- **Purpose:** Download and bundle map tiles from online sources
- **Type:** Java GUI application
- **License:** GPL
- **Repository:** <https://sourceforge.net/projects/mobac/>
- **Capabilities:**
  - Downloads tiles from OpenStreetMap, Google, Bing, etc.
  - Exports to multiple formats including Garmin Custom Maps (KMZ)
  - Does NOT export to IMG raster format directly
- **Workflow:** MOBAC → KMZ → Manual conversion to IMG (complex)

#### 8. Global Mapper (Commercial)

- **Type:** Full-featured GIS application
- **License:** Commercial (expensive)
- **Website:** <https://www.bluemarblegeo.com/global-mapper/>
- **Capabilities:**
  - Import raster imagery from many formats
  - Export to Garmin Custom Maps (KMZ)
  - Can export to JNX format
  - No direct IMG raster export
- **Use Case:** Professional GIS workflows

### Map Analysis and Inspection Tools

#### 9. GPXSee (Open Source)

- **Purpose:** GPS data viewer with full Garmin IMG parser
- **Type:** Desktop application (C++/Qt)
- **License:** GPL
- **Repository:** <https://github.com/tumic0/GPXSee>
- **Use Case:** Reference implementation for reading Garmin IMG files (both vector and raster)
- **Capabilities:**
  - Full TRE/RGN/LBL/NET parser with extended raster support
  - Raster tile extraction and display from IMG files
  - TRE7 segment boundary parsing for per-subdivision RGN2 data
  - LBL28/LBL29 image index and JPEG retrieval
- **Value for this project:**
  - Primary reference for understanding how devices parse RGN2 raster data
  - Confirmed polyline preamble type: `0x06/0xB3` → `type = 0x10613` (raster)
  - Documents TRE7 `_flags` field semantics (bits 0-2: polygon/line/point offsets)
  - Shows complete parsing chain: TRE7 → extPolygonsOffset → extPolyObjects → readRasterInfo → E0 record
- **Key source files:**
  - `src/map/IMG/rgnfile.cpp` — RGN2 parsing, raster info reading
  - `src/map/IMG/trefile.cpp` — TRE7 entry reading, subdivision initialization
  - `src/map/IMG/lblfile.cpp` — LBL28 raster table loading, JPEG retrieval
  - `src/map/IMG/style_img.h` — `isRaster()` type check (`type == 0x10613`)

#### 10. imgdecode

- **Purpose:** Decode and inspect IMG file structures
- **Type:** Command-line tool
- **Use Case:** Reverse-engineering IMG format, debugging
- **Availability:** Various open-source implementations on GitHub

#### 10a. SasPlanet (Open Source)

- **Purpose:** Satellite imagery viewer and map tile downloader with Garmin IMG export
- **Type:** Desktop application (Delphi/Pascal)
- **License:** GPL
- **Repository:** <https://github.com/sasgis/sas.planet.src>
- **Use Case:** Understanding the MTX intermediate format used for raster IMG creation
- **Key findings from source analysis:**
  - SasPlanet does **NOT** write binary IMG directly — it generates MTX text files compiled by proprietary `bld_gmap32.exe`
  - MTX format includes map format (MF=2, MG=1 for OF_GMP), map series 36 (GB Discoverer)
  - Feature types: polyline=23670 (0x5C56), polygon=20122 (0x4E9A)
  - Two submap architecture: Fine (zooms ≤7) + Coarse (zooms >7), compiled separately then joined by `gmt.exe`
  - Fixed generalization levels table mapping zoom levels to scale values
- **Value for this project:** Understanding how commercial tools organize raster data (submap splitting, zoom level mappings, feature type assignments), but not directly usable as binary reference since output goes through `bld_gmap32.exe`
- **Key source files:**
  - `Src/RegionProcess/Export/IMG/u_ExportTaskToIMG.pas` — MTX file generation and external tool invocation
  - `Src/RegionProcess/Export/IMG/t_ExportToIMGTask.pas` — Data structures and format definitions

#### 11. img2gps

- **Purpose:** Extract GPS data and metadata from IMG files
- **Type:** Parser/extractor
- **Use Case:** Reading IMG files programmatically

## Programming Libraries and Code

### Python Libraries

#### 1. garmin_img_parser (Various GitHub Projects)

- **Type:** Python parsers for reading IMG files
- **Status:** Scattered, incomplete implementations
- **Notable Projects:**
  - Various reverse-engineering attempts
  - Mostly read-only parsers
  - No comprehensive write support found

**Search Strategy:**

- GitHub search: `language:python garmin img file`
- Most projects are abandoned or incomplete
- Focus on reading/parsing, not writing

#### 2. Python + mkgmap Wrapper Approach

- **Strategy:** Use Python to generate Polish (.mp) format, then call mkgmap
- **Advantages:**
  - Polish format is text-based and well-documented
  - Leverage mature mkgmap compiler
  - Good for vector maps
- **Disadvantages:**
  - Requires Java runtime for mkgmap
  - Two-step process
  - Vector-only

### Java Libraries

#### 1. mkgmap Source Code

- **Repository:** <https://svn.mkgmap.org.uk/mkgmap/>
- **Language:** Java
- **Value:** Reference implementation for IMG writing
- **Key Classes:**
  - `uk.me.parabola.imgfmt` - IMG format handling
  - File structure writers
  - FAT management
  - Subfile generation

**Learning Resource:**

- Study mkgmap source to understand IMG writing
- Well-structured, mature codebase
- Vector-focused but contains core IMG format logic

### C/C++ Tools

#### 1. cGPSmapper Source Insights

- **Status:** Closed-source
- **Value:** Documentation and Polish format specs provide insights
- **Alternative:** Use cGPSmapper as external tool from Python (subprocess)

## Format Documentation and Specifications

### Official Documentation

- **Garmin:** No official public IMG format specification
- **Reverse-engineered:** All tools based on reverse engineering

### Comprehensive Format Specification

#### Herbert Oppmann Garmin IMG Format Documents (Local)

- **Files:**
  - `docs/exporters/Garmin_IMG_Format.pdf` — Container format specification
  - `docs/exporters/Garmin_IMG_Subfiles_Format.pdf` — Subfile format specification
- **Author:** Herbert Oppmann (memotech.franken.de)
- **Source:** <https://www.memotech.franken.de/FileFormats/#GarminIMG>
- **Dates:** 2024-08-31 (Container), 2023-09-05 (Subfiles)
- **Coverage:** Authoritative reverse-engineered specification for both container and subfile formats
- **Content (Container):**
  - Boot sector / IMG header layout with XOR encryption
  - FAT block structure and subfile chain traversal
  - GMP container format with section table
- **Content (Subfiles):**
  - TRE header with all section descriptors (TRE1-TRE10)
  - TRE Section 1 (Map levels): zoom_code encoding (bit 7=inherited, bits 3-0=level), bits_per_coordinate
  - TRE Section 2 (Subdivisions): uint32 with flag bits 31-28 (has-polygons/lines/points), width bit 15 = end of chain, next_level as 1-based index
  - TRE Section 7 (Extended type offsets): variable record format with flag byte
  - RGN header: 125-byte format with section 1-5 descriptors and local flag bitmasks
  - GMP format: all offsets are GMP-relative, not subfile-relative
- **Importance:** Most up-to-date and accurate specification available. Corrects several ambiguities in the Mechalas and Willink documents. The TRE2 subdivision field descriptions (uint32 with flag bits, 1-based next_level, end-of-chain bit semantics) are authoritative.

#### John Mechalas IMG Format Specification (Local)

- **File:** `docs/exporters/imgformat-1.0.pdf` (included in repository)
- **Author:** John Mechalas
- **Date:** 29 October 2005
- **Coverage:** The most comprehensive reverse-engineered specification for the Garmin IMG format
- **Content:**
  - Complete IMG header field layout with byte offsets
  - FAT block format and chain traversal
  - Sub-file format (common header + type-specific headers)
  - TRE sub-file: bounds, map levels, subdivision definitions, overview sections
  - LBL sub-file: label encoding (6-bit, 8-bit, 10-bit), country/region/city/POI/zip records
  - RGN sub-file: data segment layout, point/polyline/polygon structures, coordinate delta encoding
  - NET sub-file: road definitions and routing data
  - Coordinate system: 3-byte signed map units (degrees × 2^24 / 360)
  - Subdivision hierarchy and pointer chains
- **Important notes:**
  - Documents the **vector** IMG format only. Raster maps use the same container structure (header, FAT, GMP) but different subdivision and RGN data formats.
  - TRE header lengths documented: 116, 120, 154, 188 bytes (raster maps use 273 bytes — newer extended format)
  - LBL header lengths documented: 170, 196, 208, 236 bytes (raster maps use 596 bytes)
  - Label encoding (6/8/10-bit) is vector-only; raster maps use plain ASCII for tile filenames

#### Willink/Pinns "Exploring Garmin's IMG Format" (Local)

- **File:** `docs/exporters/expl_img2015.pdf` (included in repository)
- **Author:** N. Willink
- **Date:** Latest revision 02/03/2015 (original 21/08/2011)
- **Source:** <https://www.pinns.co.uk/osm/docs/expl_img2015.pdf>
- **Coverage:** Practical guide to parsing Garmin vector IMG format internals, complementing the Mechalas specification
- **Content:**
  - RGN sub-file: detailed subdivision pointer structure, POI/polyline/polygon data layout
  - Map levels and subdivision grouping — how zoom levels map to groups of subdivisions
  - TRE subdivision format: 14-byte (lowest level) and 16-byte records, object type codes
  - LBL label encoding: 6-bit character encoding with MSB-first bit packing, symbol codes
  - NET sub-file: highway definitions, multi-label entries (up to 4 labels per highway)
  - NOD sub-file: routing node format, direction coordinates, Tables A/B structure
  - DEM sub-file: digital elevation model data
  - Extended types (0x100+): POIs in RGN4, polylines in RGN3, polygons in RGN2
  - Coordinate bitstream encoding: variable bits-per-coordinate, left-shifting
  - Locked TOPO map handling and XOR decryption
- **Important notes:**
  - Vector format only — no raster IMG coverage
  - Corrects several errors in the Mechalas spec (e.g., POI subtype bit location)
  - Includes practical parsing examples with hex dumps
  - Covers TRE7, TRE8, TRE9 sections (undocumented in Mechalas)

### Community Documentation

#### 1. QMapShack Wiki - Raster IMG Format

- **URL:** <https://github.com/Maproom/qmapshack/wiki/RasterImg_AWhiter>
- **Author:** Alex Whiter
- **Content:**
  - **Raster-specific IMG format documentation** - the most comprehensive community resource
  - Complete TRE header layout for raster maps (273-byte format) with verified byte offsets
  - RGN Type E0 record format for raster tile metadata
  - LBL28 (Image Index) and LBL29 (Image Storage) section structure
  - RGN2 compound record format (0D/06/BC/DE/E0 markers)
  - TRE7 raster layer section with offset table format
  - TRE8 object type parameter entries
  - Binary format details with byte offsets and field descriptions
  - **Critical discovery:** Section positions in TRE header are GMP-relative, not TRE-relative
  - Analysis based on IOM subfile 00355951 (Isle of Man, OS Map)
- **Importance:** This is the authoritative community documentation for raster IMG files. Official Garmin documentation does not exist for this format.
- **Verification:** All findings cross-validated against IOM.img and SwissTopo_West.img using `cartoload analyze img info`

#### 2. OpenStreetMap Wiki

- **URL:** <https://wiki.openstreetmap.org/wiki/OSM_Map_On_Garmin>
- **Content:**
  - Garmin map creation workflows
  - mkgmap tutorials
  - Polish format documentation
  - Style file references

#### 3. cGPSmapper Manual

- **URL:** <http://cgpsmapper.com/en/download.htm>
- **Content:**
  - Polish (.mp) format specification
  - Map ID and metadata requirements
  - Type file (.TYP) format
  - Compilation parameters

#### 4. IMG Format Reverse Engineering Projects

- **cGPSmapper Polish Format:** Well-documented intermediate format
- **mkgmap Wiki:** Technical details on IMG structure
- **Various GitHub Projects:** Incomplete but useful parsers

#### 5. Garmin Developer Forums (Historical)

- **Note:** Limited official information
- **Community Knowledge:** Scattered across forums, mailing lists

### Reference Files

#### IOM.img (Isle of Man, Multi-Map Raster)

- **File:** `tests/data/garmin_samples/IOM.img` (33,462,272 bytes / 31.9 MB)
- **Source:** OS Map - Isle of Man, Garmin format
- **Format:** Multi-map raster IMG with 51 GMP subfiles + 1 MPS
- **Block size:** 2,048 bytes
- **Analysis subfile:** 00355951 — fully parsed and validated against QMapShack wiki
- **Key characteristics:**
  - 8 zoom levels per subfile (level 0x87 to 0x00, zoom 17-24)
  - TRE7 with rec_size=4 (simple uint32 offsets)
  - TRE8 with 2 entries (raster tiles + DATA_BOUNDS)
  - RGN5 present (112 bytes)
  - No NET section
  - bits_field=0x2B (1-byte image index, <256 tiles per subfile)

#### SwissTopo_West.img (Single-Map Raster)

- **File:** Available as reference, ~1.4 GB
- **Source:** SwissTopo professional topographic map
- **Format:** Single-map raster IMG with 1 GMP subfile + 1 MPS
- **Block size:** 32,768 bytes
- **Key characteristics:**
  - 5 zoom levels (level 0x84 to 0x00, zoom 20-24)
  - 32,443 tiles covering western Switzerland
  - TRE7 with rec_size=5 (uint32 offset + 1 byte flag)
  - TRE8 with 1 entry (raster tiles only)
  - RGN5 absent (size=0)
  - NET section present
  - bits_field=0x2D (2-byte image index, SwissTopo variant)

### Analysis Tools

#### cartoload analyze (Built-in)

The project includes a built-in CLI for inspecting and comparing Garmin IMG binary files. See [CLI Reference](../cli.md) for full documentation.

```bash
# Concise summary (bounds, bitmaps, encoding, map name)
cartoload analyze img info <img_file> -m

# Full analysis (TRE, RGN, LBL, NET sections)
cartoload analyze img info <img_file>

# Show a specific section (e.g. TRE7, RGN2)
cartoload analyze img info <img_file> --section TRE7

# Show all entries (no truncation)
cartoload analyze img info <img_file> --section TRE2 --limit 0

# Annotated RGN2 analysis (raster tile records per zoom level)
cartoload analyze img info <img_file> -r

# TRE7-based zoom level segmentation
cartoload analyze img info <img_file> -g

# Hex dump of a section
cartoload analyze img info <img_file> -x rgn2

# Side-by-side comparison of two IMG files
cartoload analyze img compare <file1> <file2>
```

**Capabilities:**
- Parse GMP container headers and compute section offsets
- FAT chain traversal for multi-part subfiles
- GMP-relative offset parsing (correct interpretation of TRE/RGN/LBL section positions)
- TRE1/TRE2/TRE7/TRE8 data extraction and formatting
- RGN2 compound record parsing (0D/06/BC/DE/E0 markers)
- LBL label extraction
- Bitmap tile statistics from RGN2 E0 records
- Hex dump output for any section
- Colored output with Rich (auto-disabled when piped)
- Spinner for large files (>200 MB)

## Raster vs Vector IMG Files: Key Differences

### Vector IMG Files

- **Structure:**
  - TRE (Tree): Spatial index
  - RGN (Region): Vector geometry
  - LBL (Label): Text labels
  - NET (Network): Routing data (optional)
  - TYP (Type): Custom styles (optional)
- **Tools:** mkgmap, cGPSmapper, GPSMapEdit
- **Well-supported:** Extensive tooling and documentation

### Raster IMG Files

- **Structure:**
  - GMP (Garmin Map): Tile data, zoom levels, indices
  - MPS (MapSource): Metadata
- **Tools:** Very limited
  - GMapTool (inspection only)
  - JNX format preferred for raster
  - No comprehensive open-source writer found
- **Status:** Poorly documented, minimal tooling

**Key Finding:** Raster IMG format has very limited tool support compared to vector format.

### Hybrid Raster/Vector IMG Files

Garmin's professional maps (like SwissTopo Pro) combine both raster and vector data in a single IMG file:

**Structure:**

- **Raster subfile (GMP):** Contains topographic background imagery as JPEG tiles
  - Provides detailed terrain visualization
  - Shows elevation shading, land cover, etc.
  - Multiple zoom levels for different scales

- **Vector subfiles (TRE, RGN, LBL, NET):** Contains searchable, routable data
  - Roads, trails, and paths
  - Points of interest (POIs)
  - Labels and place names
  - Routing network for navigation

**Advantages of Hybrid Approach:**

- Best of both worlds: photorealistic terrain + searchable/routable features
- Single file deployment (easier to manage than separate files)
- Device displays raster as base layer with vector overlays on top
- Vector features remain interactive (searchable, clickable)
- Reduced file size vs. pure raster (vectors compress better for linear features)

**Creating Hybrid Maps:**

1. Generate raster IMG with GMP subfile (topographic imagery)
2. Generate vector IMG with TRE/RGN/LBL/NET subfiles (roads, POIs) using mkgmap
3. Combine both sets of subfiles into single IMG file
4. Ensure proper draw order (raster priority < vector priority for proper layering)

**Tools for Hybrid Creation:**

- **GMapTool:** Can merge multiple IMG files (combine raster + vector)
- **Custom approach:** Write both raster and vector subfiles in same IMG
- **mkgmap limitation:** Does NOT support adding raster tiles, vector only

**Note:** This is an advanced use case requiring both raster and vector IMG generation capabilities.

## Device Compatibility and Format Support

### Garmin Device Categories and Supported Formats

#### Fenix Watches (Fenix 6, 7, 8, Epix, etc.)

- **Supported:**
  - Vector IMG maps (TopoActive, OpenStreetMap-based)
  - **Raster IMG maps** ✅ (confirmed working on Fenix 6+)
  - **Hybrid raster/vector IMG maps** ✅ (like official Garmin SwissTopo Pro)
- **NOT Supported:**
  - JNX/BirdsEye raster maps (handheld GPS only)
  - Custom Maps (KMZ format)
- **Important:** Official Garmin SwissTopo maps use **hybrid approach**: raster background imagery (topographic detail) combined with vector overlays (roads, trails, POIs, labels) in the same IMG file
- **Recommendation:** Raster IMG format DOES work on Fenix watches (user-confirmed), making it suitable for custom topo maps

#### Handheld GPS Units (GPSMap 66, Montana 700, Oregon 750, etc.)

- **Supported:**
  - Vector IMG maps (routable maps)
  - Raster IMG maps (legacy support)
  - JNX/BirdsEye raster maps
  - Custom Maps (KMZ) - limited to 100 tiles
- **Best for raster:** JNX format (simpler, better documented)
- **Best for vector:** IMG format with routing data

#### Automotive GPS (Drive, DriveSmart, Dezl series)

- **Supported:** Primarily vector IMG maps with routing
- **Raster support:** Limited or none on modern models

#### Aviation/Marine Units (G3X, GPSMAP 8600, etc.)

- **Supported:** Varies by model, typically vector IMG
- **Raster support:** Some models support custom raster overlays

### Format Compatibility Summary Table

| Format                     | Fenix Watches | Handheld GPS            | Auto GPS   | Aviation/Marine |
| -------------------------- | ------------- | ----------------------- | ---------- | --------------- |
| Vector IMG                 | ✅ Yes        | ✅ Yes                  | ✅ Yes     | ✅ Yes          |
| Raster IMG                 | ✅ Yes        | ✅ Yes                  | ⚠️ Limited | ⚠️ Varies       |
| Hybrid IMG (Raster+Vector) | ✅ Yes        | ✅ Yes                  | ⚠️ Limited | ⚠️ Varies       |
| JNX (BirdsEye)             | ❌ No         | ✅ Yes                  | ❌ No      | ⚠️ Some models  |
| KMZ (Custom Maps)          | ❌ No         | ✅ Yes (100 tile limit) | ❌ No      | ⚠️ Some models  |

**Key Insight for This Project:** Raster IMG format works on both **Fenix watches and handheld GPS units**. Official Garmin SwissTopo maps demonstrate that hybrid raster/vector IMG files (raster topography + vector roads/labels) work perfectly on Fenix devices.

## Alternative Raster Formats for Garmin

### 1. JNX Format (BirdsEye)

- **Advantages:**
  - Simpler structure than IMG
  - Better documented
  - Supported on handheld GPS devices (GPSMap, Montana, Oregon series)
  - Third-party tools available
- **Disadvantages:**
  - **NOT supported on Garmin watches** (Fenix, Epix, etc.)
  - Limited to specific device families (primarily handheld GPS units)
  - Requires BirdsEye subscription on some devices
  - Newer format, not universally compatible

**Important for Fenix Watches:** JNX format does NOT work on Fenix series watches (6, 7, 8, etc.). These watches support **vector IMG maps** and **raster IMG maps** (confirmed: SwissTopo raster IMG files load correctly on Fenix 6+). JNX is not supported.

### 2. KMZ (Garmin Custom Maps)

- **Advantages:**
  - Simple: ZIP archive with JPEG tiles + KML metadata
  - Well-documented (Google KML standard)
  - Supported on modern Garmin devices
  - Easy to create programmatically
- **Disadvantages:**
  - Limited to 100 tiles per KMZ
  - Lower zoom level support
  - Not suitable for large-scale maps

**Recommendation:** Consider JNX or KMZ for raster maps unless IMG is specifically required for legacy device support.

## Approaches for Writing Garmin Raster IMG Files

### Approach 1: Direct Binary Writing (This Project)

**Strategy:** Write IMG format directly from Python

- **Advantages:**
  - Full control over output
  - No external dependencies
  - Can optimize for specific use cases
- **Challenges:**
  - IMG format is complex and poorly documented
  - Raster variant has minimal reference implementations
  - Requires extensive reverse-engineering
- **Status:** Feasible but requires significant development effort

**Prerequisites:**

1. Complete format specification (in progress)
2. Python data model (completed)
3. Binary writer implementation
4. FAT and subfile management
5. Tile compression and encoding
6. Extensive testing with real devices

### Approach 2: Generate JNX Instead

**Strategy:** Target JNX format as simpler alternative

- **Advantages:**
  - Simpler format
  - Better documented
  - Modern device support
- **Disadvantages:**
  - Doesn't fulfill IMG requirement
  - May not work on older devices

### Approach 3: Hybrid - Use Existing Tools

**Strategy:** Leverage GMapTool or other tools as subprocess

- **Advantages:**
  - Avoid reimplementing complex format
- **Disadvantages:**
  - GMapTool has limited raster creation support
  - Dependency on external binaries
  - Less portable

### Approach 4: Study mkgmap and Adapt

**Strategy:** Port relevant mkgmap Java code to Python

- **Advantages:**
  - Proven implementation
  - Well-tested FAT and header logic
- **Challenges:**
  - mkgmap is vector-focused
  - Significant code to port
  - Different language paradigms

## Recommendations for This Project

### Short-term: Complete Raster IMG Implementation

1. **Format specification** — DONE
   - Complete GMP container format documented (TRE, RGN, LBL, NET sub-headers)
   - Tile storage as JPEG with uint32 index table verified against reference files
   - See `docs/exporters/garmin-img.md` for full specification

2. **Binary writer** — DONE
   - 512-byte header with checksum calculation
   - FAT management (special directory + subfile entries, multi-part support)
   - GMP container with all sub-headers (TRE 273B, RGN 125B, LBL 596B, NET 100B)
   - Tile encoding (NumPy → JPEG) and tile index table generation
   - GMT validation passes (exit code 0) for single and multi-tile files
   - See `src/cartoload/exporters/garmin_img_writer.py`

3. **Validation** — DONE
   - 136 unit tests (all passing)
   - GMapTool validation passes
   - Reference: `tests/test_exporter_garmin_img.py`

### Long-term: Hybrid Raster/Vector Maps

1. **Phase 1: Raster-only IMG** — DONE
   - Pure raster topographic maps
   - Works on Fenix 6+ and handheld GPS
   - GMT validation passes

2. **Phase 2: Hybrid IMG** (future enhancement)
   - Combine raster IMG (this project) with vector IMG (mkgmap)
   - Use GMapTool to merge files, or implement direct hybrid writing
   - Raster background + vector roads/trails/POIs
   - Matches official Garmin SwissTopo approach

3. **Optional: JNX format** as alternative output for handheld GPS
   - Simpler format, but doesn't work on Fenix watches
   - Consider only if handheld GPS is primary target

4. **Contribute to open-source** IMG tooling community
   - Document findings to help future developers
   - First open-source raster IMG writer

## Key Insights from Research

### Critical Findings

1. **Vector IMG ≠ Raster IMG**
   - Different subfile structures
   - Different tools
   - Vector has mature ecosystem, raster does not

2. **No Open-Source Raster IMG Writer Found** → **Now resolved**
   - This project implements the first known open-source Garmin raster IMG writer
   - GMP container format with TRE/RGN/LBL/NET sub-headers fully reverse-engineered
   - JPEG tile storage with uint32 index table verified against reference files

3. **GMapTool is Primary Reference**
   - Best inspection tool
   - Limited creation capabilities
   - Our SwissTopo analysis used this tool

4. **mkgmap is Best Code Reference**
   - Even though it's vector-focused
   - Core IMG format handling is universal
   - FAT, header, subfile structure logic is applicable

5. **JNX is Preferred Raster Format**
   - Modern Garmin devices prefer JNX over raster IMG
   - Simpler to implement
   - Better documented

6. **IMG Raster is Legacy Format**
   - Still useful for older devices
   - swisstopo and other providers still distribute raster IMG
   - Filling a tooling gap has value

## References and Links

### Tools

- [mkgmap](http://www.mkgmap.org.uk/) - OSM to Garmin vector map converter
- [GMapTool](http://www.gmaptool.eu/) - IMG file inspector and manipulator
- [cGPSmapper](http://cgpsmapper.com/) - Polish format to IMG compiler
- [GPSMapEdit](http://www.gpsmaped.com/) - Commercial map editor
- [Mobile Atlas Creator](https://sourceforge.net/projects/mobac/) - Tile downloader and bundler

### Documentation

- [OSM Garmin Map Guide](https://wiki.openstreetmap.org/wiki/OSM_Map_On_Garmin) - Community wiki
- [cGPSmapper Manual](http://cgpsmapper.com/en/download.htm) - Format specifications
- [mkgmap Wiki](http://www.mkgmap.org.uk/doc/) - Technical documentation

### Code Repositories

- [mkgmap SVN](https://svn.mkgmap.org.uk/mkgmap/) - Reference implementation (Java)
- [splitter SVN](https://svn.mkgmap.org.uk/splitter/) - OSM data splitter
- [GPXSee GitHub](https://github.com/tumic0/GPXSee) - Reference IMG parser (C++/Qt), critical for RGN2 raster parsing
- [SasPlanet GitHub](https://github.com/sasgis/sas.planet.src) - MTX format reference (Delphi)

### Format Information

- Polish (.mp) format - Text-based intermediate format for cGPSmapper
- JNX format - Modern Garmin raster format (BirdsEye)
- KMZ format - Garmin Custom Maps (limited to 100 tiles)

### Community Resources

- OpenStreetMap forums and mailing lists
- Garmin developer community (limited official support)
- GitHub repositories (various incomplete parsers)

---

**Last Updated:** 2026-05-09
**Key Takeaway:** This project implements the first known open-source Garmin raster IMG writer, filling a significant gap in the GIS ecosystem. The GMP container format has been fully reverse-engineered, with GMapTool validation passing for generated files.
