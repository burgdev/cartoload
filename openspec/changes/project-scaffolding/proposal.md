## Why

The cartoload repository is currently empty — only openspec scaffolding exists. Before any feature development can begin, the project needs its foundational structure: build configuration, task runner, linting/formatting, CI/CD, Docker, and the initial source package layout. This scaffolding establishes the development workflow so all subsequent changes (downloader, processor, exporters) have a working project to build on.

## What Changes

- Create `pyproject.toml` with Python 3.11+, hatchling build, runtime deps (click, PyYAML, requests, pystac-client, numpy, rich), and dev/test/docs dependency groups (ruff, ty, pytest, pre-commit, bump2version, git-cliff, zensical)
- Create modular `justfile` setup: root `.justfile` importing `tasks/main.just` with recipes for install, lint, typecheck, test, fmt, docs, docker-build, build, bump, changelog — following the django-admin-runner pattern
- Create `.pre-commit-config.yaml` with ruff, prettier, and basic hooks
- Create `.gitignore` for Python projects (uv, __pycache__, .egg-info, cache/, output/, site/, etc.)
- Create `Dockerfile` (GDAL, Java, osmium, gmt, mkgmap, uv) and `docker-compose.yml`
- Create `src/cartoload/` package skeleton with `__init__.py`, `cli.py` (click entry point), `config.py` (dataclasses), `pipeline.py`, and empty `downloader/`, `processor/`, `exporters/` sub-packages
- Create `.bumpversion.cfg` for version management
- Create GitHub Actions CI workflows: `ci.yml` (lint + typecheck + test on PR) and `publish.yml` (PyPI publish on tag)
- Create `cliff.toml` for changelog generation
- Create `docs/` with `zensical.toml` and placeholder markdown files
- Create `examples/configs/sources/` and `examples/configs/layers/` with example YAML configs (swisstopo, basemap.at, IGN France)
- Create `tests/` with `conftest.py` and placeholder test files
- Create `README.md` with project overview, install, and usage

## Capabilities

### New Capabilities

- `project-config`: Build system (pyproject.toml, hatchling), dependency management (uv), version bumping, and changelog generation configuration
- `justfile-tasks`: Modular justfile setup with tasks for install, lint, typecheck, test, format, docs, docker, build, release — following the django-admin-runner `tasks/*.just` pattern
- `ci-cd`: GitHub Actions workflows for continuous integration (ruff, ty, pytest) and PyPI publishing on version tags
- `docker`: Dockerfile with system deps (GDAL, Java, osmium, gmt, mkgmap) and docker-compose for local development
- `package-skeleton`: Initial `src/cartoload/` package structure with CLI entry point, config dataclasses, pipeline stub, and sub-packages for downloader, processor, exporters
- `example-configs`: Pre-configured source and layer YAML files for swisstopo, basemap.at, and IGN France
- `docs-site`: Zensical documentation site with nav structure and placeholder pages

### Modified Capabilities

_(none — this is the first change)_

## Impact

- **Repository**: Adds ~30 files across the full project structure
- **Dependencies**: Runtime deps (click, PyYAML, requests, pystac-client, numpy, rich); dev deps (ruff, ty, pytest, pre-commit, bump2version, git-cliff, zensical)
- **CI/CD**: New GitHub Actions workflows — `ci.yml` runs on PRs, `publish.yml` runs on tag push
- **Docker**: New Dockerfile requiring GDAL, Java, osmium-tool system packages
- **Tooling**: Requires `uv`, `just`, and `pre-commit` installed locally for development
