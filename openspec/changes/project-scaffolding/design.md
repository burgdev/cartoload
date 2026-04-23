## Context

The cartoload repository is empty — only `.claude/` and `openspec/` scaffolding exist. The SPEC.md defines a CLI tool + Python library for converting geodata (WMTS, GeoTIFF, vector) into Garmin `.img` maps. This change establishes the foundational project structure so feature development can begin.

The django-admin-runner repo provides the proven pattern for: `src/` layout with hatchling, modular `tasks/*.just` files, `uv` for dependency management, `ruff` for linting/formatting, `pyright`/`ty` for type checking, `pre-commit` hooks, `git-cliff` for changelogs, GitHub Actions CI/CD, and Zensical for docs.

Key differences from django-admin-runner:

- **Type checker**: SPEC.md specifies `ty` (not `pyright`) — a newer Rust-based type checker from the Astral team
- **Runtime deps**: heavier — click, PyYAML, requests, pystac-client, numpy, rich
- **System deps**: GDAL, Java, osmium-tool, gmt, mkgmap — all in Docker
- **No Django**: standard CLI library, not a Django app

## Goals / Non-Goals

**Goals:**

- Establish a working `uv sync && just install && just test` development loop
- Provide a CLI entry point (`cartoload`) that can be invoked immediately
- Set up CI that runs lint + typecheck + test on every PR
- Provide Docker environment with all system dependencies for GDAL/mkgmap work
- Ship example YAML configs so users can see the config format from day one
- Create docs site skeleton ready for content

**Non-Goals:**

- Implement any actual pipeline logic (downloader, processor, exporter) — that's future changes
- Create a working Garmin `.img` writer — Phase 1 feature, not scaffolding
- Set up `cartoload-server` integration — separate project
- Publish to PyPI — only the publish _workflow_ is set up; no actual release

## Decisions

### 1. `src/` layout with hatchling

**Choice**: `src/cartoload/` package, `[build-system]` with `hatchling`.

**Rationale**: Same as django-admin-runner. The `src` layout prevents accidental imports from the repo root and is the recommended Python packaging pattern. Hatchling is fast, doesn't require `setup.py`, and works well with `uv`.

**Alternative considered**: setuptools, flit — hatchling is already proven in the django-admin-runner project.

### 2. Type checker: `ty` instead of `pyright`

**Choice**: Use `ty` (Astral's Rust-based type checker) as specified in SPEC.md.

**Rationale**: The SPEC explicitly lists `ty>=0.0.1a23` in dev dependencies. While `ty` is pre-release, it's from the same team as `ruff` and `uv`, so it fits the Astral toolchain. CI uses `uv run ty check src/` instead of `uv run pyright src/`.

**Trade-off**: `ty` is alpha software — may have false positives or missing features. Mitigated by running in basic mode and not blocking CI on all warnings initially.

### 3. Modular justfile with `tasks/main.just`

**Choice**: Root `.justfile` imports `tasks/main.just` which contains all recipes. No sub-modules initially.

**Rationale**: Django-admin-runner uses `tasks/core.just`, `tasks/check.just`, `tasks/tests.just`, etc. For cartoload's initial scope, a single `tasks/main.just` is sufficient. If the project grows, it can be split into modules (e.g., `tasks/check.just`, `tasks/docs.just`, `tasks/release.just`) following the same pattern.

**Alternative considered**: Single flat justfile — less organized; modular is the established convention.

### 4. Single CI workflow instead of separate test + quality

**Choice**: One `ci.yml` that runs lint, typecheck, and test in a single job, plus a separate `publish.yml` for tag-based releases.

**Rationale**: Cartoload doesn't need the Django-admin-runner's split of `test.yml` + `quality.yml` at this stage. A single workflow is simpler. Can be split later if needed.

### 5. Docker with multi-stage system deps

**Choice**: Single-stage Dockerfile that installs GDAL, Java, osmium, gmt, mkgmap, then copies the app and runs `uv sync --no-dev`.

**Rationale**: All system deps are needed for the full pipeline. The Dockerfile mirrors the SPEC.md specification exactly. Using `python:3.12-slim-bookworm` as base for stable GDAL packages.

### 6. Config dataclasses (no pydantic)

**Choice**: Plain `@dataclass` for `SourceConfig` and `LayerConfig` in `config.py`.

**Rationale**: SPEC.md explicitly excludes pydantic — "config models use plain dataclasses." This keeps dependencies lean.

### 7. CLI framework: Click

**Choice**: Click for the CLI, with `cartoload.cli:main` as the console_scripts entry point.

**Rationale**: SPEC.md specifies Click. It's well-established, decorator-based, and supports the command structure (`build`, `download`, `split`, `list`) defined in the CLI reference.

## Risks / Trade-offs

- **`ty` alpha status** → If `ty` causes CI issues, temporarily fall back to `pyright` or skip the typecheck step. Pin the exact alpha version in `pyproject.toml`.
- **GDAL in CI** → CI won't run GDAL-dependent tests (no system deps in GitHub Actions runners). Tests that need GDAL should be marked with `@pytest.mark.gdal` and skipped in CI initially. Docker is the environment for full integration tests.
- **`gmt` binary URL stability** → The GMapTool download URL may change. Pin the version in the Dockerfile and add a comment about where to find the latest URL.
- **Large initial file set** → ~30 files is a lot for one change. Mitigated by keeping all files minimal — stubs and placeholders only.
