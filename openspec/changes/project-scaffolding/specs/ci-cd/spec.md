## ADDED Requirements

### Requirement: CI workflow on pull requests

The project SHALL have `.github/workflows/ci.yml` that triggers on push and pull_request, running lint, typecheck, and test in a single job using `uv` on ubuntu-latest.

#### Scenario: PR triggers CI

- **WHEN** a pull request is opened or updated
- **THEN** the CI workflow runs `ruff format --check`, `ruff check`, `ty check`, and `pytest` sequentially

#### Scenario: CI uses uv

- **WHEN** the CI workflow runs
- **THEN** it uses `astral-sh/setup-uv@v4` and `uv sync --all-groups` to install dependencies

### Requirement: Publish workflow on version tags

The project SHALL have `.github/workflows/publish.yml` that triggers on tag push matching `v*`, builds the package with `uv build`, and publishes to PyPI using `UV_PUBLISH_TOKEN` secret.

#### Scenario: Tag push triggers publish

- **WHEN** a tag matching `v*` is pushed
- **THEN** the workflow builds a wheel and sdist and publishes them to PyPI

#### Scenario: Publish requires secret

- **WHEN** the publish workflow runs
- **THEN** it uses `${{ secrets.PYPI_TOKEN }}` set as `UV_PUBLISH_TOKEN` environment variable
