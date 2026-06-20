## ADDED Requirements

### Requirement: Multi-stage Dockerfile with OSGeo GDAL base
The Dockerfile SHALL use a multi-stage build with `ghcr.io/osgeo/gdal:ubuntu-small-3.12.4` as the base image for both stages. The builder stage SHALL download and install external tools (gmt, mkgmap) with pinned versions. The runtime stage SHALL copy only the installed artifacts from the builder and SHALL NOT include download artifacts (zip files, tarballs).

#### Scenario: Build produces a working image
- **WHEN** `docker build -t cartoload .` is executed
- **THEN** the image builds successfully and the final stage does not contain wget downloads, zip files, or tar.gz archives

#### Scenario: GDAL tools are available
- **WHEN** a container is started from the image
- **THEN** `gdalwarp --version`, `gdalbuildvrt --version`, and `gdaladdo --version` commands succeed and report GDAL 3.12.x

#### Scenario: gmt is available
- **WHEN** a container is started from the image
- **THEN** `gmt --version` (or equivalent) succeeds

#### Scenario: mkgmap is available
- **WHEN** a container is started from the image
- **THEN** `java -jar /opt/mkgmap.jar --version` succeeds

#### Scenario: osmium is available
- **WHEN** a container is started from the image
- **THEN** `osmium --version` succeeds

#### Scenario: Java runtime is available
- **WHEN** a container is started from the image
- **THEN** `java -version` succeeds

### Requirement: Pinned external tool versions
All external tool downloads (gmt, mkgmap) SHALL use version-pinned URLs. The versions SHALL be documented in the Dockerfile comments. The mkgmap download SHALL NOT use the `mkgmap-latest.tar.gz` redirect URL.

#### Scenario: Reproducible builds
- **WHEN** the Dockerfile is built multiple times on different machines
- **THEN** the same versions of gmt and mkgmap are installed (barring upstream URL changes)

### Requirement: .dockerignore file
A `.dockerignore` file SHALL exist at the project root and SHALL exclude `.git`, `__pycache__`, `*.pyc`, `.venv`, `openspec/`, `docs/`, `tests/`, `*.egg-info`, `output/`, `cache/`, and `.ruff_cache/` from the Docker build context.

#### Scenario: Build context excludes development files
- **WHEN** `docker build` is executed
- **THEN** the build context does not include `.git`, `openspec/`, `docs/`, `tests/`, `cache/`, or `output/` directories

### Requirement: Entrypoint and functionality preserved
The Dockerfile entrypoint SHALL remain `uv run cartoload`. All current docker-compose.yml volume mounts and environment variables SHALL continue to work without modification.

#### Scenario: cartoload CLI works in container
- **WHEN** `docker run cartoload --help` is executed
- **THEN** the cartoload CLI help output is displayed

#### Scenario: docker-compose works unchanged
- **WHEN** `docker compose up` is executed with the existing `docker-compose.yml`
- **THEN** the cartoload service starts and processes commands using the mounted volumes
