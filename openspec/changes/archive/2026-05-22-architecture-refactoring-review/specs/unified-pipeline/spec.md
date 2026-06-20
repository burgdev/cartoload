## MODIFIED Requirements

### Requirement: CLI build command delegates to orchestration function
The `build` CLI command SHALL be a thin wrapper that parses Click arguments and delegates to a pipeline-level orchestration function in `processor/pipeline.py` (renamed from `unified_pipeline.py`). Business logic (config resolution, source instantiation, build execution) SHALL live in the pipeline layer.

#### Scenario: Build command calls orchestration function
- **WHEN** `cartoload build -c config.yaml -l my_layer` is run
- **THEN** the CLI parses arguments and calls `build_target()` in `processor/pipeline.py`

#### Scenario: Business logic testable without CLI
- **WHEN** `build_target()` is called directly with a valid config
- **THEN** it executes the build without requiring Click context

### Requirement: Download command resolves targets and layers
The `download` command SHALL resolve the `-l` argument by checking both `config.targets` and `config.layers`, matching the behavior of the `build` command.

#### Scenario: Download with target name
- **WHEN** `cartoload download -l target_name` is run and `target_name` exists in `config.targets`
- **THEN** the command resolves the target and downloads its source data

### Requirement: List command uses Click exceptions
The `list` command SHALL use `raise click.ClickException(...)` instead of `sys.exit(1)` for error handling.

#### Scenario: No config files provided
- **WHEN** `cartoload list` is run without any config files
- **THEN** a Click exception is raised with a usage hint, not `sys.exit(1)`

## ADDED Requirements

### Requirement: Dead CLI options removed
The unused `--exporter` option on the `build` command SHALL be removed.

#### Scenario: Build without --exporter option
- **WHEN** `cartoload build --help` is run
- **THEN** no `--exporter` option is listed

### Requirement: ALLOWED_SOURCE_TYPES includes xyz
The `ALLOWED_SOURCE_TYPES` set in `config.py` SHALL include `"xyz"`.

#### Scenario: XYZ source type validates
- **WHEN** a source config with `type: xyz` is loaded
- **THEN** it passes validation without error

### Requirement: Default download in LayerProcessor base
The `LayerProcessor` base class (renamed from `LayerProvider`) SHALL provide a default `download()` implementation. `GeotiffProcessor` and `GpkgProcessor` SHALL use this default.

#### Scenario: GeotiffProcessor uses base download
- **WHEN** `GeotiffProcessor.download()` is called
- **THEN** it uses the base class implementation without its own override
