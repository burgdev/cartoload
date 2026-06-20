## Why

The Garmin IMG exporter produces files that fail validation with GMapTool (`gmt`), which reports "Wrong header (block size)" errors. The output files are also significantly undersized (1.4 MB) compared to the expected size based on cached tile data (46 MB), indicating that tile data is either not being written correctly or is being lost during the write process. These issues make the exported IMG files unusable on Garmin devices.

## What Changes

- Fix the 512-byte IMG header serialization to match the byte-level layout observed in known-good SwissTopo reference files, including correct field offsets, byte ordering, and missing fields (length prefix at 0x40, FAT descriptor block at 0x1C0, etc.)
- Implement proper FAT (File Allocation Table) block chain entries instead of writing a zero-filled placeholder region, so that subfile data blocks can be located by Garmin tools and devices
- Fix the subfile directory entry format to match the binary layout expected by GMT (currently the name/type/offset/size fields are at incorrect offsets within each 512-byte entry)
- Fix the GMP subfile writer so that tile index entries contain correct offsets relative to the GMP data section (currently offsets are relative to an internal counter but do not account for the GMP header, zoom table, draw order, and tile index sections that precede the tile data)
- Fix tile extraction from GeoTIFF rasters to handle the case where `gdal_translate` is given an already-processed raster (not raw WMTS tiles), ensuring tiles are actually extracted rather than producing empty output
- Add a comprehensive E2E test that downloads a small area (2 zoom levels), generates an IMG file, and validates it with `gmt`

## Capabilities

### New Capabilities

- `img-fat-chains`: Correct FAT block chain management for Garmin IMG files, enabling Garmin tools and devices to locate subfile data through proper chain traversal
- `img-header-validation`: Byte-accurate IMG header serialization that matches the format expected by GMapTool and Garmin firmware, with validation against reference SwissTopo files

### Modified Capabilities

## Impact

- **`src/cartoload/exporters/garmin_img_writer.py`**: Major changes to `IMGHeaderWriter` (header field offsets and values), new FAT chain writer, fixes to `SubfileDirectoryWriter` entry layout, fixes to `GMPWriter` tile index offset calculation
- **`src/cartoload/exporters/garmin_img_model.py`**: Possible additions to `IMGHeader` dataclass for missing fields (FAT descriptor, header size prefix at 0x40)
- **`src/cartoload/exporters/garmin_img.py`**: Minor changes to `GarminImgExporter` for passing additional metadata needed by fixed writer
- **`tests/test_exporter_garmin_img.py`**: Updated tests to verify correct header byte offsets, FAT chain structure, and GMP tile index offsets
- **`tests/test_e2e.py`**: New E2E test downloading small area and validating IMG with `gmt`
- **External dependency**: `gmt` (GMapTool) required for validation tests (already an optional test dependency)
