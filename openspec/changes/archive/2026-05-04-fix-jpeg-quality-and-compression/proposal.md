## Why

The `--quality` CLI parameter (1-100) has no effect on output size. Testing with `--quality 20` and `--quality 80` produces identical 17.0 MB files. This matters because full Switzerland maps reach ~10 GB and there's no way to control output size. SwissTopo serves tiles at roughly JPEG quality 85 — testing shows re-encoding at Q75 saves ~30%, Q50 saves ~50% of tile data.

## What Changes

- Fix the quality parameter so it actually controls JPEG compression in the output IMG file
- Use PIL (Pillow) for JPEG re-encoding since rasterio's MemoryFile ignores `JPEG_QUALITY` creation options
- Apply quality re-encoding to ALL tiles, not just those needing CRS reprojection — currently tiles already in EPSG:4326 are embedded as raw bytes regardless of quality setting
- Fix the `_process_tile_jpeg` function which receives `jpeg_quality` but never passes it to the `tile_processor` callable

## Capabilities

### New Capabilities

_None_

### Modified Capabilities

- `rasterio-warp-processor`: Quality parameter must actually control JPEG output quality. Switch from rasterio MemoryFile JPEG encoding to PIL for reliable quality control. Apply quality re-encoding to all tiles (not just warp path).
- `streaming-tile-processing`: When quality differs from source, tiles in matching CRS must also be re-encoded (currently they pass through as raw bytes regardless of quality setting).

## Impact

- `src/cartoload/processor/rasterio_warp.py` — switch JPEG encoding from rasterio MemoryFile to PIL for quality control
- `src/cartoload/exporters/garmin_img_writer.py` — `_process_tile_jpeg` must apply quality re-encoding even when no processor is set; quality parameter must actually flow to encoding
- `src/cartoload/exporters/garmin_img.py` — may need to always provide a processor or re-encode step
- Dependency: Pillow (already used elsewhere in the project, no new dependency needed)
- Breaking: output file sizes will change when quality < 85 (default) — this is the intended fix
