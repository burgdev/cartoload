## ADDED Requirements

### Requirement: Source package replaces downloader
The `cartoload.downloader` package SHALL be renamed to `cartoload.source`. The core abstraction is `Source` -- `PathSource` does not download anything. All internal imports SHALL be updated.

#### Scenario: Import Source from new package
- **WHEN** code does `from cartoload.source import Source`
- **THEN** the `Source` ABC is available

#### Scenario: Old import path removed
- **WHEN** code attempts `from cartoload.downloader import ...`
- **THEN** an `ImportError` is raised

### Requirement: Source types organized in subpackages
Each source type SHALL have its own subpackage under `source/`:
- `source/stac/` — `StacSource` + STAC query logic
- `source/wmts/` — `WmtsSource` + `WmtsDownloader` + capabilities + tile grid
- `source/path.py` — `PathSource` (generic, stays top-level)

#### Scenario: Import StacSource from subpackage
- **WHEN** code does `from cartoload.source.stac import StacSource`
- **THEN** `StacSource` is available

#### Scenario: Import from top-level __init__
- **WHEN** code does `from cartoload.source import StacSource`
- **THEN** `StacSource` is available (re-exported from subpackage)

### Requirement: Redundant file prefixes removed
Files SHALL drop redundant type prefixes when inside their type subpackage:
- `stac_source.py` → `stac/source.py`
- `wmts_source.py` → `wmts/source.py`
- `stac_query.py` → `stac/query.py`
- `path_source.py` → `path.py`

#### Scenario: File names match their role
- **WHEN** navigating `source/stac/`
- **THEN** files are named `source.py`, `query.py` (not `stac_source.py`, `stac_query.py`)

### Requirement: Legacy downloader classes deleted
`BaseDownloader`, `STACDownloader`, and `GPKGDownloader` SHALL be deleted. Any unique logic in `STACDownloader` and `GPKGDownloader` SHALL be absorbed into `StacSource`. `WmtsDownloader` SHALL become a standalone class (no longer inheriting `BaseDownloader`).

#### Scenario: No BaseDownloader in codebase
- **WHEN** searching for `class BaseDownloader`
- **THEN** no results are found

#### Scenario: WmtsDownloader still works standalone
- **WHEN** `WmtsDownloader` is instantiated
- **THEN** it functions correctly without `BaseDownloader` inheritance

### Requirement: WMTSDownloader renamed to WmtsDownloader
`WMTSDownloader` SHALL be renamed to `WmtsDownloader` for consistent casing with `WmtsSource`.

#### Scenario: Consistent casing
- **WHEN** searching for WmtsDownloader
- **THEN** the class name uses consistent PascalCase matching `WmtsSource`

### Requirement: Processor package restructured with type subpackages
The `processor/` package SHALL organize type-specific files into subpackages:
- `processor/geotiff/` — `GeotiffProcessor` + tile reader + collector + index + prewarp
- `processor/gpkg/` — `GpkgProcessor` + vector rasterizer
- `processor/wmts/` — `WmtsProcessor`

Shared utilities (`compositor`, `checkpoint`, `preview`, `summary`, `warp`, `gdal`, `tile_metadata`) stay at top level.

#### Scenario: GeotiffProcessor in subpackage
- **WHEN** navigating `processor/geotiff/`
- **THEN** `processor.py` contains `GeotiffProcessor`, with helpers `tile_reader.py`, `collector.py`, `index.py`, `prewarp.py`

#### Scenario: Import from top-level
- **WHEN** code does `from cartoload.processor import GeotiffProcessor`
- **THEN** it is available (re-exported from subpackage)

### Requirement: Provider renamed to Processor
All "Provider" names SHALL become "Processor": `LayerProvider` → `LayerProcessor`, `GeotiffProvider` → `GeotiffProcessor`, `GpkgProvider` → `GpkgProcessor`, `WmtsProvider` → `WmtsProcessor`. Registry functions: `register_provider` → `register_processor`, `make_provider` → `make_processor`, `get_provider_registry` → `get_processor_registry`.

#### Scenario: Consistent Processor naming
- **WHEN** searching for `class.*Provider`
- **THEN** no results are found (all renamed to `*Processor`)

### Requirement: Processor file renames for clarity
Processor files SHALL be renamed:
- `provider.py` → `base.py` (LayerProcessor ABC)
- `unified_pipeline.py` → `pipeline.py` ("unified" is historical)
- `rasterio_warp.py` → `warp.py` ("rasterio" is an implementation detail)
- `build_summary.py` → `summary.py` (redundant prefix)
- `raster.py` → `gdal.py` (it wraps GDAL CLI tools)
- `geotiff_*.py` → `geotiff/*.py` with prefix removed (e.g., `geotiff_tile_reader.py` → `geotiff/tile_reader.py`)

#### Scenario: Clear file names
- **WHEN** navigating `processor/`
- **THEN** top-level files have clear, concise names without redundant prefixes

### Requirement: cli_analyze.py moved to analysis package
`cli_analyze.py` SHALL move from the top-level package to `analysis/cli.py`. The `cli.py` main module SHALL import it from the new location.

#### Scenario: Analysis CLI in analysis package
- **WHEN** navigating `analysis/`
- **THEN** `cli.py` contains the `analyze` command group

#### Scenario: Main CLI still works
- **WHEN** `cartoload analyze img info <file>` is run
- **THEN** it works identically to before
