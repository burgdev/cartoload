## 1. Sample Collection

- [x] 1.1 Collect at least two existing raster Garmin `.img` files for analysis (e.g., swisstopo ch_basemap_25k and ch_basemap_10k) and place them in a local test data directory
- [x] 1.2 Verify `gmt` (GMapTool) is installed and functional by running `gmt` with no arguments and confirming it prints usage info
- [x] 1.3 Run `gmt -i -v` on each sample `.img` file and save the full verbose output to text files for offline analysis

## 2. Header Structure Analysis

- [x] 2.1 Document the IMG file magic bytes/signature, format version field, and their expected values
- [x] 2.2 Document the creation date encoding (byte offset, length, date format)
- [x] 2.3 Document the overall data size field, block size field, and their relationship
- [x] 2.4 Document the File Allocation Table (FAT) layout: FAT page size, number of pages, block pointer format, and chain traversal algorithm
- [x] 2.5 Cross-reference all header field values against hex dumps of the first 512 bytes for verification

## 3. Subfile Organization Analysis

- [x] 3.1 Enumerate all subfile types present in the sample files (MAP, TRE, RGN, LBL, GMP, TYP, MDR, etc.)
- [x] 3.2 Document the subfile header table location, entry format (name, type, size, start block), and entry count
- [x] 3.3 Document how each subfile's data blocks are chained via the FAT and how to reconstruct contiguous data
- [x] 3.4 Identify which subfile types are required for raster maps vs. optional or vector-only

## 4. Tile Grid Layout Analysis

- [x] 4.1 Document the tile index structure: location within the file, entry format, and how to determine tile count
- [x] 4.2 Document tile coordinate encoding: how lat/lon bounds map to tile row/column numbers
- [x] 4.3 Document the tile data block format: compression type, pixel encoding, header within tile data
- [x] 4.4 Document the 3.5 MB per-tile-cell limit and its practical implications for tile dimensions at each zoom level
- [x] 4.5 Verify tile data integrity by confirming tile count, size, and compression type from GMT output

## 5. Zoom Level Encoding Analysis

- [x] 5.1 Document the zoom level table structure: location, number of entries, entry format
- [x] 5.2 Document how each zoom level references its subset of tiles (tile range or offset/count)
- [x] 5.3 Map zoom level numbers to approximate ground resolution (meters per pixel) based on sample data
- [x] 5.4 Document how the multi-resolution pyramid is built across zoom levels

## 6. Draw Order and Attribution Analysis

- [x] 6.1 Locate and document the draw order field: byte offset, valid range, and recommended values for raster basemaps
- [x] 6.2 Document map name, description, and copyright string locations, maximum lengths, and character encoding
- [x] 6.3 Document any additional metadata fields visible on Garmin devices (area bounds, language, etc.)

## 7. Size Constraints Analysis

- [x] 7.1 Document the 4 GB maximum file size limit and how it relates to FAT and block addressing
- [x] 7.2 Document maximum tile count per subfile, maximum subfile count, and maximum zoom level count
- [x] 7.3 Document any block count or FAT size limits discovered during inspection
- [x] 7.4 Document when and how a single map must be split into multiple `.img` files

## 8. Python Data Model

- [x] 8.1 Create `src/cartoload/exporters/garmin_img_model.py` with `IMGHeader` dataclass containing all header fields with typed attributes and docstrings
- [x] 8.2 Add `SubfileHeader` dataclass with type, name, size, start block, and FAT chain fields
- [x] 8.3 Add `TileRecord` dataclass with tile coordinates (row, col, lat/lon bounds), data offset, data length, and compression type fields
- [x] 8.4 Add `ZoomLevel` dataclass with level number, resolution, tile offset/count, and bounds fields
- [x] 8.5 Add `DrawOrderEntry` dataclass with value and layer type fields
- [x] 8.6 Add `IMGFile` dataclass as a top-level container aggregating `IMGHeader`, list of `SubfileHeader`, list of `TileRecord`, list of `ZoomLevel`, and `DrawOrderEntry`
- [x] 8.7 Add module-level docstring explaining the purpose and relationship to `docs/exporters/garmin-img.md`

## 9. Validation

- [x] 9.1 Parse `gmt -i -v` output from SwissTopo_West into the data model and verify all fields are captured correctly
- [x] 9.2 Parse `gmt -i -v` output from SwissTopo_Est into the data model and verify all fields are captured correctly
- [x] 9.3 Cross-reference parsed values against raw `gmt` output to confirm no fields are missing or misinterpreted
- [x] 9.4 Write findings into `docs/exporters/garmin-img.md` as the authoritative format reference, replacing the placeholder

## 10. Finalization

- [x] 10.1 Review the complete format specification document for internal consistency (field offsets, sizes, and descriptions all agree)
- [x] 10.2 Review the data model classes for completeness (every field in the spec has a corresponding dataclass attribute)
- [x] 10.3 Note any unresolved questions or "unknown/reserved" fields for future investigation during writer implementation
