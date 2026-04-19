## ADDED Requirements

### Requirement: pyproject.toml with build system and dependencies
The project SHALL have a `pyproject.toml` at the repository root with:
- `[project]` section: name `cartoload`, version `0.1.0`, `requires-python >= 3.11`, MIT license, GIS topic classifiers
- Runtime dependencies: `click>=8.0`, `PyYAML>=6.0`, `requests>=2.28`, `pystac-client>=0.6`, `numpy>=1.24`, `rich>=13.0`
- `[project.scripts]` entry point: `cartoload = "cartoload.cli:main"`
- `[dependency-groups]` for dev (ruff, ty, pre-commit, bump2version, git-cliff, deptry), test (pytest, pytest-cov, pytest-xdist), docs (zensical)
- `[build-system]` using hatchling
- `[tool.hatch.build.targets.wheel]` with `packages = ["src/cartoload"]`
- `[tool.ruff]` with src `["src"]`, line-length 100, lint rules E, F, I, UP
- `[tool.pytest.ini_options]` with `testpaths = ["tests"]`

#### Scenario: Project installs with uv sync
- **WHEN** a developer runs `uv sync --all-groups`
- **THEN** all runtime, dev, test, and docs dependencies are installed and the `cartoload` CLI entry point is available

#### Scenario: Build produces a wheel
- **WHEN** `uv build` is run
- **THEN** a wheel containing the `cartoload` package from `src/` is produced

### Requirement: Version bumping configuration
The project SHALL have a `.bumpversion.cfg` that bumps the version in both `pyproject.toml` and `src/cartoload/__init__.py`.

#### Scenario: Bump patch version
- **WHEN** `uv run bump2version patch` is executed
- **THEN** the version is incremented in both `pyproject.toml` and `src/cartoload/__init__.py`

### Requirement: Changelog generation configuration
The project SHALL have a `cliff.toml` configured for GitHub-based changelog generation with PR label categorization (BREAKING, Features, Fixes, Refactor, Docs, Dependencies, Others).

#### Scenario: Generate changelog
- **WHEN** `uv run git-cliff -o CHANGELOG.md` is executed
- **THEN** a changelog is generated from GitHub PRs, grouped by label categories

### Requirement: Git ignore file
The project SHALL have a `.gitignore` covering Python artifacts (`__pycache__/`, `*.egg-info/`, `dist/`, `build/`), uv files (`.python-version`, `uv.lock`), project-specific dirs (`cache/`, `output/`, `site/`), and editor/OS files.

#### Scenario: Build artifacts are ignored
- **WHEN** a build or test run produces `__pycache__/`, `*.egg-info/`, or `dist/` files
- **THEN** `git status` does not show them as untracked
