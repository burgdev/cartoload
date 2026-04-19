## Context

Downloaded raster tiles -- whether from WMTS or GeoTIFF sources -- arrive in their native coordinate reference system (CRS) and as individual files. Before the Garmin `.img` exporter can consume them, these tiles must be reprojected to the target CRS (typically EPSG:4326 or EPSG:3857), mosaicked into a single coherent raster, and equipped with overviews for efficient multi-resolution access. GDAL is the de facto standard tool for all three operations.

The processor sits between the downloader and the exporter in the cartoload pipeline. It receives a list of tile file paths and configuration parameters (target CRS, output path), and produces a single GeoTIFF ready for export.

The existing `src/cartoload/processor/raster.py` is currently a stub. This change implements the full `RasterProcessor` class.

## Goals / Non-Goals

**Goals:**
- Reproject downloaded tiles to a configurable target CRS using `gdalwarp`
- Mosaic multiple tiles into a single raster via VRT (Virtual Raster Table) using `gdalbuildvrt`
- Build overviews (pyramid levels) on the output raster using `gdaladdo`
- Output a single GeoTIFF file ready for the exporter
- Validate GDAL tool availability at runtime and surface clear error messages

**Non-Goals:**
- Downloading tiles from WMTS, WMS, or STAC sources -- that is the downloader's responsibility
- Exporting to Garmin `.img` format -- that is the exporter's responsibility
- Supporting non-raster (vector) data -- vector processing is a separate concern
- Implementing custom resampling or interpolation algorithms -- GDAL handles this

## Decisions

### 1. GDAL CLI tools via subprocess instead of Python bindings

**Choice**: Use `gdalwarp`, `gdalbuildvrt`, and `gdaladdo` as subprocess calls rather than the `osgeo.gdal` Python bindings.

**Rationale**: The `python3-gdal` package version must exactly match the installed GDAL library version. This creates fragile dependency coupling -- especially across different Linux distributions, macOS Homebrew, and Windows OSGeo4W. Calling the CLI tools via `subprocess.run()` only requires that the GDAL binaries are on `PATH`, which is simpler to guarantee (the Docker image already installs `gdal-bin`). The CLI tools are stable, well-documented, and produce identical results.

**Alternative considered**: `osgeo.gdal` Python bindings -- avoided due to version coupling issues and the fact that the project already avoids `python3-gdal` as a runtime dependency.

### 2. VRT-first mosaicking strategy

**Choice**: Build a VRT from all input tiles using `gdalbuildvrt`, then translate the VRT to a final GeoTIFF.

**Rationale**: `gdalbuildvrt` is fast because it creates a lightweight XML file referencing the source tiles rather than copying pixel data. The VRT can then be fed to `gdalwarp` for reprojection, which handles both mosaicking and reprojection in a single pass. This avoids an intermediate full-copy mosaic step.

**Alternative considered**: Running `gdalwarp` on each tile individually and then mosaicking the results -- more I/O and more intermediate files.

### 3. Overview levels and resampling method

**Choice**: Build overviews at standard power-of-2 levels (2, 4, 8, 16, 32, 64) using average resampling.

**Rationale**: Power-of-2 levels are the GDAL convention and match what most GIS tools expect. Average resampling produces smooth overviews suitable for raster map data. These values can be made configurable later if needed.

### 4. Output format: single GeoTIFF

**Choice**: The processor outputs a single GeoTIFF file (`.tif`) with embedded overviews.

**Rationale**: GeoTIFF is universally supported and can contain internal overviews. The Garmin `.img` exporter expects a single raster input. A single file simplifies downstream handling.

## Risks / Trade-offs

- **GDAL version differences across systems** -- Different GDAL versions may have slightly different CLI flag support or default behavior. Mitigated by targeting well-established flags that have been stable across GDAL 3.x. The Docker image pins a specific GDAL version via `gdal-bin`.
- **Subprocess error handling** -- GDAL tools return non-zero exit codes on failure, but error messages go to stderr. The processor must capture and surface stderr content in exceptions so users can diagnose issues (missing files, unsupported CRS, corrupted tiles).
- **Large raster I/O** -- Mosaicking and reprojecting large tile sets can consume significant memory and disk space. The processor uses VRT to minimize intermediate copies, but the final `gdalwarp` output is a full GeoTIFF. For very large areas, this is inherent to the workflow.
- **GDAL not installed** -- If the user runs cartoload outside Docker without GDAL installed, the processor must detect this early and produce a clear error message rather than a generic `FileNotFoundError`.
