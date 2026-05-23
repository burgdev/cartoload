## Why

When running `cartoload build` with multi-layer targets, the download and prepare stages show only a single line per layer (e.g. "Layer 1/9: downloading Switzerland 1:1 Million...") with no progress indication. For large areas like Switzerland at high zoom levels, downloading thousands of tiles takes a long time with no visible feedback. The WMTSDownloader already has Rich progress bars internally (`download_grid()`), but the unified pipeline never calls `download_grid()` — it uses the provider's `download()` method, which for WMTS sources only initializes the downloader without fetching tiles. Tiles are fetched individually on-demand during export via `to_raster()`, meaning all download activity happens during the "Exporting to Garmin IMG" phase with no per-tile progress visibility.

## What Changes

- Add tile download progress reporting to the unified pipeline's export stage, showing how many tiles need downloading vs are already cached
- Expose download progress from `WmtsProvider.to_raster()` so the export progress callback can distinguish "downloading" from "processing" tiles
- Show a separate Rich progress bar for the download/cache-miss phase during export, alongside the existing encoding/writing bars

## Capabilities

### New Capabilities

- `download-progress`: Per-tile download progress during the export stage in the unified pipeline, showing cached vs fetched tile counts with a Rich progress bar

### Modified Capabilities

## Impact

- `src/cartoload/processor/wmts_provider.py` — track cache misses/Downloads in `to_raster()`
- `src/cartoload/exporters/garmin_img_writer.py` — add download progress reporting alongside encoding/writing
- `src/cartoload/processor/unified_pipeline.py` — pass download progress info through the pipeline
- `src/cartoload/cli.py` — add a Rich progress bar for the download phase during export
