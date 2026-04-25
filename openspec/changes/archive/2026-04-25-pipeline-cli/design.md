## Context

All individual components of cartoload now exist as working implementations:

- **config-loader** (`config.py`): Parses, merges, validates, and resolves YAML source and layer config files into typed `SourceConfig` and `LayerConfig` dataclasses.
- **wmts-downloader** (`downloader/wmts.py`): Downloads tiles from WMTS/XYZ/TMS services within a bounding box at specified zoom levels, with concurrent downloads, rate limiting, caching, and retry logic.
- **geotiff-downloader** (`downloader/geotiff.py`): Queries STAC APIs and downloads GeoTIFF tiles for a given product and bounding box, with caching and progress output.
- **raster-processor** (`processor/raster.py`): Reprojects downloaded tiles to the target CRS, creates a VRT mosaic, builds overviews, and outputs a single GeoTIFF ready for export.
- **garmin-img-exporter** (`exporters/garmin_img.py`): Writes raster Garmin `.img` files from processed GeoTIFF data, supporting multi-resolution pyramids, attribution, and size constraints.

The stubs in `pipeline.py` and `cli.py` (created during project-scaffolding) need to become real implementations that wire these components together into a working end-to-end pipeline. This is step 4 in the SPEC.md implementation order.

## Goals / Non-Goals

**Goals:**

- Implement pipeline orchestration in `pipeline.py` that chains config loading, downloading, processing, and exporting into a single `build_layer()` call
- Make the `build` CLI command functional with all documented flags (`--sources`, `--layers`, `--layer`, `--exporter`, `--bounds`, `--zoom`, `--output-dir`, `--cache-dir`, `--no-download`, `--quality`)
- Make the `download` CLI command functional for download-only workflows
- Make the `split` CLI command functional using `gmt` subprocess to split oversized `.img` files
- Proper error handling at each pipeline stage with user-friendly error messages
- Progress output using Click's progress bar and rich for download/build stages

**Non-Goals:**

- New downloaders (gpkg downloader, vector sources)
- New exporters (garmin-img-vector, other formats)
- New processors (vector processing)
- Web UI or server integration
- Parallel layer builds (each layer built sequentially)

## Decisions

### 1. Pipeline is async at the downloader level, synchronous at the orchestrator level

**Choice**: `build_layer()` is an async function because the WMTS downloader uses async for concurrent tile downloads. The CLI invokes it via `asyncio.run()`.

**Rationale**: The WMTS downloader already uses async for concurrent HTTP requests with rate limiting. The orchestrator itself does not add additional async complexity -- it calls the downloader's async methods and awaits the result. The processor and exporter are synchronous (subprocess calls and binary file writing).

**Alternative considered**: Fully synchronous pipeline with thread-based concurrency. Rejected because the downloader is already async and wrapping it in threads adds unnecessary complexity.

### 2. Downloader selection by source type

**Choice**: A factory function `get_downloader(source: SourceConfig) -> BaseDownloader` that returns `WMTSDownloader` for `type: wmts` and `GeoTIFFDownloader` for `type: geotiff`.

**Rationale**: Each source config has a `type` field that maps directly to a downloader class. The factory pattern keeps the pipeline decoupled from specific downloader implementations. Future downloaders (gpkg, vector) are added by extending the factory.

**Alternative considered**: Method on `SourceConfig` that returns its downloader. Rejected to avoid coupling config dataclasses to downloader implementations.

### 3. Exporter selection by config

**Choice**: A factory function `get_exporter(layer: LayerConfig) -> BaseExporter` that returns `GarminIMGExporter` for `exporter: garmin-img`.

**Rationale**: Same factory pattern as downloader selection. The layer config's `exporter` field specifies which exporter to use.

### 4. CLI uses Click's progress bar plus rich

**Choice**: The `build` and `download` commands use rich for structured console output (status messages, errors, summary) and Click's progress bar for tile download progress.

**Rationale**: rich is already a dependency (used by the WMTS downloader). Click's built-in progress bar integrates naturally with Click commands. Using both gives structured output (rich) for status messages and a simple progress indicator (Click) for operations with known counts.

### 5. Split uses `gmt` subprocess

**Choice**: The `split` command invokes `gmt` (GMapTool) as a subprocess to split oversized `.img` files that exceed the 4 GB Garmin device limit.

**Rationale**: `gmt` is already a system dependency (installed in Docker). GMapTool is the standard tool for splitting Garmin `.img` files. Calling it via subprocess is the simplest approach and avoids reimplementing its splitting logic.

**Alternative considered**: Implementing splitting in pure Python. Rejected because `gmt` already handles this correctly and is a required system dependency.

### 6. Error handling via Click's exception handling

**Choice**: Pipeline errors are caught in the CLI layer and converted to Click exceptions (`click.ClickException` for user errors, `click.Abort` for fatal errors). The pipeline itself raises domain exceptions (`PipelineError`, `DownloadError`, `ExportError`).

**Rationale**: Click's exception handling provides clean error output (no traceback for user errors, proper exit codes). The pipeline layer uses domain exceptions so errors can be distinguished by type. The CLI layer maps domain exceptions to Click exceptions.

### 7. `--no-download` flag skips download stage

**Choice**: When `--no-download` is passed, the pipeline skips the download stage and proceeds directly to processing, using whatever tiles are already in the cache directory.

**Rationale**: This supports iterative development of processing and export steps without re-downloading tiles. It also enables offline usage when tiles have been pre-fetched.

## Risks / Trade-offs

- **Interface mismatches between components** → Each component was developed in isolation. The pipeline wiring may reveal that downloader output paths don't match processor input expectations, or that processor output format doesn't match exporter input requirements. Mitigated by defining clear interfaces in the `BaseDownloader`, `BaseExporter`, and processor contracts, and validating them during integration testing.
- **Full Switzerland run may exceed memory or disk** → A complete Switzerland 1:25k raster at high zoom levels could produce tens of GB of tile data. The VRT mosaic approach (used by the raster processor) avoids loading everything into memory, but disk space in the cache directory must be sufficient. Mitigated by documenting expected disk requirements and adding a pre-flight disk space check in the future.
- **`gmt` binary behavior varies by version** → GMapTool's command-line interface may differ between versions. The split command should validate `gmt` availability and version before use, and provide clear error messages if `gmt` is not installed.
- **Error messages during integration** → Wiring components together creates more surface area for user-facing errors (e.g., source not found, layer references unknown source, exporter fails on processed data). Each error path needs a clear, actionable message. Mitigated by testing error paths explicitly.
