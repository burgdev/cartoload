## Why

A multi-agent architecture review identified pervasive code duplication, unclear module boundaries, and significant separation-of-concerns violations. Additionally, the directory structure is flat and messy -- especially `processor/` with 17 files at one level -- making it hard to find related code. The project has two parallel class hierarchies in the downloader layer (`Source` vs `BaseDownloader`), inconsistent naming ("Provider" in the `processor/` package), and redundant file prefixes. This refactoring consolidates shared logic, reorganizes into type-specific subpackages, renames everything consistently, and fixes known bugs.

## What Changes

### Restructuring

- **Rename `downloader/` to `source/`**: The core abstraction is `Source`, not "downloader" -- `PathSource` doesn't download anything. Move each source type into its own subpackage (`source/stac/`, `source/wmts/`).
- **Restructure `processor/` with subpackages**: Move type-specific files into `processor/geotiff/`, `processor/gpkg/`, `processor/wmts/`. Shared utilities stay at top level. Reduces 17 flat files to 6 shared + 3 focused subpackages.
- **Move `cli_analyze.py` to `analysis/cli.py`**: The analysis module already exists as `analysis/`; the CLI belongs with it.

### Renaming

- **Provider → Processor**: `LayerProvider` → `LayerProcessor`, `GeotiffProvider` → `GeotiffProcessor`, `GpkgProvider` → `GpkgProcessor`, `WmtsProvider` → `WmtsProcessor`. Matches the package name.
- **Remove redundant file prefixes**: `geotiff_provider.py` → `geotiff/processor.py`, `wmts_source.py` → `wmts/source.py`, `stac_source.py` → `stac/source.py`, etc.
- **Clean up pipeline naming**: `unified_pipeline.py` → `pipeline.py` (the "unified" qualifier is historical). `rasterio_warp.py` → `warp.py` ("rasterio" is an implementation detail). `build_summary.py` → `summary.py`. `raster.py` → `gdal.py` (it wraps GDAL CLI tools). `WMTSDownloader` → `WmtsDownloader` (consistent casing).
- **Delete legacy downloader classes**: `STACDownloader`, `GPKGDownloader`, and `BaseDownloader` are superseded by the `Source` abstraction. Move any unique logic into `StacSource`, then delete.

### Deduplication

- **Extract `tile_math.py`**: Consolidate 6+ reimplementations of Web Mercator tile coordinate functions into a single canonical module.
- **Extract shared utilities**: Consolidate `_human_size` (4 copies), JPEG encoding helpers (11 call sites), RGBA normalization (4 call sites), band normalization, and shared type aliases.
- **Generalize registry pattern**: Extract a `Registry[T]` class used by both source and processor registries.
- **Add default `download()` to `LayerProcessor` base class**: Eliminates identical boilerplate in `GeotiffProcessor` and `GpkgProcessor`.

### Bug fixes

- **Fix `ALLOWED_SOURCE_TYPES`**: Add missing `"xyz"`.
- **Fix `download` command**: Resolve `-l` against both targets and layers (matching `build`).
- **Remove dead `--exporter` CLI option**: Accepted but never used.
- **Fix `list_layers`**: Use `click.ClickException` instead of `sys.exit(1)`.

### Test infrastructure

- **Consolidate test helpers**: Move `_make_jpeg` (6 copies), `_write_tile_with_world_file` (3 copies), and other duplicated helpers into `tests/helpers.py`.

## Capabilities

### New Capabilities
- `shared-tile-math`: Canonical Web Mercator tile coordinate functions in `tile_math.py`
- `shared-utilities`: Common utility functions (`human_size`, `encode_jpeg`, `ensure_rgba`, `normalize_bands`) and type aliases in `utils.py`
- `generic-registry`: A reusable `Registry[T]` class for source and processor type registries
- `package-restructure`: Directory reorganization with type-specific subpackages and consistent naming

### Modified Capabilities
- `unified-pipeline`: Renamed to `processor/pipeline.py`; Provider → Processor naming; extract CLI orchestration; fix `resolve_source` collision; fix `download` command target resolution
- `source-provider-registry`: Refactor to use generic `Registry[T]`; rename `downloader/` to `source/`; delete legacy downloader classes; rename `*Provider` registry functions to `*Processor`

## Impact

- **Package rename**: `cartoload.downloader` → `cartoload.source` (all internal imports change)
- **Class renames**: `LayerProvider` → `LayerProcessor`, `GeotiffProvider` → `GeotiffProcessor`, `GpkgProvider` → `GpkgProcessor`, `WmtsProvider` → `WmtsProcessor`, `WMTSDownloader` → `WmtsDownloader`
- **Deleted classes**: `BaseDownloader`, `STACDownloader`, `GPKGDownloader`
- **File moves**: ~20 files move to new locations; file renames for ~10 files
- **Test files**: All test imports update. Duplicated helpers consolidated into `tests/helpers.py`.
- **New files**: `tile_math.py`, `utils.py`, `tests/helpers.py`, multiple `__init__.py` files for subpackages
- **CLI interface unchanged**: No user-facing behavior changes
- **Dependencies**: No new external dependencies
