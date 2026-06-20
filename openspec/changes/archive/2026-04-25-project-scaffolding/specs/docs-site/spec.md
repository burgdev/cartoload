## ADDED Requirements

### Requirement: Zensical documentation site configuration

The project SHALL have `docs/zensical.toml` configured with project name, description, site URL (`{user}.github.io/cartoload/`), and a navigation structure covering: Home, Getting started, Configuration (Sources, Layers, Style), Exporters (Garmin raster IMG, Garmin vector IMG, Adding exporters), and CLI reference.

#### Scenario: Serve docs locally

- **WHEN** `just docs` is run
- **THEN** zensical serves the documentation site on the configured port

### Requirement: Documentation placeholder pages

The project SHALL have the following markdown files under `docs/`:

- `index.md` — project overview and links
- `getting-started.md` — installation and quickstart (placeholder)
- `configuration/sources.md` — source config format (placeholder)
- `configuration/layers.md` — layer config format (placeholder)
- `configuration/style.md` — style files for vector (placeholder, Phase 2 note)
- `exporters/garmin-img.md` — Garmin raster IMG exporter (placeholder)
- `exporters/garmin-img-vector.md` — Garmin vector IMG exporter (placeholder, Phase 2 note)
- `exporters/adding-exporters.md` — how to add custom exporters (placeholder)
- `cli.md` — CLI reference (placeholder)

Each placeholder SHALL contain a title and a brief description of what the page will cover.

#### Scenario: All doc pages render

- **WHEN** `just docs-build` is run
- **THEN** the documentation site builds without errors and all pages are accessible in the generated site

### Requirement: README file

The project SHALL have a `README.md` at the repo root with: project name and tagline, brief description, installation instructions (`uv tool install cartoload` and `pip install cartoload`), minimal usage example, link to documentation, and MIT license note.

#### Scenario: README renders on GitHub

- **WHEN** the repository is viewed on GitHub
- **THEN** the README displays project overview, install instructions, and usage example
