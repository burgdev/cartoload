## Why

Generated Garmin IMG raster maps display incorrectly in GPXSee: tiles show up sporadically and are "spread out" rather than forming a coherent map. While LBL28/LBL29 sections now have non-zero sizes (fixing the previous bug), tiles still don't render properly, indicating deeper issues with coordinate encoding, projection, zoom level mapping, or JPEG storage format that require systematic investigation against working reference files.

## What Changes

- **Add binary comparison tools**: Implement systematic comparison between generated IMG files and working references (SwissTopo, IOM) to identify structural differences in headers, sections, and data encoding
- **Add JPEG coordinate validation**: Verify that JPEG tile coordinates are correctly encoded in RGN2 records and that projection/reprojection is handled properly for Web Mercator → WGS84 conversion
- **Add raster export capability**: Implement `cartoload analyze img export` command to extract raster tiles from IMG files as GeoTIFF, enabling visual verification of tile placement and coordinate accuracy
- **Investigate zoom level encoding**: Analyze why reference files use higher zoom levels (16+) vs our generated files, and determine if this affects tile display
- **Enhanced analysis output**: Improve `cartoload analyze img info` to show per-tile coordinate details, zoom level mapping, and validate internal consistency

## Capabilities

### New Capabilities
- `img-binary-comparison`: Systematic byte-level and structural comparison of IMG files against reference files, with normalization of date/ID fields
- `img-raster-export`: Extract raster tiles from IMG files as GeoTIFF with proper georeferencing, supporting bbox filtering and zoom level selection
- `img-coordinate-validation`: Validate tile coordinate encoding in RGN2 records, including delta encoding, map unit conversions, and bounds consistency

### Modified Capabilities
- `cli-extent-override`: Extend analyze commands with export capability, coordinate detail views, and comparison normalization
- `garmin-img-exporter`: Fix coordinate encoding, projection handling, and zoom level mapping based on comparison findings

## Impact

- `src/cartoload/analysis/img_parser.py` — Add GeoTIFF export, coordinate validation, enhanced tile detail parsing
- `src/cartoload/analysis/compare.py` — Add normalization for date/ID fields, structural diff highlighting
- `src/cartoload/cli_analyze.py` — Add `img export` command, new flags for coordinate/tile details
- `src/cartoload/exporters/garmin_img_writer.py` — Fix coordinate encoding, zoom level generation, projection conversions
- `src/cartoload/exporters/garmin_img.py` — Fix tile bounds calculation, subdivision coordinate mapping
- `tests/test_analysis.py` — Add tests for export, validation, comparison
- New dependency: `rasterio` or `gdal` for GeoTIFF export
