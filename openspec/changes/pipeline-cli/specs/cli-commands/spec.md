## ADDED Requirements

### Requirement: Build command with all flags

The `build` CLI command SHALL accept the following options:

- `--sources` (multiple): paths to source YAML config files
- `--layers` (multiple): paths to layer YAML config files
- `--layer` (single): specific layer ID to build (required)
- `--exporter` (single): override the exporter type from the layer config
- `--bounds` (single): override bounds as `minx,miny,maxx,maxy`
- `--zoom` (single): override zoom levels as a comma-separated list or range
- `--output-dir` (single): output directory for exported files (default: `output/`)
- `--cache-dir` (single): cache directory for downloaded tiles (default: `cache/`)
- `--no-download` (flag): skip the download stage, use cached tiles
- `--quality` (single): quality setting for export (default: `high`)

The command SHALL load config, resolve the specified layer to its source, and invoke `build_layer()`.

#### Scenario: Build command with minimal arguments
- **WHEN** `cartoload build --sources sources.yaml --layers layers.yaml --layer ch_basemap_25k` is run
- **THEN** the config files are loaded, the layer `ch_basemap_25k` is resolved to its source, and the full pipeline (download, process, export) executes

#### Scenario: Build command with all flags
- **WHEN** `cartoload build --sources swisstopo.yaml --layers switzerland.yaml --layer ch_basemap_25k --exporter garmin-img --bounds 5.9,45.8,10.5,47.8 --zoom 8,9,10,11,12 --output-dir ./out --cache-dir ./cache --quality high` is run
- **THEN** all provided flags override the corresponding layer config values and the pipeline executes with those overrides

#### Scenario: Build command with --no-download
- **WHEN** `cartoload build --sources sources.yaml --layers layers.yaml --layer ch_basemap_25k --no-download` is run
- **THEN** the download stage is skipped and the pipeline processes tiles already present in the cache directory

#### Scenario: Build command with missing layer ID
- **WHEN** `cartoload build --sources sources.yaml --layers layers.yaml --layer nonexistent` is run
- **THEN** a clear error message is displayed indicating that the layer ID was not found in the provided config files, and the command exits with a non-zero code

#### Scenario: Build command with missing config files
- **WHEN** `cartoload build --sources missing.yaml --layers layers.yaml --layer ch_basemap_25k` is run
- **THEN** a clear error message is displayed indicating that the config file does not exist, and the command exits with a non-zero code

### Requirement: Download command

The `download` CLI command SHALL accept `--sources`, `--layers`, `--layer`, `--bounds`, `--zoom`, and `--cache-dir` options. It SHALL execute only the download stage of the pipeline without processing or exporting.

#### Scenario: Download command fetches tiles
- **WHEN** `cartoload download --sources sources.yaml --layers layers.yaml --layer ch_basemap_25k` is run
- **THEN** tiles are downloaded to the cache directory but no processing or export occurs

#### Scenario: Download command with bounds override
- **WHEN** `cartoload download --sources sources.yaml --layers layers.yaml --layer ch_basemap_25k --bounds 7.0,46.0,8.0,47.0` is run
- **THEN** tiles are downloaded only for the specified bounding box

### Requirement: Split command

The `split` CLI command SHALL accept an input `.img` file path and use `gmt` (GMapTool) as a subprocess to split oversized `.img` files that exceed the 4 GB Garmin device limit into region files.

#### Scenario: Split oversized IMG file
- **WHEN** `cartoload split output/ch_basemap_25k.img` is run and the file exceeds 4 GB
- **THEN** `gmt` is invoked as a subprocess to split the file into region-sized `.img` files in the same directory

#### Scenario: Split file that is under size limit
- **WHEN** `cartoload split output/ch_basemap_25k.img` is run and the file is under 4 GB
- **THEN** a message is displayed indicating that splitting is not needed

#### Scenario: Split command with gmt not installed
- **WHEN** `cartoload split output/ch_basemap_25k.img` is run and `gmt` is not found on PATH
- **THEN** a clear error message is displayed indicating that GMapTool (`gmt`) must be installed, and the command exits with a non-zero code

#### Scenario: Split command with non-existent file
- **WHEN** `cartoload split nonexistent.img` is run
- **THEN** a clear error message is displayed indicating that the file does not exist, and the command exits with a non-zero code

### Requirement: Proper error messages

All CLI commands SHALL display user-friendly error messages when errors occur. Domain exceptions (`PipelineError`, `DownloadError`, `ProcessingError`, `ExportError`) SHALL be caught in the CLI layer and converted to `click.ClickException` with actionable messages. Unexpected exceptions SHALL display a brief error message with instructions to report the issue.

#### Scenario: Download error produces user-friendly message
- **WHEN** the pipeline raises a `DownloadError` during a build command
- **THEN** the CLI displays a message like "Download failed for source 'swisstopo_wmts': [original error]" and exits with code 1

#### Scenario: Config validation error produces user-friendly message
- **WHEN** the config loader raises a validation error
- **THEN** the CLI displays the validation error message without a traceback and exits with code 1

#### Scenario: Unexpected exception displays generic message
- **WHEN** an unexpected exception occurs that is not a known domain exception
- **THEN** the CLI displays a brief error message with the exception details and suggests reporting the issue

### Requirement: Progress output

The `build` and `download` commands SHALL display progress information during execution:

- The download stage SHALL show a progress bar indicating the number of tiles downloaded out of the total
- The processing stage SHALL show a status message (e.g., "Processing raster data...")
- The export stage SHALL show a status message (e.g., "Exporting to Garmin IMG...")
- A summary SHALL be printed upon completion with output file path and file size

#### Scenario: Build command shows progress
- **WHEN** `cartoload build` runs the full pipeline
- **THEN** progress information is displayed for each stage: a progress bar during download, status messages during processing and export, and a summary upon completion

#### Scenario: Download command shows progress
- **WHEN** `cartoload download` runs
- **THEN** a progress bar is displayed showing tiles downloaded out of the total tile count
