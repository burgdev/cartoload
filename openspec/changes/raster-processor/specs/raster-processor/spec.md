## ADDED Requirements

### Requirement: Reproject tiles to target CRS
The `RasterProcessor` SHALL reproject input raster tiles to a configurable target CRS using `gdalwarp`. The target CRS SHALL be specified as an EPSG code (e.g., `EPSG:4326`). The processor SHALL pass the source files and target CRS to `gdalwarp` via subprocess and handle the output.

#### Scenario: Reproject a set of tiles from native CRS to EPSG:4326
- **WHEN** `RasterProcessor` is given a list of tile file paths and a target CRS of `EPSG:4326`
- **THEN** it invokes `gdalwarp` with the source tiles and `-t_srs EPSG:4326`, producing reprojected output

#### Scenario: Reprojection preserves pixel data
- **WHEN** tiles are reprojected from EPSG:3857 to EPSG:4326
- **THEN** the output raster contains the same pixel values (resampled according to the configured resampling method) in the target CRS

### Requirement: Create VRT mosaic from multiple tiles
The `RasterProcessor` SHALL mosaic multiple input tiles into a single virtual raster using `gdalbuildvrt`. The VRT SHALL reference all input tiles without copying pixel data, providing a lightweight mosaic that can be processed further.

#### Scenario: Mosaic three adjacent tiles
- **WHEN** `RasterProcessor` is given three tile file paths that cover adjacent geographic areas
- **THEN** it invokes `gdalbuildvrt` with the three source files, producing a single VRT file that references all three tiles

#### Scenario: Single tile passes through mosaicking
- **WHEN** `RasterProcessor` is given exactly one tile file path
- **THEN** it still creates a VRT referencing that single file, maintaining a consistent output format regardless of input count

### Requirement: Build overviews for multi-resolution access
The `RasterProcessor` SHALL build internal overviews on the output GeoTIFF using `gdaladdo`. Overviews SHALL be generated at power-of-2 levels (2, 4, 8, 16, 32, 64) using average resampling.

#### Scenario: Build overviews on a mosaicked raster
- **WHEN** the processor has produced a final GeoTIFF output
- **THEN** it invokes `gdaladdo` with overview levels `2 4 8 16 32 64` and average resampling, adding internal overviews to the GeoTIFF

#### Scenario: Overview levels are suitable for zoom
- **WHEN** the output GeoTIFF with overviews is opened in a GIS viewer
- **THEN** the viewer can display the raster at multiple zoom levels without re-reading the full resolution data

### Requirement: Output single GeoTIFF
The `RasterProcessor` SHALL produce a single GeoTIFF file as its final output. The processing pipeline SHALL be: build VRT from input tiles, reproject via `gdalwarp` (reading from VRT and writing GeoTIFF), then build overviews on the resulting GeoTIFF. The output file path SHALL be configurable.

#### Scenario: Full pipeline produces a single GeoTIFF
- **WHEN** `RasterProcessor.process(tiles, target_crs, output_path)` is called with a list of tile paths, a target CRS, and an output path
- **THEN** a single GeoTIFF file exists at `output_path` containing the reprojected, mosaicked raster with embedded overviews

#### Scenario: Output path is created if parent directory does not exist
- **WHEN** the specified output path's parent directory does not exist
- **THEN** the processor creates the parent directory before writing the output

### Requirement: Error handling for missing GDAL
The `RasterProcessor` SHALL check for GDAL tool availability before attempting processing. If `gdalwarp`, `gdalbuildvrt`, or `gdaladdo` is not found on the system `PATH`, the processor SHALL raise a clear error message indicating which tool is missing and how to install GDAL. If a GDAL subprocess returns a non-zero exit code, the processor SHALL capture stderr and include it in the exception message.

#### Scenario: GDAL is not installed
- **WHEN** `RasterProcessor` is initialized on a system where `gdalwarp` is not on `PATH`
- **THEN** it raises a `GdalNotFoundError` (or equivalent) with a message like `"gdalwarp not found on PATH. Install GDAL: apt install gdal-bin (Debian/Ubuntu) or brew install gdal (macOS)"`

#### Scenario: gdalwarp fails with corrupted input
- **WHEN** `gdalwarp` is invoked on a corrupted tile file and returns a non-zero exit code
- **THEN** the processor raises an exception that includes the stderr output from `gdalwarp`, allowing the user to diagnose the problem

#### Scenario: gdalbuildvrt fails with no input files
- **WHEN** `gdalbuildvrt` is invoked with an empty list of source files and returns a non-zero exit code
- **THEN** the processor raises an exception that includes the stderr output from `gdalbuildvrt`
