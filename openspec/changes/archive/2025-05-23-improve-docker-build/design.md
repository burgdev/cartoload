## Context

The cartoload Dockerfile currently uses `python:3.12-slim-bookworm` as its base and installs GDAL from Debian bookworm's apt repository (GDAL 3.4.1, released ~2022). The project depends on GDAL both for CLI tools (`gdalwarp`, `gdalbuildvrt`, `gdaladdo`) invoked via subprocess and for Python libraries `rasterio` and `fiona` that link against the GDAL C library.

Current image installs:
- `gdal-bin`, `python3-gdal`, `libgdal-dev` — outdated GDAL 3.4.1
- `default-jre-headless` — for mkgmap
- `osmium-tool` — for future OSM processing
- `gmt` (GMapTool) — downloaded from gmaptool.eu, unpinned version
- `mkgmap` — downloaded as "latest", unpinned
- `uv` — copied from official image

The OSGeo GDAL project publishes Docker images at `ghcr.io/osgeo/gdal` with recent GDAL builds on Ubuntu 24.04 (Python 3.12). The `ubuntu-small` variant (~385 MB) includes GDAL CLI tools, Python bindings, and PROJ — everything cartoload needs from GDAL.

### Current image behavior

The current Dockerfile works but has these issues:
1. **GDAL 3.4.1 is old** — missing 2+ years of bug fixes, driver improvements, and format support
2. **Unpinned downloads** — `mkgmap-latest.tar.gz` and gmt URL can break when upstream changes
3. **No `.dockerignore`** — full `.git` directory and other unnecessary files enter build context
4. **No build separation** — download artifacts (wget, tar) remain in the final image
5. **`libgdal-dev` in production image** — dev headers are build-only dependencies, not needed at runtime

## Goals / Non-Goals

**Goals:**
- Use an up-to-date GDAL (3.12.x) via the OSGeo base image
- Pin versions for all external tool downloads (gmt, mkgmap)
- Multi-stage build to keep the final image clean
- Add `.dockerignore` to reduce build context size
- Maintain all current functionality (gdal CLI tools, Java/mkgmap, osmium, gmt, Python deps)

**Non-Goals:**
- Publishing the Docker image to a registry (no CI changes)
- Changing the application code or entrypoint
- Switching to Alpine-based images (would require musl-compatible builds for rasterio/fiona)
- Adding health checks or process management (cartoload is CLI-only)

## Decisions

### Decision 1: Use `ghcr.io/osgeo/gdal:ubuntu-small-3.12.4` as base

**Choice:** OSGeo ubuntu-small image (pinned to 3.12.4)

**Alternatives considered:**
- `ghcr.io/osgeo/gdal:alpine-normal-latest` — smaller (~282 MB) but musl-based; rasterio/fiona wheels on PyPI are glibc-only, would require compiling from source
- `ghcr.io/osgeo/gdal:ubuntu-full-latest` — unnecessarily large (~1.48 GB) with drivers cartoload doesn't need
- Keep `python:3.12-slim-bookworm` + apt GDAL — keeps GDAL 3.4.1, defeats the purpose
- Build GDAL from source — complex, slow builds, maintenance burden

**Rationale:** ubuntu-small provides GDAL 3.12.4 with Python 3.12, includes GDAL Python bindings, and uses glibc (compatible with rasterio/fiona binary wheels). At ~385 MB it's reasonable. Pinning to a specific version ensures reproducibility.

### Decision 2: Two-stage build (builder → runtime)

**Stage 1 (builder):** Based on the OSGeo image. Downloads gmt and mkgmap with pinned versions. Installs them to a staging directory.

**Stage 2 (runtime):** Based on the same OSGeo image. Copies only the installed tool binaries from builder. Installs remaining apt packages (JRE, osmium). Installs Python deps with uv.

This keeps download artifacts (zip files, tarballs, build tools) out of the final image.

### Decision 3: Version pinning for external tools

- **gmt**: Pin to 0.8.220 (already the current version, just not explicitly pinned in the URL)
- **mkgmap**: Pin to a specific release tarball instead of `mkgmap-latest.tar.gz`

The mkgmap "latest" URL is a redirect; pinning to a specific version ensures reproducible builds.

### Decision 4: Install rasterio/fiona via pip (uv), not from OSGeo image

The OSGeo image includes GDAL Python bindings (`from osgeo import gdal`), but cartoload uses `rasterio` and `fiona` (which have their own GDAL linking). Installing these via `uv sync` lets uv pull binary wheels that link against the system GDAL provided by the base image. This is the standard approach and avoids version conflicts.

## Risks / Trade-offs

- **[GDAL version compatibility]** → rasterio and fiona have minimum GDAL version requirements but are generally forward-compatible. GDAL 3.12.4 should work with current rasterio>=1.4.4 and fiona>=1.10.1. **Mitigation:** Test the build and run the test command to verify.

- **[OSGeo image update cadence]** → Pinning to `ubuntu-small-3.12.4` means we control when to upgrade, but won't get automatic GDAL patches. **Mitigation:** This is actually a feature — explicit upgrades are better than surprise breakage.

- **[Image size increase]** → OSGeo ubuntu-small (~385 MB) + Python deps is likely larger than the current slim + GDAL apt. **Mitigation:** The multi-stage build helps, and the trade-off for up-to-date GDAL is worth it. Exact sizes should be compared after building.

- **[OSGeo image availability]** → Depends on `ghcr.io/osgeo/gdal` staying available. **Mitigation:** This is an official OSGeo project with strong community support; low risk.

- **[gmt binary architecture]** → gmt is downloaded as a precompiled Linux binary. **Mitigation:** Already the case in the current Dockerfile; no regression.
