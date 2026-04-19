## ADDED Requirements

### Requirement: IMG header writer
The `GarminImgExporter` SHALL write a valid IMG file header as the first structure in the output file. The header SHALL include the magic bytes, version field, creation timestamp, map name (used for attribution), and a FAT-like subfile directory. The header SHALL be written using the `IMGHeader` dataclass from `garmin_img_model.py`.

#### Scenario: Valid header structure
- **WHEN** the exporter writes an IMG header to a new file
- **THEN** the header begins with the correct magic bytes and version field as documented in `docs/exporters/garmin-img.md`
- **AND** the creation timestamp is set to the current UTC time
- **AND** the subfile directory contains entries for every subfile that will be written

#### Scenario: Header offsets are consistent
- **WHEN** the exporter finishes writing all subfiles
- **THEN** every offset in the header subfile directory points to the correct byte position in the file
- **AND** the total file size is consistent with the header's size field

### Requirement: Subfile writer
The exporter SHALL write one subfile per zoom level (or per split region). Each subfile SHALL contain a `SubfileHeader` (with tile dimensions, geographic bounds, and zoom level), followed by the encoded tile data blocks. Subfile structure SHALL conform to the format documented in `docs/exporters/garmin-img.md` and use the `SubfileHeader` dataclass from `garmin_img_model.py`.

#### Scenario: Subfile per zoom level
- **WHEN** the exporter processes a raster dataset with zoom levels 12, 13, and 14
- **THEN** it writes three subfiles, each with the corresponding zoom level in its header

#### Scenario: Subfile geographic bounds
- **WHEN** the exporter writes a subfile for a given zoom level
- **THEN** the subfile header contains the exact north, south, east, and west bounds in Garmin coordinate units (degrees multiplied by 2^31 / 180)
- **AND** the bounds match the geographic extent of the raster data for that zoom level

#### Scenario: Subfile data integrity
- **WHEN** a written `.img` file is inspected with `gmt -i -v`
- **THEN** every subfile is listed with correct type, size, and offset fields

### Requirement: Tile data encoder
The exporter SHALL encode each raster tile into the Garmin tile format. Tile encoding SHALL convert raw pixel data (from the processed GeoTIFF) into the bit-packed format required by the Garmin `.img` specification, including the tile header (with width, height, and colour depth) followed by the compressed pixel payload.

#### Scenario: Tile encoding produces valid output
- **WHEN** the encoder processes a 256x256 pixel tile from the raster dataset
- **THEN** the output is a byte sequence starting with the tile header (width=256, height=256, colour depth as configured)
- **AND** the pixel payload decodes back to the original tile data

#### Scenario: Tile encoding handles edge tiles
- **WHEN** the encoder processes a tile at the geographic boundary that is smaller than 256x256
- **THEN** the tile is padded or truncated according to the format specification and the tile header reflects the actual dimensions

### Requirement: Multi-resolution pyramid support
The exporter SHALL accept multiple zoom levels and produce a single `.img` file containing a tile pyramid — one subfile per zoom level, ordered from lowest to highest resolution. Each zoom level SHALL have its own tile grid covering the full geographic bounds of the raster dataset at that zoom level's tile size.

#### Scenario: Pyramid with multiple zoom levels
- **WHEN** the exporter receives a raster dataset with zoom levels [10, 11, 12, 13]
- **THEN** the output `.img` file contains four subfiles, one per zoom level
- **AND** zoom level 10 has the fewest tiles and zoom level 13 has the most
- **AND** all subfiles share the same geographic bounds

#### Scenario: Single zoom level
- **WHEN** the exporter receives a raster dataset with a single zoom level
- **THEN** the output `.img` file contains exactly one subfile for that zoom level

### Requirement: Attribution embedding
The exporter SHALL embed attribution text in the map name field of the IMG header. The attribution string SHALL come from the `LayerConfig.attribution` field (or fall back to the source attribution). The string SHALL be encoded in the format's character set (ASCII or the Garmin-specific extended character set as documented).

#### Scenario: Attribution from layer config
- **WHEN** the layer config specifies `attribution: "Swisstopo"`
- **THEN** the IMG header map name field contains "Swisstopo" and the attribution is visible when the map is loaded on a Garmin device

#### Scenario: Fallback to source attribution
- **WHEN** the layer config does not specify an attribution but the source config does
- **THEN** the IMG header uses the source config's attribution string

#### Scenario: Attribution length limit
- **WHEN** the attribution string exceeds the format's maximum length for the map name field
- **THEN** the string is truncated to fit within the limit and a warning is logged

### Requirement: 3.5 MB tile cell size limit
The exporter SHALL ensure that no single tile cell exceeds 3.5 MB (3,670,016 bytes). If a tile cell would exceed this limit, the exporter SHALL split the tile data across multiple subfile entries that share the same geographic bounds. The draw order table SHALL correctly reference all split entries.

#### Scenario: Tile within size limit
- **WHEN** a tile cell is 2.0 MB
- **THEN** the tile is written as a single entry without splitting

#### Scenario: Tile exceeds size limit
- **WHEN** a tile cell would be 4.2 MB
- **THEN** the exporter splits it into two subfile entries, each under 3.5 MB
- **AND** the draw order table references both entries for the same geographic position

#### Scenario: Pre-write size check
- **WHEN** the exporter is about to write a tile cell
- **THEN** it computes the encoded size before writing and splits if necessary, never writing a tile cell that exceeds 3.5 MB

### Requirement: 4 GB file size limit
The exporter SHALL ensure that no single `.img` file exceeds 4 GB (4,294,967,296 bytes). If the output would exceed this limit, the exporter SHALL split the map into multiple `.img` files, each with its own header and subfile directory. Splitting SHALL occur along tile row boundaries to maintain spatial contiguity. Each resulting file SHALL be independently loadable on a Garmin device.

#### Scenario: Output within file limit
- **WHEN** the total output is 2.8 GB
- **THEN** a single `.img` file is produced

#### Scenario: Output exceeds file limit
- **WHEN** the total output would be 6.5 GB
- **THEN** the exporter produces two `.img` files, each under 4 GB
- **AND** each file has a complete header and subfile directory
- **AND** the files together cover the full geographic extent without gaps

#### Scenario: Split files are named consistently
- **WHEN** the output is split into multiple files
- **THEN** the files are named with a numeric suffix (e.g., `switzerland_25k_1.img`, `switzerland_25k_2.img`)

### Requirement: Post-write validation with gmt
The exporter SHALL optionally validate each written `.img` file by running `gmt -i -v <file>` after writing. If validation is enabled and `gmt` reports errors, the exporter SHALL raise an exception with the validation output. If `gmt` is not available on the system, the exporter SHALL log a warning and skip validation rather than failing.

#### Scenario: Successful validation
- **WHEN** the exporter writes a valid `.img` file and runs `gmt -i -v output.img`
- **THEN** `gmt` exits with code 0 and reports no errors
- **AND** the exporter returns successfully

#### Scenario: Validation detects error
- **WHEN** the exporter writes a `.img` file and `gmt -i -v` reports a structural error
- **THEN** the exporter raises an exception containing the `gmt` error output
- **AND** the invalid file is not silently accepted

#### Scenario: gmt not available
- **WHEN** the exporter attempts validation but `gmt` is not found on PATH
- **THEN** a warning is logged and the export completes without error

### Requirement: Finalize BaseExporter interface
The `BaseExporter` abstract class in `exporters/base.py` SHALL be finalized with the following interface:
- `export(self, raster_dataset, layer_config: LayerConfig, output_path: Path) -> list[Path]` — main entry point, returns list of written file paths (multiple if split)
- `validate(self, output_path: Path) -> bool` — post-write validation hook
- `name` property returning the exporter identifier string (e.g., `"garmin-img"`)

#### Scenario: BaseExporter is abstract
- **WHEN** a subclass does not implement `export()` or `validate()`
- **THEN** instantiation raises `TypeError` (standard ABC behaviour)

#### Scenario: GarminImgExporter implements BaseExporter
- **WHEN** `GarminImgExporter` is instantiated and `export()` is called with a raster dataset, layer config, and output path
- **THEN** it produces one or more `.img` files at the specified output path and returns their paths
- **AND** each file passes `gmt -i -v` validation (if validation is enabled)
