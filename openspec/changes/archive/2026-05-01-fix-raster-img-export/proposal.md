## Why

Cartoload generates Garmin IMG raster map files, but the maps do not display on Garmin devices. The IMG files are syntactically valid (GMT parses them), but something in the binary encoding prevents devices from rendering the raster tiles. This is the core functionality of the tool — without working device output, the export pipeline is useless.

## What Changes

- **Fix RGN2 section structure**: The RGN2 data section currently writes a polyline preamble + E0 record per tile, but the segment boundaries (which subdivisions have data, where each subdivision's data starts/ends) may not align with what devices expect. GPXSee's parsing reveals that RGN2 data is split into per-subdivision segments using extended polygon offsets from TRE7.

- **Fix TRE7 extended section semantics**: Our TRE7 writes a `uint32 offset + uint8 flag` per subdivision, but the offset semantics need verification — GPXSee treats TRE7 polygon offsets as segment start positions into the `_polygons` section of RGN (which is RGN2). The flag byte controls empty vs data subdivisions but may need specific handling for how offsets form segment boundaries.

- **Fix RGN sub-header polygon section fields**: The RGN sub-header at offset 0x1D-0x24 currently stores RGN2 position/size, but the "polygons" extended section fields at offsets 0x25-0x2C (non-base polygon section) may also need to be populated with offset/size data, as GPXSee reads these for extended polygon object parsing.

- **Enhance analyze tool**: Add structured comparison capability to validate generated IMG files against reference files. Add section-level validation that checks TRE7/RGN2/TRE2 consistency. Improve RGN2 record parsing to properly decode polyline preambles and E0 records with per-subdivision segmentation.

## Capabilities

### New Capabilities
- `rgn2-segment-encoding`: Correct per-subdivision RGN2 data layout with proper segment boundaries, polyline preamble encoding, and E0 record format — matching what Garmin devices parse via extended polygon object segments.

### Modified Capabilities
- `garmin-img-exporter`: Fix TRE7 offset semantics to properly represent per-subdivision RGN2 segment boundaries. Fix RGN sub-header to populate extended polygon section fields. Fix TRE2 subdivision records to correctly encode segment boundaries for raster maps.
- `cli-extent-override`: Extend `cartoload analyze img info` with validation checks for TRE7/RGN2 segment consistency and structured section comparison.

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — RGN sub-header, TRE7 writing, RGN2 data section, polyline preamble encoding
- `src/cartoload/exporters/garmin_img.py` — Subdivision generation, TRE2 subdivision linking
- `src/cartoload/exporters/garmin_img_model.py` — Subdivision model (if segment boundary fields needed)
- `src/cartoload/analysis/rgn2.py` — Enhanced RGN2 parsing with per-subdivision segment decoding
- `src/cartoload/analysis/img_parser.py` — TRE7/RGN2 consistency validation
- `src/cartoload/cli_analyze.py` — New validation/comparison CLI options
