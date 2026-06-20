## 1. Pipeline Domain Exceptions

- [x] 1.1 Define `PipelineError` base exception class in `pipeline.py`
- [x] 1.2 Define `DownloadError`, `ProcessingError`, and `ExportError` subclasses that inherit from `PipelineError` and include relevant context (source ID, layer ID) in their messages

## 2. Pipeline Factory Functions

- [x] 2.1 Implement `get_downloader(source: SourceConfig, cache_dir: Path) -> BaseDownloader` factory that maps `source.type` to the correct downloader class (wmts -> WMTSDownloader, geotiff -> GeoTIFFDownloader) and raises `PipelineError` for unknown types
- [x] 2.2 Implement `get_exporter(layer: LayerConfig, output_dir: Path) -> BaseExporter` factory that maps `layer.exporter` to the correct exporter class (garmin-img -> GarminIMGExporter) and raises `PipelineError` for unknown types

## 3. Pipeline Orchestrator

- [x] 3.1 Implement source resolution logic: given a `LayerConfig` and a list of `SourceConfig` objects, find and return the matching source by ID, raising `PipelineError` if not found
- [x] 3.2 Implement `build_layer()` async function that accepts `LayerConfig`, list of `SourceConfig`, `cache_dir`, `output_dir`, `no_download` flag, optional bounds/zoom overrides, and optional progress callback
- [x] 3.3 Implement the download stage: call `get_downloader()` with the resolved source, invoke the downloader's download method with bounds and zoom levels, catch errors and wrap in `DownloadError`
- [x] 3.4 Implement the process stage: call `RasterProcessor` to reproject, mosaic, and build overviews from downloaded tiles, catch errors and wrap in `ProcessingError`
- [x] 3.5 Implement the export stage: call `get_exporter()` with the layer config, invoke the exporter with the processed GeoTIFF, catch errors and wrap in `ExportError`
- [x] 3.6 Make `build_layer()` return the `Path` to the final output file on success
- [x] 3.7 Wire the progress callback to emit stage identifiers ("download", "process", "export") at the start of each stage

## 4. Build CLI Command

- [x] 4.1 Implement the `build` command in `cli.py` to accept all documented flags (`--sources`, `--layers`, `--layer`, `--exporter`, `--bounds`, `--zoom`, `--output-dir`, `--cache-dir`, `--no-download`, `--quality`)
- [x] 4.2 Load and merge source and layer config files using the config loader, with error handling for missing files
- [x] 4.3 Resolve the specified `--layer` ID against loaded configs, raising a clear error if not found
- [x] 4.4 Apply CLI flag overrides (bounds, zoom, exporter, quality) to the resolved layer config
- [x] 4.5 Invoke `build_layer()` via `asyncio.run()` with the resolved config and flags
- [x] 4.6 Catch domain exceptions and convert to `click.ClickException` with actionable messages
- [x] 4.7 Display a completion summary with output file path and file size

## 5. Download CLI Command

- [x] 5.1 Implement the `download` command in `cli.py` to accept `--sources`, `--layers`, `--layer`, `--bounds`, `--zoom`, and `--cache-dir` flags
- [x] 5.2 Load config and resolve the layer-to-source reference with error handling
- [x] 5.3 Invoke the appropriate downloader directly (not the full pipeline), passing bounds and zoom levels
- [x] 5.4 Catch download errors and display user-friendly messages

## 6. Split CLI Command

- [x] 6.1 Implement the `split` command in `cli.py` to accept an input `.img` file path argument
- [x] 6.2 Validate that the input file exists, displaying a clear error if not
- [x] 6.3 Check whether the file exceeds the 4 GB Garmin size limit and display a message if splitting is not needed
- [x] 6.4 Invoke `gmt` as a subprocess to split the file, capturing output and errors
- [x] 6.5 Handle `gmt` not found on PATH with a clear error message suggesting installation
- [x] 6.6 Handle `gmt` subprocess failures with the error output from `gmt`

## 7. Progress Output

- [x] 7.1 Add rich console output for stage status messages ("Downloading tiles...", "Processing raster data...", "Exporting to Garmin IMG...")
- [x] 7.2 Integrate Click's progress bar for the download stage, showing tile count progress
- [x] 7.3 Print a summary line upon build completion with the output file path and human-readable file size
- [x] 7.4 Print a summary line upon download completion with the number of tiles downloaded and total cache size

## 8. Error Handling in CLI

- [x] 8.1 Add a Click exception handler wrapper that catches `PipelineError` and subclasses, converting them to `click.ClickException` with user-friendly messages and no traceback
- [x] 8.2 Add a catch-all handler for unexpected exceptions that prints a brief message and suggests reporting the issue
- [x] 8.3 Ensure all file-not-found errors from config loading produce clear messages with the file path

## 9. Integration Tests

- [x] 9.1 Create `tests/test_pipeline.py` with a test that exercises the full pipeline with mocked downloader, processor, and exporter, verifying the correct methods are called in sequence
- [x] 9.2 Add test for `get_downloader()` factory returning the correct downloader type for each source type and raising `PipelineError` for unknown types
- [x] 9.3 Add test for `get_exporter()` factory returning the correct exporter type for each exporter name and raising `PipelineError` for unknown types
- [x] 9.4 Add test for source resolution: matching source found, missing source raises `PipelineError`
- [x] 9.5 Add test for `--no-download` flag: verify download stage is skipped and processing proceeds with cached tiles
- [x] 9.6 Add test for error propagation: verify download errors, processing errors, and export errors are wrapped in the correct domain exceptions

## 10. CLI Tests

- [x] 10.1 Create `tests/test_cli.py` tests for `build` command: verify it accepts all flags, invokes the pipeline, and produces expected output
- [x] 10.2 Add test for `download` command: verify it invokes the downloader without processing or exporting
- [x] 10.3 Add test for `split` command: verify it invokes `gmt` subprocess with correct arguments (mock subprocess)
- [x] 10.4 Add test for error messages: verify that missing layer ID, missing config file, and unknown source type produce clear error messages

## 11. End-to-End Test

- [x] 11.1 Create `tests/test_e2e.py` with a test that runs the full pipeline using a small real dataset (a few tiles for a tiny bounding box) to produce a valid `.img` file
- [x] 11.2 Validate the produced `.img` file exists and has a non-zero file size
- [x] 11.3 Mark the end-to-end test with `@pytest.mark.gdal` and `@pytest.mark.slow` so it is skipped in CI
