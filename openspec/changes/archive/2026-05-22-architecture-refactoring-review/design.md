## Context

Cartoload has grown organically through many feature additions. A multi-agent architecture review (5 parallel agents covering architecture, duplication, CLI/config, processor/downloader, and exporter/tests) identified systemic issues:

- **Flat directory structure**: `processor/` has 17 files at one level mixing providers, helpers, and orchestration. `downloader/` similarly mixes sources, legacy downloaders, and helpers.
- **Two parallel hierarchies**: `Source` and `BaseDownloader` overlap in purpose. `STACDownloader` and `GPKGDownloader` are legacy classes that the `Source` abstraction replaced but never deleted.
- **Naming mismatches**: `LayerProvider` lives in `processor/` and is described as "data processor". The package is `downloader/` but the abstraction is `Source`.
- **Redundant prefixes**: `geotiff_provider.py` defines `GeotiffProvider` -- the prefix repeats the directory context.
- **Code duplication**: Tile math reimplemented 6+ times, `_human_size` copied 4 times, test helpers duplicated across 6 files.
- **CLI bloat**: 370-line `build` command mixing argument parsing, business logic, and progress display.

The codebase is on the `develop` branch. This refactoring does not touch user-facing behavior. No backward compatibility needed.

## Goals / Non-Goals

**Goals:**
- Restructure `downloader/` and `processor/` into type-specific subpackages
- Rename consistently: Source → processor → exporter (three clean stages)
- Delete legacy classes superseded by newer abstractions
- Consolidate all duplicated logic into canonical locations
- Fix bugs and naming collisions
- Improve test infrastructure

**Non-Goals:**
- No new features or behavior changes
- No changes to CLI interface (commands, options, output format)
- No external dependency additions
- No changes to Garmin IMG binary format output
- No performance optimization

## Decisions

### D1: Rename `downloader/` to `source/`

**Choice**: `cartoload.downloader` becomes `cartoload.source`.

**Rationale**: The core abstraction is `Source`. `PathSource` doesn't download anything -- it resolves local paths. The package name should reflect the abstraction, not one implementation detail. This also creates a clean three-stage naming: **Source → Processor → Exporter**.

**Structure**:
```
source/
├── __init__.py          # re-exports: Source, StacSource, WmtsSource, PathSource
├── base.py              # Source ABC + registry (renamed from source.py)
├── cache_key.py         # shared helper (unchanged)
├── path.py              # PathSource (renamed from path_source.py)
├── stac/
│   ├── __init__.py      # re-exports: StacSource
│   ├── source.py        # StacSource (renamed from stac_source.py)
│   └── query.py         # STAC query logic (renamed from stac_query.py)
└── wmts/
    ├── __init__.py      # re-exports: WmtsSource, WmtsDownloader
    ├── source.py        # WmtsSource (renamed from wmts_source.py)
    ├── capabilities.py  # (unchanged)
    ├── download.py      # WmtsDownloader (renamed from WMTSDownloader)
    └── tile_grid.py     # (unchanged)
```

**Deleted**: `stac.py` (`STACDownloader`), `gpkg.py` (`GPKGDownloader`), `base.py` (`BaseDownloader`). Any unique logic moves into `StacSource`.

### D2: Rename Provider → Processor throughout

**Choice**: `LayerProvider` → `LayerProcessor`, `GeotiffProvider` → `GeotiffProcessor`, `GpkgProvider` → `GpkgProcessor`, `WmtsProvider` → `WmtsProcessor`. Registry functions: `register_provider` → `register_processor`, `make_provider` → `make_processor`, `get_provider_registry` → `get_processor_registry`.

**Rationale**: The word "Provider" in the `processor/` package is confusing. The class docstring already says "data processor". This creates a consistent mental model: Source (fetch) → Processor (transform) → Exporter (output). `Source` already follows this pattern (`StacSource`, not `StacProvider`).

### D3: Restructure `processor/` with type-specific subpackages

**Choice**: Move type-specific files into `geotiff/`, `gpkg/`, `wmts/` subpackages. Shared utilities stay at top level.

```
processor/
├── __init__.py          # re-exports: LayerProcessor, GeotiffProcessor,
│                        #   GpkgProcessor, WmtsProcessor, make_processor
├── base.py              # LayerProcessor ABC + registry (renamed from provider.py)
├── pipeline.py          # build_target() (renamed from unified_pipeline.py)
├── compositor.py        # shared (unchanged)
├── checkpoint.py        # shared (unchanged)
├── preview.py           # shared (unchanged)
├── summary.py           # shared (renamed from build_summary.py)
├── warp.py              # shared (renamed from rasterio_warp.py)
├── gdal.py              # shared (renamed from raster.py)
├── tile_metadata.py     # shared (unchanged)
├── geotiff/
│   ├── __init__.py      # re-exports: GeotiffProcessor
│   ├── processor.py     # GeotiffProcessor (renamed from geotiff_provider.py)
│   ├── tile_reader.py   # (renamed from geotiff_tile_reader.py)
│   ├── collector.py     # (renamed from geotiff_collector.py)
│   ├── index.py         # (renamed from geotiff_index.py)
│   └── prewarp.py       # (renamed from geotiff_prewarp.py)
├── gpkg/
│   ├── __init__.py      # re-exports: GpkgProcessor
│   ├── processor.py     # GpkgProcessor (renamed from gpkg_provider.py)
│   └── vector_rasterizer.py  # (unchanged)
└── wmts/
    ├── __init__.py      # re-exports: WmtsProcessor
    └── processor.py     # WmtsProcessor (renamed from wmts_provider.py)
```

**Rationale**: From 17 flat files to 6 shared files + 3 focused subpackages. Each source type's processing logic is self-contained. Adding a new type (e.g., MBTiles) is obvious: create `processor/mbtiles/`.

**File renames rationale**:
- `provider.py` → `base.py`: Standard convention for ABCs
- `unified_pipeline.py` → `pipeline.py`: "Unified" is historical
- `rasterio_warp.py` → `warp.py`: "rasterio" is an implementation detail; "warp" describes what it does
- `build_summary.py` → `summary.py`: "build_" prefix is redundant inside `processor/`
- `raster.py` → `gdal.py`: It wraps GDAL CLI tools; "raster" is too vague

### D4: Move `cli_analyze.py` to `analysis/cli.py`

**Choice**: The `analysis/` module already exists with `img_parser.py`, `compare.py`, etc. The CLI for analysis belongs with the module it exposes.

**Rationale**: Keeps all analysis-related code together. `cli.py` imports from it via `from cartoload.analysis.cli import analyze`.

### D5: New `tile_math.py` for all Web Mercator tile coordinate functions

**Choice**: Create `src/cartoload/tile_math.py` as a standalone module.

**Functions**: `lon_to_tile_x`, `lat_to_tile_y`, `tile_x_to_lon`, `tile_y_to_lat`, `compute_bounds_4326`, `bounds_to_tile_coords`.

**Rationale**: Pure computational concern, no heavy dependencies. Replaces 6+ inline implementations.

### D6: `utils.py` for general utilities

**Choice**: Create `src/cartoload/utils.py` with `human_size`, `encode_jpeg`, `ensure_rgba`, `normalize_bands`, and callback type aliases.

**Rationale**: Generic utilities used across the entire codebase. Replaces 4+ copies of `_human_size`, 11 inline JPEG encoding patterns, 4 RGBA normalization patterns.

### D7: Generic `Registry[T]` class

**Choice**: A small generic class that both `source/base.py` and `processor/base.py` instantiate.

```python
class Registry[T]:
    def __init__(self, name: str): ...
    def register(self, key: str, cls: type[T]) -> None: ...
    def resolve(self, key: str) -> type[T]: ...
    def get_all(self) -> dict[str, type[T]]: ...
```

**Rationale**: Identical pattern duplicated in source and processor registries. ~20 lines eliminates real duplication.

### D8: Default `download()` in `LayerProcessor` base class

**Choice**: `GeotiffProcessor` and `GpkgProcessor` have identical `download()` implementations. Move to base class.

**Rationale**: `WmtsProcessor` overrides it; the default serves the common case.

### D9: Fix bugs and dead code

- Add `"xyz"` to `ALLOWED_SOURCE_TYPES`
- Remove dead `--exporter` CLI option
- Fix `download` command to resolve targets (not just layers)
- Replace `sys.exit(1)` with `click.ClickException` in `list_layers`
- Remove duplicate `import shutil` in `cache_clean`
- Rename `pipeline.resolve_source()` to `resolve_source_config()` (disambiguate from `source.resolve_source()`)

### D10: Consolidate test helpers into `tests/helpers.py`

**Choice**: Create `tests/helpers.py` with `make_jpeg`, `write_tile_with_world_file`, `make_tiles_with_bounds`, `solid_rgba`, `solid_rgb`.

**Rationale**: These are defined identically in 3-6 test files each. Centralizing reduces maintenance burden.

## Risks / Trade-offs

- **Large scope** → ~20 files move, ~10 files rename, all imports update. Mitigate by executing in phases: rename package first, then restructure directories, then consolidate code. Run tests after each phase.
- **Legacy class deletion** → `STACDownloader` and `GPKGDownloader` may have callers outside the codebase. Mitigate: project is pre-1.0, no backward compat needed per user requirement.
- **Subtle behavioral differences in tile math** → The 6+ implementations have minor variations (clamping, edge cases). Mitigate by writing tests for canonical versions first.
- **`BaseDownloader` removal** → `WmtsDownloader` currently inherits from `BaseDownloader`. Mitigate: `WmtsDownloader` becomes a standalone class used internally by `WmtsSource`; it doesn't need the ABC.
- **Merge conflicts** → The `develop` branch has 40+ modified files. Mitigate by batching changes logically and committing after each phase.
