## ADDED Requirements

### Requirement: Root justfile imports tasks module
The project SHALL have a root `.justfile` that imports `tasks/main.just`.

#### Scenario: Just listing recipes
- **WHEN** `just --list` is run from the repo root
- **THEN** all recipes from `tasks/main.just` are listed

### Requirement: Core development recipes
`tasks/main.just` SHALL provide the following recipes:
- `default` — lists available recipes (`just --list`)
- `install` — runs `uv sync --all-groups`
- `lint` — runs `ruff check` and `ruff format --check` on `src/` and `tests/`
- `typecheck` — runs `ty check src/`
- `test` — runs `uv run pytest`
- `test-cov` — runs pytest with coverage on `src/cartoload`
- `fmt` — runs `ruff format` and `ruff check --fix` on `src/` and `tests/`

#### Scenario: Install all dependencies
- **WHEN** `just install` is run
- **THEN** `uv sync --all-groups` executes and installs all dependency groups

#### Scenario: Run linter
- **WHEN** `just lint` is run
- **THEN** ruff check and ruff format check run against `src/` and `tests/`

#### Scenario: Run type checker
- **WHEN** `just typecheck` is run
- **THEN** `ty check src/` executes

#### Scenario: Run tests
- **WHEN** `just test` is run
- **THEN** pytest runs and discovers tests in `tests/`

#### Scenario: Format code
- **WHEN** `just fmt` is run
- **THEN** ruff auto-formats and auto-fixes all files in `src/` and `tests/`

### Requirement: Documentation recipes
`tasks/main.just` SHALL provide:
- `docs` — serves docs locally with `zensical serve docs/`
- `docs-build` — builds docs for publishing with `zensical build docs/`

#### Scenario: Serve docs locally
- **WHEN** `just docs` is run
- **THEN** zensical serves the documentation site on the default port

### Requirement: Docker recipes
`tasks/main.just` SHALL provide:
- `docker-build` — builds the Docker image tagged as `cartoload`

#### Scenario: Build Docker image
- **WHEN** `just docker-build` is run
- **THEN** `docker build -t cartoload .` executes

### Requirement: Build and release recipes
`tasks/main.just` SHALL provide:
- `build layer` — runs `uv run cartoload build` with example config paths and the given layer ID
- `build-ch-25k` — convenience recipe for the Switzerland 1:25k basemap
- `bump part="patch"` — runs `bump2version` with the given part
- `changelog` — runs `git-cliff -o CHANGELOG.md`

#### Scenario: Build a specific layer via just
- **WHEN** `just build ch_basemap_25k` is run
- **THEN** the cartoload CLI is invoked with example swisstopo configs and the layer ID `ch_basemap_25k`

#### Scenario: Bump version
- **WHEN** `just bump minor` is run
- **THEN** `bump2version minor` executes
