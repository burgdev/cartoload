## 1. Sample Collection

- [ ] 1.1 Collect at least two existing raster Garmin `.img` files for analysis (e.g., swisstopo ch_basemap_25k and ch_basemap_10k) and place them in a local test data directory
- [ ] 1.2 Verify `gmt` (GMapTool) is installed and functional by running `gmt` with no arguments and confirming it prints usage info
- [ ] 1.3 Run `gmt -i -v` on each sample `.img` file and save the full verbose output to text files for offline analysis

## 2. Header Structure Analysis

- [ ] 2.1 Document the IMG file magic bytes/signature, format version field, and their expected values
- [ ] 2.2 Document the creation date encoding (byte offset, length, date format)
- [ ] 2.3 Document the overall data size field, block size field, and their relationship
- [ ] 2.4 Document the File Allocation Table (FAT) layout: FAT page size, number of pages, block pointer format, and chain traversal algorithm
- [ ] 2.5 Cross-reference all header field values against hex dumps of the first 512 bytes for verification

## 3. Subfile Organization Analysis

- [ ] 3.1 Enumerate all subfile types present in the sample files (MAP, TRE, RGN, LBL, GMP, TYP, MDR, etc.)
- [ ] 3.2 Document the subfile header table location, entry format (name, type, size, start block), and entry count
- [ ] 3.3 Document how each subfile's data blocks are chained via the FAT and how to reconstruct contiguous data
- [ ] 3.4 Identify which subfile types are required for raster maps vs. optional or vector-only

## 4. Tile Grid Layout Analysis

- [ ] 4.1 Document the tile index structure: location within the file, entry format, and how to determine tile count
- [ ] 4.2 Document tile coordinate encoding: how lat/lon bounds map to tile row/column numbers
- [ ] 4.3 Document the tile data block format: compression type, pixel encoding, header within tile data
- [ ] 4.4 Document the 3.5 MB per-tile-cell limit and its practical implications for tile dimensions at each zoom level
- [ ] 4.5 Verify tile data integrity by extracting and decompressing a sample tile from the test files

## 5. Zoom Level Encoding Analysis

- [ ] 5.1 Document the zoom level table structure: location, number of entries, entry format
- [ ] 5.2 Document how each zoom level references its subset of tiles (tile range or offset/count)
- [ ] 5.3 Map zoom level numbers to approximate ground resolution (meters per pixel) based on sample data
- [ ] 5.4 Document how the multi-resolution pyramid is built across zoom levels

## 6. Draw Order and Attribution Analysis

- [ ] 6.1 Locate and document the draw order field: byte offset, valid range, and recommended values for raster basemaps
- [ ] 6.2 Document map name, description, and copyright string locations, maximum lengths, and character encoding
- [ ] 6.3 Document any additional metadata fields visible on Garmin devices (area bounds, language, etc.)

## 7. Size Constraints Analysis

- [ ] 7.1 Document the 4 GB maximum file size limit and how it relates to FAT and block addressing
- [ ] 7.2 Document maximum tile count per subfile, maximum subfile count, and maximum zoom level count
- [ ] 7.3 Document any block count or FAT size limits discovered during inspection
- [ ] 7.4 Document when and how a single map must be split into multiple `.img` files

## 8. Python Data Model

- [ ] 8.1 Create `src/cartoload/exporters/garmin_img_model.py` with `IMGHeader` dataclass containing all header fields with typed attributes and docstrings
- [ ] 8.2 Add `SubfileHeader` dataclass with type, name, size, start block, and FAT chain fields
- [ ] 8.3 Add `TileRecord` dataclass with tile coordinates (row, col, lat/lon bounds), data offset, data length, and compression type fields
- [ ] 8.4 Add `ZoomLevel` dataclass with level number, resolution, tile offset/count, and bounds fields
- [ ] 8.5 Add `DrawOrderEntry` dataclass with value and layer type fields
- [ ] 8.6 Add `IMGFile` dataclass as a top-level container aggregating `IMGHeader`, list of `SubfileHeader`, list of `TileRecord`, list of `ZoomLevel`, and `DrawOrderEntry`
- [ ] 8.7 Add module-level docstring explaining the purpose and relationship to `docs/exporters/garmin-img.md`

## 9. Validation

- [ ] 9.1 Parse `gmt -i -v` output from ch_basemap_25k into the data model and verify all fields are captured correctly
- [ ] 9.2 Parse `gmt -i -v` output from ch_basemap_10k into the data model and verify all fields are captured correctly
- [ ] 9.3 Cross-reference parsed values against raw `gmt` output to confirm no fields are missing or misinterpreted
- [ ] 9.4 Write findings into `docs/exporters/garmin-img.md` as the authoritative format reference, replacing the placeholder

## 10. Finalization

- [ ] 10.1 Review the complete format specification document for internal consistency (field offsets, sizes, and descriptions all agree)
- [ ] 10.2 Review the data model classes for completeness (every field in the spec has a corresponding dataclass attribute)
- [ ] 10.3 Note any unresolved questions or "unknown/reserved" fields for future investigation during writer implementation
