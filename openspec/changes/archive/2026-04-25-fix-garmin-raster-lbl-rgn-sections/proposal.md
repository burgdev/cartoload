## Why

The current Garmin IMG raster implementation produces structurally valid files that pass basic GMT validation but **GMT does not detect the raster images** and Garmin devices cannot render the tiles. Analysis reveals that the implementation is missing critical raster-specific sections documented in the QMapShack wiki: LBL28 (Image Index), LBL29 (Image Storage), and RGN Type E0 records (tile metadata). Without these sections, GMT cannot locate the JPEG tile data, resulting in no "Bitmaps" line in the output and non-functional raster maps.

## What Changes

- **Add LBL28 section** to LBL sub-header: image index table storing uint32 offsets pointing to each JPEG tile in LBL29
- **Add LBL29 section** to LBL sub-header: image storage area containing concatenated JPEG files (currently written at wrong location)
- **Add RGN Type E0 records** to RGN data section: per-tile metadata including bounds, size, and LBL28 index references (currently 1582 bytes of zeros)
- **Move JPEG tile data** from "end of GMP" to LBL29 section, indexed by LBL28 and referenced by RGN Type E0 records
- **Remove incorrect tile index table** currently written at end of GMP (not part of raster IMG specification)
- **Update documentation** in `docs/exporters/garmin-img.md` to include LBL28/LBL29/RGN Type E0 details from QMapShack wiki
- **Update resources** in `docs/exporters/garmin-img-resources.md` to reference QMapShack wiki as authoritative source for raster-specific sections

## Capabilities

### New Capabilities

- `lbl28-image-index`: LBL28 section writing - creates image index table with uint32 offsets to JPEG tiles
- `lbl29-image-storage`: LBL29 section writing - stores concatenated JPEG tiles indexed by LBL28
- `rgn-type-e0-records`: RGN Type E0 record writing - per-tile metadata with bounds, size, and image index references

### Modified Capabilities

- `gmp-container-format`: Update GMP container layout to remove incorrect tile index table and move JPEGs to LBL29 section

## Impact

**Files Modified**:

- `src/cartoload/exporters/garmin_img_writer.py`: Major changes to GMPWriter, LBL sub-header builder, RGN data writer
- `src/cartoload/exporters/garmin_img_model.py`: Add data models for Type E0 records, LBL28/LBL29 section metadata
- `docs/exporters/garmin-img.md`: Add LBL28/LBL29/RGN Type E0 documentation sections
- `docs/exporters/garmin-img-resources.md`: Add QMapShack wiki reference and raster-specific format details
- `tests/test_exporter_garmin_img.py`: Update tests to verify LBL28/LBL29/RGN structure, verify GMT "Bitmaps" output

**Breaking Changes**: None - this is a bug fix for non-functional raster output. Existing (broken) IMG files will be replaced with correct ones.

**Dependencies**: No new external dependencies. QMapShack wiki analysis already completed during exploration.

**Testing Impact**: GMT validation tests must be updated to assert "Bitmaps" line appears in output. Existing tests that pass with broken structure will need adjustment.
