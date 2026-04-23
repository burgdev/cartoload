## 1. Core RasterProcessor Class

- [x] 1.1 Create `src/cartoload/processor/raster.py` with `RasterProcessor` class accepting `target_crs: str` and `output_path: Path` in its constructor
- [x] 1.2 Implement `RasterProcessor.process(tiles: list[Path]) -> Path` method that orchestrates the full pipeline: build VRT, reproject, build overviews, and return the output path
- [x] 1.3 Implement `RasterProcessor._ensure_output_dir()` to create the output directory if it does not exist
- [x] 1.4 Define custom exceptions: `GdalNotFoundError` and `GdalProcessError` in `src/cartoload/processor/raster.py`

## 2. GDAL Availability Check

- [x] 2.1 Implement `_check_gdal_available()` static method that verifies `gdalwarp`, `gdalbuildvrt`, and `gdaladdo` are on `PATH` using `shutil.which()`
- [x] 2.2 Raise `GdalNotFoundError` with installation instructions if any GDAL tool is missing; include platform-specific hints (apt, brew, OSGeo4W)
- [x] 2.3 Call `_check_gdal_available()` in `RasterProcessor.__init__()` so GDAL absence is detected early

## 3. gdalbuildvrt Wrapper

- [x] 3.1 Implement `_build_vrt(tiles: list[Path], vrt_path: Path) -> Path` method that runs `gdalbuildvrt` via `subprocess.run()` with the tile list as input and writes a VRT file
- [x] 3.2 Handle `gdalbuildvrt` non-zero exit codes by raising `GdalProcessError` with captured stderr
- [x] 3.3 Validate that the tile list is not empty before invoking `gdalbuildvrt`

## 4. gdalwarp Wrapper

- [x] 4.1 Implement `_reproject(vrt_path: Path, output_path: Path) -> Path` method that runs `gdalwarp` via `subprocess.run()` with `-t_srs <target_crs>` to reproject the VRT into a GeoTIFF
- [x] 4.2 Pass appropriate flags: `-of GTiff` for output format, `-co COMPRESS=LZW` for lossless compression, `-co TILED=YES` for tiled output
- [x] 4.3 Handle `gdalwarp` non-zero exit codes by raising `GdalProcessError` with captured stderr

## 5. gdaladdo Wrapper

- [x] 5.1 Implement `_build_overviews(geotiff_path: Path) -> None` method that runs `gdaladdo` via `subprocess.run()` with average resampling and levels `2 4 8 16 32 64`
- [x] 5.2 Pass `-r average` flag for resampling method
- [x] 5.3 Handle `gdaladdo` non-zero exit codes by raising `GdalProcessError` with captured stderr

## 6. Tests

- [x] 6.1 Create `tests/test_processor_raster.py` with `@pytest.mark.gdal` marker on all tests requiring GDAL
- [x] 6.2 Test that `RasterProcessor.__init__()` raises `GdalNotFoundError` when GDAL tools are not on PATH (mock `shutil.which` to return `None`)
- [x] 6.3 Test that `RasterProcessor.process()` calls `_build_vrt`, `_reproject`, and `_build_overviews` in order (mock subprocess calls)
- [x] 6.4 Test that `_build_vrt()` raises `GdalProcessError` on non-zero exit code from `gdalbuildvrt` (mock `subprocess.run`)
- [x] 6.5 Test that `_reproject()` raises `GdalProcessError` on non-zero exit code from `gdalwarp` (mock `subprocess.run`)
- [x] 6.6 Test that `_build_overviews()` raises `GdalProcessError` on non-zero exit code from `gdaladdo` (mock `subprocess.run`)
- [x] 6.7 Test that `_build_vrt()` raises `ValueError` when called with an empty tile list
- [x] 6.8 Add integration test (marked `@pytest.mark.gdal` and `@pytest.mark.integration`) that processes a small synthetic GeoTIFF through the full pipeline and verifies the output exists and has overviews
