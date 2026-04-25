## Why

Downloaded tiles (whether from WMTS or GeoTIFF) must be reprojected to the target CRS (typically EPSG:4326 or EPSG:3857), mosaicked into a single raster, and prepared with overviews before the exporter can convert them to `.img`. GDAL is the standard tool for these operations — the processor wraps GDAL calls (via subprocess or Python bindings) to produce a clean raster dataset.

## What Changes

- Implement `RasterProcessor` in `processor/raster.py` that: reprojects downloaded tiles to the target CRS using `gdalwarp`, creates a VRT mosaic from multiple tiles, builds overviews for multi-resolution pyramid, and outputs a single GeoTIFF ready for the exporter
- Use GDAL command-line tools (`gdalwarp`, `gdalbuildvrt`, `gdaladdo`) via subprocess for reliability (avoids python3-gdal binding version issues)

## Capabilities

### New Capabilities

- `raster-processor`: Reproject, mosaic, and prepare raster tile data for export using GDAL, producing a single output GeoTIFF with overviews

### Modified Capabilities

_(none)_

## Impact

- **Code**: `src/cartoload/processor/raster.py` goes from stub to working implementation
- **Dependencies**: GDAL system tools (`gdalwarp`, `gdalbuildvrt`, `gdaladdo`) — already in Docker, not a PyPI dep
- **Tests**: `tests/test_processor.py` — tests need GDAL installed (mark with `@pytest.mark.gdal`, skip in CI)
