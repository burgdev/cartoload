## Why

No open-source tool can create a **raster** Garmin `.img` file from raw tile data. The format has been reverse-engineered by the community but never formally documented for this use case. Before writing any exporter code, the internal structure must be fully understood by inspecting existing `.img` files with `gmt -i -v`. This research is the critical first step that unblocks the entire `garmin-img-exporter` change.

## What Changes

- Research and document the Garmin raster `.img` container format by analyzing existing swisstopo `.img` files with GMapTool
- Create a comprehensive format specification document at `docs/exporters/garmin-img.md` covering: header structure, subfile organisation, tile grid layout, zoom level encoding, draw order, attribution fields, and size constraints
- Define the internal data structures (Python dataclasses) that represent the format — these become the foundation for the writer implementation
- Record findings on: 3.5 MB tile cell limit, 4 GB file limit, multi-resolution pyramid encoding, and how multiple `.img` files coexist on device

## Capabilities

### New Capabilities

- `garmin-img-format-spec`: Detailed technical specification of the Garmin raster `.img` container format, derived from reverse-engineering existing files. Includes Python data model definitions for all format structures.

### Modified Capabilities

_(none)_

## Impact

- **Documentation**: `docs/exporters/garmin-img.md` becomes the authoritative format reference for the project
- **Code**: New data model classes in `src/cartoload/exporters/garmin_img_model.py` (dataclasses representing IMG header, subfiles, tile records, draw order)
- **Dependencies**: Requires `gmt` (GMapTool) binary installed locally or in Docker for `gmt -i -v` inspection
- **Blocks**: `garmin-img-exporter` cannot start until this research is complete
