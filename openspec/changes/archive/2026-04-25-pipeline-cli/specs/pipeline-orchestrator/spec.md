## ADDED Requirements

### Requirement: Pipeline orchestrates download-process-export stages

`pipeline.py` SHALL implement an async `build_layer()` function that chains three stages in sequence: download tiles, process raster, export to device format. Each stage receives the output of the previous stage.

#### Scenario: Full pipeline execution

- **WHEN** `build_layer()` is called with a valid `LayerConfig`, `SourceConfig`, cache directory, and output directory
- **THEN** it downloads tiles via the appropriate downloader, processes the downloaded tiles into a mosaic GeoTIFF, and exports the GeoTIFF to the target format (e.g., `.img`)

#### Scenario: Pipeline skips download with --no-download

- **WHEN** `build_layer()` is called with `no_download=True`
- **THEN** the download stage is skipped and the pipeline proceeds directly to processing using tiles already present in the cache directory

### Requirement: Pipeline selects downloader by source type

`pipeline.py` SHALL implement a factory function `get_downloader(source: SourceConfig, cache_dir: Path) -> BaseDownloader` that returns the correct downloader based on `source.type`:

- `type: wmts` returns `WMTSDownloader`
- `type: geotiff` returns `GeoTIFFDownloader`
- Unknown types raise a `PipelineError` with a descriptive message

#### Scenario: WMTS source gets WMTS downloader

- **WHEN** `get_downloader()` is called with a `SourceConfig` where `type="wmts"`
- **THEN** a `WMTSDownloader` instance is returned

#### Scenario: GeoTIFF source gets GeoTIFF downloader

- **WHEN** `get_downloader()` is called with a `SourceConfig` where `type="geotiff"`
- **THEN** a `GeoTIFFDownloader` instance is returned

#### Scenario: Unknown source type raises error

- **WHEN** `get_downloader()` is called with a `SourceConfig` where `type="unknown"`
- **THEN** a `PipelineError` is raised with a message indicating the unsupported source type

### Requirement: Pipeline selects exporter by config

`pipeline.py` SHALL implement a factory function `get_exporter(layer: LayerConfig, output_dir: Path) -> BaseExporter` that returns the correct exporter based on `layer.exporter`:

- `exporter: garmin-img` returns `GarminIMGExporter`
- Unknown exporters raise a `PipelineError` with a descriptive message

#### Scenario: Garmin IMG exporter selected

- **WHEN** `get_exporter()` is called with a `LayerConfig` where `exporter="garmin-img"`
- **THEN** a `GarminIMGExporter` instance is returned

#### Scenario: Unknown exporter raises error

- **WHEN** `get_exporter()` is called with a `LayerConfig` where `exporter="unknown"`
- **THEN** a `PipelineError` is raised with a message indicating the unsupported exporter type

### Requirement: Pipeline handles errors at each stage

`pipeline.py` SHALL catch and wrap errors from each pipeline stage into domain exceptions:

- Download errors raise `DownloadError` with the source ID and original error
- Processing errors raise `ProcessingError` with the layer ID and original error
- Export errors raise `ExportError` with the layer ID and original error

Each domain exception inherits from `PipelineError` and preserves the original exception as `__cause__`.

#### Scenario: Download failure produces DownloadError

- **WHEN** the download stage raises an exception (e.g., HTTP connection error)
- **THEN** a `DownloadError` is raised wrapping the original exception, including the source ID in the message

#### Scenario: Processing failure produces ProcessingError

- **WHEN** the processing stage raises an exception (e.g., GDAL subprocess failure)
- **THEN** a `ProcessingError` is raised wrapping the original exception, including the layer ID in the message

#### Scenario: Export failure produces ExportError

- **WHEN** the export stage raises an exception (e.g., tile encoding failure)
- **THEN** an `ExportError` is raised wrapping the original exception, including the layer ID in the message

### Requirement: Pipeline resolves layer to source reference

`pipeline.py` SHALL resolve a `LayerConfig` to its corresponding `SourceConfig` by matching `layer.source` against a collection of loaded source configs. If no matching source is found, a `PipelineError` is raised.

#### Scenario: Layer references existing source

- **WHEN** `build_layer()` is called with a layer whose `source` field matches a loaded source ID
- **THEN** the pipeline resolves the source and proceeds with the correct downloader

#### Scenario: Layer references missing source

- **WHEN** `build_layer()` is called with a layer whose `source` field does not match any loaded source ID
- **THEN** a `PipelineError` is raised with a message listing the unresolved source reference

### Requirement: Pipeline returns output path

`build_layer()` SHALL return the `Path` to the final output file (e.g., the `.img` file) upon successful completion.

#### Scenario: Successful build returns output path

- **WHEN** `build_layer()` completes all stages successfully
- **THEN** it returns a `Path` pointing to the exported output file

### Requirement: Pipeline supports progress callback

`build_layer()` SHALL accept an optional progress callback that is called at the start of each stage with a stage identifier and description. This enables the CLI to display progress information.

#### Scenario: Progress callback receives stage updates

- **WHEN** `build_layer()` is called with a `progress_callback` argument
- **THEN** the callback is invoked with stage information at the start of the download, process, and export stages
