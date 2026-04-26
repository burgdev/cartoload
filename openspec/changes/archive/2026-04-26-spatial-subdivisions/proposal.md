## Why

Garmin raster IMG files produced by cartoload pass GMapTool validation but are invisible on physical Garmin devices (confirmed on GPSMAP 66i with multiple test builds, including single-zoom-level tests). The root cause is missing spatial subdivisions: the current implementation writes 1 TRE2 subdivision record per zoom level instead of dividing the map area into a grid of geographic regions. Garmin's rendering engine requires this spatial index to locate and display tiles.

## What Changes

- Add a spatial subdivision generator that divides the map area into a geographic grid at each zoom level, matching the SwissTopo reference file pattern (SwissTopo_West has ~598 subdivisions across 5 zoom levels)
- Write proper TRE2 records with per-subdivision center coordinates, RGN2 offsets, and subdivision counts
- Write proper TRE7 raster layer entries (one per subdivision instead of one per zoom level)
- Generate polyline preamble coordinate bitstreams with actual geographic extent data (currently all zeros)
- Group RGN2 data by subdivision instead of by zoom level
- Update TRE1 subdivision counts to reflect actual spatial subdivision counts

## Capabilities

### New Capabilities
- `spatial-subdivisions`: Subdivision generation for Garmin raster IMG files — dividing the map area into a geographic grid, assigning tiles to subdivisions, and producing correct TRE2/TRE7/RGN2 data structures

### Modified Capabilities
- `dynamic-zoom-codes`: TRE1 subdivision_count field changes from hard-coded 1 to dynamically computed from spatial subdivisions

## Impact

- **Core files**: `src/cartoload/exporters/garmin_img.py` (subdivision generation), `src/cartoload/exporters/garmin_img_writer.py` (TRE2, TRE7, RGN2 writing), `src/cartoload/exporters/garmin_img_model.py` (data model updates)
- **Tests**: `tests/test_exporter_garmin_img.py` — existing tests must pass, new tests for subdivision generation
- **Documentation**: `docs/exporters/garmin-img.md` — update subdivision format section, add polyline preamble encoding details
- **Reference data**: SwissTopo_West.img and IOM.img verified working on GPSMAP 66i; new findings about polyline preambles and spatial subdivision structure to be documented
