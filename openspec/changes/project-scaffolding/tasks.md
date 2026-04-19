## 1. Project Configuration Files

- [x] 1.1 Create `pyproject.toml` with `[project]` metadata, runtime deps, `[project.scripts]` entry point, `[dependency-groups]` (dev/test/docs), `[build-system]` with hatchling, `[tool.ruff]` config, `[tool.pytest.ini_options]`, and `[tool.hatch.build]` targets
- [x] 1.2 Create `.bumpversion.cfg` for version bumping in `pyproject.toml` and `src/cartoload/__init__.py`
- [x] 1.3 Create `cliff.toml` for GitHub-based changelog generation with PR label categorization
- [x] 1.4 Create `.gitignore` covering Python artifacts, uv files, project dirs (cache/, output/, site/), and editor/OS files
- [x] 1.5 Create `.pre-commit-config.yaml` with pre-commit-hooks (case-conflict, merge-conflict, TOML, YAML, end-of-file, trailing-whitespace), ruff (lint + format), and prettier

## 2. Justfile Task Runner

- [x] 2.1 Create root `.justfile` that imports `tasks/main.just`
- [x] 2.2 Create `tasks/main.just` with `default`, `install`, `lint`, `typecheck`, `test`, `test-cov`, `fmt`, `docs`, `docs-build`, `docker-build`, `build`, `build-ch-25k`, `bump`, and `changelog` recipes

## 3. Package Skeleton

- [x] 3.1 Create `src/cartoload/__init__.py` with `__version__ = "0.1.0"`
- [x] 3.2 Create `src/cartoload/cli.py` with Click group (`main`) and stub subcommands: `build`, `download`, `split`, `list` — `build` accepting all documented CLI flags (`--sources`, `--layers`, `--layer`, `--exporter`, `--bounds`, `--zoom`, `--output-dir`, `--cache-dir`, `--no-download`, `--quality`)
- [x] 3.3 Create `src/cartoload/config.py` with `SourceConfig` and `LayerConfig` dataclasses matching the YAML config schema
- [x] 3.4 Create `src/cartoload/pipeline.py` with stub `async build_layer()` function
- [x] 3.5 Create downloader sub-package: `src/cartoload/downloader/__init__.py`, `base.py` (abstract base), `wmts.py` (stub), `geotiff.py` (stub), `gpkg.py` (stub)
- [x] 3.6 Create processor sub-package: `src/cartoload/processor/__init__.py`, `raster.py` (stub)
- [x] 3.7 Create exporters sub-package: `src/cartoload/exporters/__init__.py`, `base.py` (BaseExporter abstract class), `garmin_img.py` (stub), `garmin_img_vec.py` (stub)

## 4. Docker

- [x] 4.1 Create `Dockerfile` based on `python:3.12-slim-bookworm` with system deps (GDAL, Java, osmium, gmt, mkgmap), uv binary, app copy, `uv sync --no-dev`, and cartoload entrypoint
- [x] 4.2 Create `docker-compose.yml` with cartoload service, volume mounts (cache/, output/, examples/configs/), and environment variables (WMTS_DELAY_MS, WMTS_THREADS)

## 5. Example Configs

- [x] 5.1 Create `examples/configs/sources/swisstopo.yaml` with `swisstopo_wmts` (WMTS) and `swisstopo_stac` (GeoTIFF/STAC) source definitions
- [x] 5.2 Create `examples/configs/sources/basemap_at.yaml` with `basemap_at_wmts` source definition
- [x] 5.3 Create `examples/configs/sources/france_ign.yaml` with `ign_wmts` source definition
- [x] 5.4 Create `examples/configs/layers/switzerland.yaml` with bounds and layers: `ch_basemap_25k`, `ch_basemap_10k`, `ch_steepness`
- [x] 5.5 Create `examples/configs/layers/austria.yaml` with bounds and at least one layer referencing `basemap_at_wmts`
- [x] 5.6 Create `examples/configs/layers/france.yaml` with bounds and at least one layer referencing `ign_wmts`

## 6. Documentation

- [x] 6.1 Create `docs/zensical.toml` with project config, site URL, and full navigation structure
- [x] 6.2 Create documentation markdown placeholders: `index.md`, `getting-started.md`, `configuration/sources.md`, `configuration/layers.md`, `configuration/style.md`, `exporters/garmin-img.md`, `exporters/garmin-img-vector.md`, `exporters/adding-exporters.md`, `cli.md`
- [x] 6.3 Create `README.md` with project overview, installation, minimal usage, docs link, and MIT license

## 7. CI/CD

- [x] 7.1 Create `.github/workflows/ci.yml` — runs on push/PR, uses uv, runs lint + typecheck + test
- [x] 7.2 Create `.github/workflows/publish.yml` — runs on tag push (v*), builds and publishes to PyPI

## 8. Tests

- [x] 8.1 Create `tests/conftest.py` with basic pytest fixtures
- [x] 8.2 Create `tests/test_config.py` with tests for `SourceConfig` and `LayerConfig` dataclass instantiation
- [x] 8.3 Create `tests/test_cli.py` with test that `cartoload --help` succeeds and shows expected commands

## 9. Verification

- [x] 9.1 Run `uv sync --all-groups` and verify all dependencies install
- [x] 9.2 Run `just lint` and verify ruff passes on all files
- [x] 9.3 Run `just typecheck` and verify ty passes
- [x] 9.4 Run `just test` and verify all tests pass
- [x] 9.5 Run `cartoload --help` and verify CLI entry point works
