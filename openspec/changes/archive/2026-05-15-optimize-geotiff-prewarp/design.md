## Context

The current GeoTIFF pre-warp pipeline in `geotiff_prewarp.py` uses rasterio's Python API for both CRS transformation and mosaic assembly. For Swiss topo data at 10m resolution, each source file is ~200-300MB (~14k x 14k pixels). The pipeline processes these with `rasterio.warp.reproject()` (single-threaded, full-array allocation) and merges them into a physical mosaic using `np.zeros()` followed by per-file reprojection into the output array. For full-Switzerland builds this allocates ~2.3GB, well above the 1GB RAM target.

The rasterio library bundles GDAL CLI tools (`gdalwarp`, `gdalbuildvrt`) which are already available in the environment but not currently used.

## Goals / Non-Goals

**Goals:**
- Pre-warp individual GeoTIFFs using multi-threaded `gdalwarp` CLI for 3-5x speedup
- Replace physical mosaic with VRT to eliminate large memory allocations
- Add ETag/Last-Modified staleness detection for STAC downloads
- Delete original GeoTIFFs after successful warp, keeping only JSON metadata
- Keep peak RAM under 1GB for any operation, including full Switzerland at 10m

**Non-Goals:**
- Block-streaming for individual file warps (gdalwarp handles this internally)
- Replacing rasterio for tile reads (rasterio opens VRTs natively — no change needed)
- Adding `osgeo.gdal` as a Python dependency (using CLI tools instead to avoid dual-GDAL)
- Changing the WMTS download/caching pipeline (only STAC is affected by ETag changes)

## Decisions

### 1. Use `subprocess.run(["gdalwarp", ...])` instead of `osgeo.gdal.Warp()`

**Choice**: CLI subprocess over Python bindings.

**Alternatives considered**:
- `osgeo.gdal.Warp()`: Programmatic Python API for gdalwarp. More "Pythonic" but requires the `gdal` pip package as a new dependency, which bundles its own copy of libgdal alongside rasterio's bundled copy. This causes version conflicts and binary compatibility issues.
- `rasterio` (current approach): Single-threaded, full-array allocation, no multi-threading support.

**Rationale**: Zero new dependencies. `gdalwarp` binary is already present via rasterio's GDAL bundle. The subprocess overhead is negligible compared to the warp time. CLI tools are battle-tested and well-documented.

### 2. Use `subprocess.run(["gdalbuildvrt", ...])` for mosaic VRT creation

**Choice**: CLI subprocess to create a file-based VRT.

**Alternatives considered**:
- `rasterio.vrt.WarpedVRT`: Only handles single-file on-the-fly warping. Cannot merge multiple files. Not applicable.
- `osgeo.gdal.BuildVRT()`: Same dual-GDAL dependency issue as above.
- Physical mosaic (current): Allocates full output in memory. Breaks at scale.

**Rationale**: A VRT is a tiny XML file (few KB) that virtually references the underlying pre-warped GeoTIFFs. Zero pixel data is copied. `rasterio.open("mosaic.vrt")` reads it transparently — no changes needed in `geotiff_tile_reader.py`.

### 3. Palette expansion handled by `gdalwarp -expand rgb`

**Choice**: Let `gdalwarp` handle palette-to-RGB expansion natively via the `-expand rgb` flag.

**Alternatives considered**:
- Current two-step approach (warp indices → LUT expansion): Custom Python code, single-threaded, requires loading full arrays.

**Rationale**: `gdalwarp -expand rgb` is a well-tested code path that handles palette expansion during the warp in a single pass with proper nearest-neighbor resampling on indices before expansion. Eliminates the color fringing concern that motivated the two-step approach.

### 4. ETag/Last-Modified via HTTP HEAD for STAC freshness

**Choice**: Issue `requests.head(asset_url)` for each STAC item. Store `ETag` and `Last-Modified` in a JSON sidecar file per cached item.

**Alternatives considered**:
- Conditional GET (`If-None-Match` / `If-Modified-Since`): More efficient (saves a round-trip when unchanged) but more complex. Could be added later.
- Content hash comparison: Requires downloading the file, defeating the purpose.
- File existence only (current): No staleness detection.

**Rationale**: HEAD requests are cheap (~100ms each), simple to implement, and most STAC servers (including swisstopo) support them. The JSON sidecar is small and human-readable.

### 5. Delete originals after successful warp

**Choice**: After `prewarp_geotiff()` succeeds, delete the source `.tif` and write a JSON metadata file with `{item_id, url, size, etag, last_modified}`.

**Rationale**: The pre-warped `_4326.tif` file is all that's needed for tile reads. The original is only needed for re-warping, which should only happen if the remote source changes. In that case, the file gets re-downloaded anyway. Keeping the metadata JSON allows the STAC downloader to check freshness via ETag without the original file.

## Risks / Trade-offs

- **[gdalwarp not found in PATH]** → Add a startup check that verifies `gdalwarp` and `gdalbuildvrt` are available. Raise a clear error if missing. In practice, rasterio always installs these.
- **[VRT references deleted files]** → If a pre-warped `_4326.tif` is manually deleted, the VRT will have gaps. Mitigate by checking VRT validity before use and regenerating if stale (compare VRT mtime vs source file mtimes, same as current mosaic freshness check).
- **[HEAD request not supported by some STAC servers]** → Fall back to current behavior (file existence check only) if HEAD returns 405 or fails. Log a warning.
- **[Larger disk usage per warped file]** → The pre-warped 3-band RGB GeoTIFF is larger than the 1-band paletted original. This is the same as today — no regression. The net savings come from deleting originals and replacing the physical mosaic with VRT.
- **[Subprocess error handling]** → `gdalwarp` can fail for corrupt inputs. Capture stderr, raise a descriptive error. Fall back to current rasterio path if needed (keep as optional fallback initially).

## Open Questions

- Should we keep the rasterio-based pre-warp as a fallback if `gdalwarp` is unavailable, or require it? (Leaning toward requiring it — it's always present with rasterio.)
- What `gdalwarp` `-wm` (warp memory limit) value to use? Default is likely fine, but for constrained environments we might want to cap it.
