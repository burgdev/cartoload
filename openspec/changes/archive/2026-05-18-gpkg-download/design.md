## Context

Cartoload's pipeline currently handles raster-only sources (WMTS, STAC GeoTIFFs). The STAC downloader (`STACDownloader`) already queries STAC collections, filters by bbox, downloads assets, and manages a cache with ETag/Last-Modified freshness. The new `gpkg` source type follows the same pattern but targets `.gpkg.zip` assets instead of GeoTIFFs.

The existing STAC downloader has reusable components:
- STAC collection querying with bbox filtering (`STACDownloader.query`)
- Client-side spatial overlap filtering
- Cache path generation with human-readable keys
- Metadata sidecar with ETag/Last-Modified
- Freshness checking via HTTP HEAD

The pipeline dispatches in `pipeline.py` based on source type: WMTS → main pipeline, STAC/GeoTIFF → `build_geotiff_layer`. A new `gpkg` branch will produce a `.gpkg` file path for downstream vector processing.

## Goals / Non-Goals

**Goals:**
- Download `.gpkg.zip` files from STAC endpoints (e.g., swisstopo data)
- Unzip and cache the extracted `.gpkg` file
- Reuse STAC query logic (bbox filtering, spatial overlap)
- Provide freshness checking consistent with existing STAC caching
- Return the path to the `.gpkg` file for downstream use (style engine, rasterizer, mkgmap pipeline)
- Support offline mode (use cached files)

**Non-Goals:**
- Reading or parsing GPKG contents (handled by downstream processors)
- Style engine or rasterization (separate changes)
- mkgmap integration (separate change)
- Non-STAC GPKG sources (local files, direct URLs) — can be added later

## Decisions

### 1. Separate GPKGDownloader class (not extending STACDownloader)

**Decision:** Create a new `GPKGDownloader` class in `src/cartoload/downloader/gpkg.py` that reuses the STAC querying pattern but has its own download/cache logic.

**Rationale:** The STAC downloader is tightly coupled to GeoTIFF assets (media type detection, `.tif` cache paths, pre-warp cache checking). A GPKG downloader has different concerns: zip extraction, single-asset-per-item semantics, no tiling. Reusing the query pattern by extracting shared logic is cleaner than adding conditionals to the existing class.

**Shared logic to extract:**
- `_find_gpkg_asset()` — mirrors `_find_geotiff_asset()` but looks for `application/x.geopackage+zip` media type and `.gpkg.zip` extensions
- STAC query method can be shared via a base class or a utility function in the future. For now, the GPKG downloader will have its own `query()` that follows the same pattern.

### 2. Cache structure: zip + extracted gpkg side by side

**Decision:** Cache the downloaded `.gpkg.zip` and extract the `.gpkg` alongside it in the same cache directory.

```
cache/
  <source_id>/
    <cache_key>/
      skitouren.zip          ← downloaded zip
      skitouren.gpkg         ← extracted geopackage
      skitouren.json         ← metadata sidecar (etag, last-modified)
```

**Rationale:** Keeping the zip allows re-extraction if the `.gpkg` is deleted. The metadata sidecar follows the existing STAC pattern. Human-readable cache keys via `url_to_cache_key`.

**Alternative considered:** Extract to a separate `extracted/` subdirectory. Rejected — adds unnecessary indirection.

### 3. Single-asset assumption

**Decision:** Each STAC item is expected to have exactly one `.gpkg.zip` asset. If multiple are found and no filter is provided, raise an error (same pattern as GeoTIFF).

**Rationale:** Swiss topo datasets have one GPKG per item. If this assumption breaks, `asset_filter` provides an escape hatch.

### 4. No Fiona/geopandas dependency for downloading

**Decision:** The downloader only downloads and extracts. No GPKG reading libraries needed.

**Rationale:** GPKG reading is a downstream concern (rasterizer, mkgmap pipeline). Keeping the downloader lightweight avoids unnecessary dependencies.

### 5. Pipeline integration: new `build_gpkg_layer` function

**Decision:** Add a `build_gpkg_layer()` in `pipeline.py` that downloads the GPKG and returns its path. Initially this is a terminal step — downstream processors will be added by future changes.

**Rationale:** Follows the existing pattern (`build_geotiff_layer`, WMTS pipeline). The function will grow as Path B and Path C changes are added.

## Risks / Trade-offs

- **[Large GPKG files]** swisstopo GPKGs can be 50-200MB zipped. → Cache management handles this; no special treatment needed beyond what STAC already does.
- **[Zip structure variability]** The zip may contain the `.gpkg` at any depth or with any name. → Extraction scans for `.gpkg` files in the zip archive and takes the first match. Warn if multiple `.gpkg` files found.
- **[STAC query duplication]** The query logic is similar to `STACDownloader.query`. → Acceptable duplication for now. A future refactor can extract shared STAC querying into a utility.
- **[No downstream consumer yet]** This change produces a `.gpkg` file path but nothing uses it yet. → This is intentional — the style engine and rasterizer changes will consume it.
