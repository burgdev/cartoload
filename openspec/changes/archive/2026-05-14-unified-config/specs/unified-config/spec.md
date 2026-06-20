## ADDED Requirements

### Requirement: Unified config file format
A config file SHALL be a YAML document that may contain any combination of the following top-level keys: `includes`, `sources`, `layers`, `bounds`, `settings`. All sections are optional. A file containing only `sources:` is valid.

#### Scenario: Config file with all sections
- **WHEN** a config file contains `includes`, `sources`, `layers`, and `bounds` keys
- **THEN** the loader SHALL parse all sections and return them as a unified result

#### Scenario: Config file with only sources
- **WHEN** a config file contains only a `sources` key (no `layers` or `bounds`)
- **THEN** the loader SHALL return the sources with no layers and no bounds

#### Scenario: Config file with only layers
- **WHEN** a config file contains only a `layers` key (no `sources`)
- **THEN** the loader SHALL return the layers with no sources

#### Scenario: Empty config file
- **WHEN** a config file contains no recognized top-level keys
- **THEN** the loader SHALL return empty sources, empty layers, and no bounds

### Requirement: Include mechanism
A config file SHALL support an `includes` key containing a list of file paths. Each path SHALL be resolved relative to the directory of the file that declares it.

#### Scenario: Single include
- **WHEN** a config file declares `includes: ["../sources/swisstopo.yaml"]`
- **THEN** the loader SHALL resolve the path relative to the declaring file's directory and load it

#### Scenario: Multiple includes in order
- **WHEN** a config file declares `includes: ["a.yaml", "b.yaml"]`
- **THEN** the loader SHALL load `a.yaml` first, then `b.yaml`, and merge them in that order before merging the current file's sections

#### Scenario: Nested includes
- **WHEN** an included file itself declares `includes`
- **THEN** the loader SHALL recursively load those includes (depth-first) before merging the including file's sections

#### Scenario: Missing include file
- **WHEN** a declared include path does not exist
- **THEN** the loader SHALL raise `FileNotFoundError`

### Requirement: Circular include detection
The loader SHALL detect circular include references and raise an error.

#### Scenario: Direct circular include
- **WHEN** file A includes file B and file B includes file A
- **THEN** the loader SHALL raise `ValueError` with a message indicating the circular reference

#### Scenario: Indirect circular include
- **WHEN** file A includes file B, file B includes file C, and file C includes file A
- **THEN** the loader SHALL raise `ValueError` with a message indicating the circular reference

### Requirement: Merge semantics
When multiple files (via includes or multiple CLI flags) define the same source or layer key, the last definition SHALL win. A warning SHALL be logged for duplicate keys.

#### Scenario: Duplicate source key across includes
- **WHEN** included file defines `sources.foo` and the including file also defines `sources.foo`
- **THEN** the including file's definition SHALL be used and a warning SHALL be logged

#### Scenario: Duplicate layer key across CLI flags
- **WHEN** `-C a.yaml -C b.yaml` is used and both define `layers.bar`
- **THEN** `b.yaml`'s definition SHALL be used and a warning SHALL be logged

#### Scenario: Duplicate bounds across files
- **WHEN** multiple files define `bounds`
- **THEN** the last file's bounds SHALL be used and a warning SHALL be logged

### Requirement: CLI uses single config flag
The CLI SHALL accept `-c/--config` as a repeatable flag for specifying config files. The `-S/--sources` and `-L/--layers` flags SHALL be removed from all commands (`build`, `download`, `list`). The `--cache-dir` short flag SHALL change from `-c` to `-C`.

#### Scenario: Single config file
- **WHEN** user runs `cartoload build -c cartoload.yaml -l ch_basemap`
- **THEN** the command SHALL load `cartoload.yaml` as a unified config

#### Scenario: Multiple config files
- **WHEN** user runs `cartoload build -c base.yaml -c overrides.yaml -l ch_basemap`
- **THEN** the command SHALL load both files and merge them in order (last wins)

#### Scenario: Old flags removed
- **WHEN** user runs `cartoload build -S sources.yaml -L layers.yaml -l foo`
- **THEN** the CLI SHALL report that `-S` and `-L` are unrecognized options

#### Scenario: Cache dir uses -C
- **WHEN** user runs `cartoload build -c config.yaml -C /tmp/cache -l foo`
- **THEN** the command SHALL use `/tmp/cache` as the cache directory

### Requirement: Settings section
A config file SHALL support a `settings:` section containing runtime defaults. Supported keys: `cache_dir`, `output_dir`, `executor`, `quality`, `rate_limit_ms`. Settings merge at the key level across includes (later wins).

#### Scenario: Settings in config file
- **WHEN** a config file contains `settings: { cache_dir: "./my_cache", quality: 85 }`
- **THEN** the loader SHALL return these as resolved settings

#### Scenario: Settings merge across includes
- **WHEN** included file defines `settings: { cache_dir: "./a" }` and including file defines `settings: { quality: 90 }`
- **THEN** the merged settings SHALL contain `cache_dir: "./a"` and `quality: 90`

#### Scenario: Settings absent from config
- **WHEN** no config file defines a `settings` section
- **THEN** all settings SHALL fall back to built-in defaults

### Requirement: Environment variable override for settings
Each settings key SHALL be overridable via an environment variable named `CARTOLOAD_<UPPER_SNAKE_KEY>`. Environment variables take precedence over config file settings but are overridden by CLI flags.

Resolution order (highest priority first):
1. CLI flag
2. Environment variable (`CARTOLOAD_CACHE_DIR`, etc.)
3. Config file `settings:` section
4. Built-in default

#### Scenario: Env var overrides config setting
- **WHEN** config defines `settings: { cache_dir: "./cache" }` and env `CARTOLOAD_CACHE_DIR=/tmp/cache` is set
- **THEN** the resolved `cache_dir` SHALL be `/tmp/cache`

#### Scenario: CLI flag overrides env var
- **WHEN** env `CARTOLOAD_QUALITY=50` is set and user passes `--quality 90`
- **THEN** the resolved `quality` SHALL be `90`

#### Scenario: Env var with no config setting
- **WHEN** no config file defines `settings.quality` but env `CARTOLOAD_QUALITY=70` is set
- **THEN** the resolved `quality` SHALL be `70`

### Requirement: Source reference resolution across includes
Layer source references (`ref:` in source fields) SHALL resolve against the merged pool of sources from all included files and the current file.

#### Scenario: Layer references source from included file
- **WHEN** a config includes `sources/swisstopo.yaml` (which defines `swisstopo_wmts`) and the config's layer references `ref: swisstopo_wmts`
- **THEN** the reference SHALL resolve successfully
