## ADDED Requirements

### Requirement: IMG header structure documentation

The format specification at `docs/exporters/garmin-img.md` SHALL document the Garmin raster `.img` file header structure, including: the magic bytes/signature, format version, creation date, data size, block size (typically 512 bytes), and the File Allocation Table (FAT) layout including FAT page size, number of FAT pages, and how subfile block pointers are stored.

#### Scenario: Header fields are fully documented

- **WHEN** a developer reads the IMG header section of `docs/exporters/garmin-img.md`
- **THEN** every field in the first 512-byte header block is documented with byte offset, length, data type, and valid values, cross-referenced against `gmt -i -v` output from real `.img` files

#### Scenario: FAT structure is explained

- **WHEN** a developer reads the FAT section
- **THEN** the document explains how the FAT maps logical block numbers to physical file offsets, how many FAT pages exist, and how to traverse the FAT chain to locate a subfile's data blocks

### Requirement: Subfile organization documentation

The format specification SHALL document how a raster `.img` file organizes its content into subfiles, including: the subfile header table (typically at a fixed offset after the main header), subfile types (MAP, RGN, TRE, LBL, GMP, TYP, and raster-specific types like MDR), naming conventions, and how each subfile's blocks are chained via the FAT.

#### Scenario: All subfile types are enumerated

- **WHEN** a developer reads the subfile organization section
- **THEN** the document lists every subfile type found in raster `.img` files, describes the purpose of each, and notes which types are required vs. optional for raster maps

#### Scenario: Subfile block chaining is documented

- **WHEN** a developer reads the subfile chaining section
- **THEN** the document explains how to read a subfile's start block from its header, follow the FAT chain, and reconstruct the subfile's contiguous data from non-contiguous blocks

### Requirement: Tile grid layout documentation

The format specification SHALL document how raster tile data is organized within the IMG container, including: the tile index structure, tile coordinate encoding (how lat/lon bounds map to tile numbers), tile data block format (compressed vs. uncompressed), the 3.5 MB per-tile-cell limit, and how tiles reference their pixel data.

#### Scenario: Tile index can be reconstructed

- **WHEN** a developer reads the tile grid section
- **THEN** the document provides enough detail to parse the tile index, determine how many tiles exist, and locate each tile's pixel data within the file

#### Scenario: Tile cell size limit is documented

- **WHEN** a developer reads the size constraints section
- **THEN** the 3.5 MB per-tile-cell limit is documented with its exact byte value, and the implications for tile dimensions at various zoom levels are explained

### Requirement: Zoom level encoding documentation

The format specification SHALL document how multi-resolution pyramid zoom levels are encoded, including: the zoom level table structure, how each level references its tile subset, the relationship between zoom level numbers and pixel resolution, and how the multi-resolution pyramid is built (coarse levels from fewer tiles, fine levels from more tiles).

#### Scenario: Zoom level table can be parsed

- **WHEN** a developer reads the zoom level section
- **THEN** the document describes the byte layout of the zoom level table, how to determine the number of zoom levels, and how each level's tile range is specified

#### Scenario: Resolution mapping is documented

- **WHEN** a developer reads the resolution mapping section
- **THEN** the document maps zoom level numbers to approximate ground resolution (meters per pixel) and explains how this relates to the tile grid dimensions at each level

### Requirement: Draw order documentation

The format specification SHALL document the draw order mechanism used to control which map layers appear on top when multiple `.img` files are loaded on a Garmin device, including: the draw order field location, valid value ranges, and recommended values for raster basemaps vs. overlay layers.

#### Scenario: Draw order values are explained

- **WHEN** a developer reads the draw order section
- **THEN** the document explains which byte(s) control draw order, the numeric range, and provides guidance on choosing values that ensure raster basemaps render below vector overlays

### Requirement: Attribution fields documentation

The format specification SHALL document any attribution or metadata fields within the IMG container, including: map name, map description, copyright strings, and any other text fields that appear on the Garmin device.

#### Scenario: Attribution strings are located and documented

- **WHEN** a developer reads the attribution section
- **THEN** the document identifies where map name, description, and copyright strings are stored, their maximum lengths, character encoding, and how they appear to the end user on a Garmin device

### Requirement: Size constraints documentation

The format specification SHALL document all known size constraints and limits, including: the 4 GB maximum file size, the 3.5 MB per-tile-cell limit, maximum number of tiles per subfile, maximum number of subfiles, maximum number of zoom levels, and any block count or FAT size limits.

#### Scenario: All size limits are enumerated

- **WHEN** a developer reads the size constraints section
- **THEN** the document provides a table of every known size limit with its exact value, source (observed vs. documented), and practical implications for map creation

#### Scenario: File splitting strategy is documented

- **WHEN** a developer reads the file splitting section
- **THEN** the document explains when a single map must be split into multiple `.img` files and how the split affects the tile grid and zoom level structure

### Requirement: Python data model for IMG structures

The file `src/cartoload/exporters/garmin_img_model.py` SHALL define Python dataclasses representing all documented IMG structures, including: `IMGHeader` (magic, version, date, size, block size, FAT info), `SubfileHeader` (type, name, size, start block), `TileRecord` (tile coordinates, data offset, data length), `ZoomLevel` (level number, resolution, tile range), `DrawOrderEntry` (value, layer type), and `IMGFile` as a top-level container aggregating all sub-structures.

#### Scenario: Dataclasses capture all header fields

- **WHEN** a developer instantiates `IMGHeader` from raw bytes parsed via `gmt -i -v` output
- **THEN** every field from the output maps to a typed dataclass attribute with appropriate Python types (int, str, datetime, bytes)

#### Scenario: IMGFile aggregates all sub-structures

- **WHEN** a developer creates an `IMGFile` instance
- **THEN** it contains an `IMGHeader`, a list of `SubfileHeader` instances, a list of `TileRecord` instances, a list of `ZoomLevel` instances, and a `DrawOrderEntry`, providing a complete in-memory representation of the `.img` file structure

### Requirement: Data model validation against real files

The data model SHALL be validated by parsing `gmt -i -v` output from real swisstopo `.img` files and confirming that every field reported by `gmt` is represented in the corresponding dataclass, and that the parsed values match the raw output.

#### Scenario: Validation passes for ch_basemap_25k

- **WHEN** `gmt -i -v` output for a swisstopo ch_basemap_25k `.img` file is parsed into the data model
- **THEN** all header fields, subfile entries, tile records, zoom levels, and draw order values are captured without errors, and the values match the raw `gmt` output

#### Scenario: Validation passes for ch_basemap_10k

- **WHEN** `gmt -i -v` output for a swisstopo ch_basemap_10k `.img` file is parsed into the data model
- **THEN** all fields are captured and match, confirming the model works across different map scales
