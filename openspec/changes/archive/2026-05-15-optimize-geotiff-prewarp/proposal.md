## Why

GeoTIFF pre-warping is extremely slow — each 200-300MB Swiss topo file takes several minutes because rasterio's `reproject()` is single-threaded and loads entire arrays into memory. The physical mosaic merge allocates the full output as a single numpy array, making it unusable for full-Switzerland builds (estimated ~2.3GB at 10m resolution, violating the 1GB RAM target). Original GeoTIFFs are kept forever after warping, wasting disk space. STAC downloads have no staleness detection beyond file existence.

## What Changes

- Replace rasterio's single-threaded `reproject()` with `gdalwarp` CLI for pre-warping. `gdalwarp` multi-threades both the warp and LZW compression, streams in blocks, and handles palette expansion (`-expand rgb`) in one pass. The `gdalwarp` binary is already available — rasterio bundles GDAL CLI tools. No new dependencies. Expected 3-5x speedup per file.
- Replace the physical mosaic (single giant GeoTIFF created via `np.zeros` + per-file `reproject`) with a GDAL VRT (virtual raster). Created via `gdalbuildvrt` CLI, a VRT is a tiny XML file that virtually stitches pre-warped files together. Zero memory for creation, instant, and `rasterio.open("mosaic.vrt")` reads it transparently. Scales to any area size without RAM concerns.
- Add HTTP HEAD requests with ETag/Last-Modified comparison for STAC downloads. Store metadata JSON alongside cached files. Only re-download when remote content has actually changed.
- Delete original GeoTIFFs after successful pre-warp, keeping only a JSON metadata file for cache invalidation. Saves ~33% disk.

## Capabilities

### New Capabilities

- `geotiff-prewarp`: Fast, memory-efficient pre-warping of GeoTIFFs using `gdalwarp` CLI with VRT-based mosaic assembly and post-warp cleanup of originals.

### Modified Capabilities

- `tile-cache`: Cache structure changes — original GeoTIFFs replaced with JSON metadata files, physical mosaic replaced with VRT, new metadata-based staleness checks for STAC items.

## Impact

- **Code**: `geotiff_prewarp.py` (major rewrite), `stac.py` (HEAD/ETag logic), `pipeline.py` (VRT integration), `geotiff_tile_reader.py` (minor — VRT is transparent to rasterio)
- **Dependencies**: No new Python packages. Relies on `gdalwarp` and `gdalbuildvrt` CLI tools already present via rasterio's GDAL bundle.
- **Cache**: Existing cached `_4326.tif` files remain compatible. Physical `mosaic_4326.tif` will be replaced by `mosaic.vrt` on next build. Old original `.tif` files can be cleaned up.
- **Disk**: Net reduction of ~33% per cache directory (originals deleted, mosaic is tiny VRT instead of full GeoTIFF).
- **RAM**: Peak usage drops from ~2.3GB (full Switzerland mosaic allocation) to bounded by single tile read (~MB).
- **Performance**: Pre-warp speed expected to improve 3-5x. Mosaic creation goes from minutes (full array write) to instant (XML generation).
