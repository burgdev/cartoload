## Why

The current Dockerfile installs GDAL from Debian bookworm's apt repository, which ships GDAL 3.4.1 — a version that's several years old and increasingly behind upstream. The OSGeo project publishes well-maintained Docker images (`ghcr.io/osgeo/gdal`) with recent GDAL releases (currently 3.12.x) built against Ubuntu 24.04 with Python 3.12. Using one of these as a base image would provide up-to-date GDAL without the fragile approach of installing `libgdal-dev` and `python3-gdal` from Debian packages. Additionally, the current Dockerfile lacks `.dockerignore`, pinning for external tool downloads, and could benefit from a multi-stage build to separate tool installation from the final runtime image.

## What Changes

- Switch base image from `python:3.12-slim-bookworm` to `ghcr.io/osgeo/gdal:ubuntu-small-3.12.4` (includes GDAL 3.12.4, PROJ, Python 3.12, and GDAL Python bindings)
- Remove manual `apt-get install` of `gdal-bin`, `python3-gdal`, `libgdal-dev` — the OSGeo image provides these
- Add multi-stage build: one stage for downloading/installing external tools (gmt, mkgmap), final stage copies only the runtime artifacts
- Pin gmt and mkgmap download URLs to specific versions (currently downloads are unpinned: `mkgmap-latest.tar.gz`)
- Add a `.dockerignore` file to exclude unnecessary files from build context (`.git`, `__pycache__`, `openspec/`, etc.)
- Keep `default-jre-headless` and `osmium-tool` as apt installs in the final stage (still needed for mkgmap and future OSM processing)
- Update `docker-compose.yml` if needed

## Capabilities

### New Capabilities
- `docker-multi-stage-build`: Multi-stage Dockerfile with separate builder and runtime stages, using OSGeo GDAL base image

### Modified Capabilities
<!-- No existing specs have requirement changes — this is infrastructure only -->

## Impact

- **Dockerfile**: Complete rewrite of base image and build stages
- **docker-compose.yml**: No structural changes needed; volume mounts remain the same
- **docker.just**: Build command may need adjustment if image tag changes
- **`.dockerignore`**: New file
- **Image size**: OSGeo ubuntu-small is ~385 MB vs python-slim + GDAL apt install. The multi-stage build will keep the final image leaner by not including download artifacts.
- **GDAL version**: Jumps from 3.4.1 to 3.12.4 — rasterio/fiona should work fine with newer GDAL but this needs testing
- **No code changes**: Pure infrastructure change; no Python code is affected
