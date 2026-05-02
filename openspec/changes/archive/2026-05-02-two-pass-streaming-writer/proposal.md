## Why

The current IMG writer requires all tile JPEG data in memory to compute layout (subdivisions, FAT tables, section offsets) before writing. For a 40x40km SwissTopo build (197K tiles), this means 5+ GB of RAM. A full-country build (~2M tiles) would need 50+ GB — impractical for most machines. The tile bounds needed for layout are deterministic from (x, y, zoom) coordinates, so JPEG data should never need to be in memory during the layout pass.

## What Changes

- Split the IMG writer into a **layout pass** (compute bounds, subdivisions, FAT, offsets from tile coordinates only) and a **write pass** (stream JPEG data using pre-computed offsets, only one batch in memory at a time)
- Refactor `pipeline.py` to stream tiles per-zoom to the writer instead of accumulating all tiles in a `compressed_tiles` dict
- Connect the existing `process_zoom_level_batched()` generator to the writer so JPEG data flows through in batches of ~500 tiles (~12 MB) instead of accumulating all at once

## Capabilities

### New Capabilities

- `two-pass-img-writer`: IMG writer architecture that separates layout computation (from tile coordinates) from JPEG data writing (streamed in batches), bounding memory to ~500 MB regardless of tile count

### Modified Capabilities

- `streaming-tile-processing`: Pipeline streams tiles per-zoom to the writer instead of accumulating all tiles in memory before export
- `garmin-img-exporter`: `export_from_tiles()` accepts tile data incrementally per zoom level instead of requiring the full `compressed_tiles` dict upfront

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — Major refactor: split `LayoutComputer` to work from coordinate-only tile metadata, add streaming write path that reads JPEG data on demand
- `src/cartoload/exporters/garmin_img.py` — Update `export_from_tiles()` to accept per-zoom tile streams
- `src/cartoload/pipeline.py` — Replace `compressed_tiles` accumulation with per-zoom streaming to exporter
- `src/cartoload/processor/batch.py` — Connect `process_zoom_level_batched()` generator to pipeline
