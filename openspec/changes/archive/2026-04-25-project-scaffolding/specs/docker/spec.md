## ADDED Requirements

### Requirement: Dockerfile with system dependencies

The project SHALL have a `Dockerfile` based on `python:3.12-slim-bookworm` that installs system dependencies: `gdal-bin`, `python3-gdal`, `libgdal-dev`, `default-jre-headless`, `osmium-tool`, `wget`, `unzip`, `ca-certificates`. It SHALL also download and install `gmt` (GMapTool) and `mkgmap.jar`. It SHALL copy `uv` from the official image, copy `pyproject.toml` and `src/`, run `uv sync --no-dev`, and set `ENTRYPOINT ["uv", "run", "cartoload"]`.

#### Scenario: Build Docker image

- **WHEN** `docker build -t cartoload .` is run
- **THEN** the image builds successfully with GDAL, Java, osmium, gmt, and mkgmap available

#### Scenario: Run CLI in Docker

- **WHEN** `docker run cartoload --help` is executed
- **THEN** the cartoload CLI help is displayed

### Requirement: Docker Compose for local development

The project SHALL have a `docker-compose.yml` with a `cartoload` service that builds from the Dockerfile, mounts `./cache`, `./output`, and `./examples/configs` as volumes, and sets environment variables `WMTS_DELAY_MS` and `WMTS_THREADS`.

#### Scenario: Run via docker compose

- **WHEN** `docker compose run cartoload build --layer ch_basemap_25k` is executed
- **THEN** the cartoload CLI runs inside the container with mounted cache, output, and config directories
