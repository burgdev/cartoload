## ADDED Requirements

### Requirement: Source package layout

The project SHALL have `src/cartoload/` with the following files:

- `__init__.py` — exports `__version__`
- `cli.py` — Click group with `main()` entry point and stub `build`, `download`, `split`, `list` commands
- `config.py` — `SourceConfig` and `LayerConfig` dataclasses
- `pipeline.py` — stub `build_layer()` async function
- `downloader/__init__.py`, `downloader/base.py`, `downloader/wmts.py`, `downloader/geotiff.py`, `downloader/gpkg.py` — downloader sub-package with abstract base and stub implementations
- `processor/__init__.py`, `processor/raster.py` — processor sub-package with stub
- `exporters/__init__.py`, `exporters/base.py`, `exporters/garmin_img.py`, `exporters/garmin_img_vec.py` — exporter sub-package with abstract base and stub implementations

#### Scenario: Package is importable

- **WHEN** `python -c "import cartoload; print(cartoload.__version__)"` is run after install
- **THEN** it prints `0.1.0`

#### Scenario: CLI responds to --help

- **WHEN** `cartoload --help` is run
- **THEN** a help message listing `build`, `download`, `split`, `list` commands is displayed

### Requirement: CLI commands are registered

The `cli.py` SHALL define a Click group with the following subcommands (stubs that accept the documented flags but raise `NotImplementedError` or print a placeholder):

- `build` — with `--sources`, `--layers`, `--layer`, `--exporter`, `--bounds`, `--zoom`, `--output-dir`, `--cache-dir`, `--no-download`, `--quality` options
- `download` — download source data only
- `split` — split oversized `.img` into region files
- `list` — list all layers from provided config files

#### Scenario: Build command accepts documented flags

- **WHEN** `cartoload build --help` is run
- **THEN** the help text shows all documented options: `--sources`, `--layers`, `--layer`, `--exporter`, `--bounds`, `--zoom`, `--output-dir`, `--cache-dir`, `--no-download`, `--quality`

#### Scenario: List command lists layers

- **WHEN** `cartoload list --help` is run
- **THEN** the help text shows the list command usage

### Requirement: Config dataclasses

`config.py` SHALL define `SourceConfig` and `LayerConfig` as plain Python dataclasses (not pydantic models) with fields matching the YAML config schema from SPEC.md.

#### Scenario: SourceConfig from dict

- **WHEN** a `SourceConfig` is created from a source YAML dictionary
- **THEN** it exposes `id`, `type`, `url_template`, `attribution`, `rate_limit_ms`, `max_threads`, `stac_url` fields

#### Scenario: LayerConfig from dict

- **WHEN** a `LayerConfig` is created from a layer YAML dictionary
- **THEN** it exposes `id`, `name`, `description`, `type`, `source`, `zoom_levels`, `exporter`, `output` fields
