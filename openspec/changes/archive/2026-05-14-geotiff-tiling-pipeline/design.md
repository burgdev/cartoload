## Context

Cartoload currently supports `wmts` as its primary raster source. A `GeoTIFFDownloader` class exists with STAC API support, but the pipeline cannot consume downloaded GeoTIFFs — they sit in cache unused.

The swisstopo 1:25k raster map provides 264 GeoTIFF tiles (EPSG:2056, 1.25m resolution) via STAC. Each GeoTIFF embeds its own CRS and bounding box, so no manual CRS/bounds configuration is needed.

## Goals / Non-Goals

**Goals:**
- Three source types: `wmts` (existing), `stac` (STAC API → download → process), `geotiff` (local/remote GeoTIFF files)
- On-the-fly GeoTIFF tile reading via rasterio windowed reads — no preprocessing
- Feed JPEG bytes into the existing export pipeline (same interface as WMTS)
- Keep the WMTS pipeline untouched

**Non-Goals:**
- STAC API auto-discovery — user provides URL and collection ID
- Preprocessing GeoTIFFs into intermediate XYZ tiles
- Vector GeoTIFF support
- Mosaicking overlapping GeoTIFFs (swisstopo tiles are a regular grid)
- Non-GeoTIFF STAC assets (future: inspect media type and route)

## Decisions

### 1. Three source types: `wmts`, `stac`, `geotiff`

**Decision:** Three distinct source types sharing the same `urls`/`url_template` config pattern:

- **`wmts`** — existing, no changes. `urls` contain tile URL templates with `${x}/${y}/${z}` per-tile vars.
- **`stac`** — queries a STAC collection endpoint, downloads assets. `urls` contain STAC API URLs with `${layer}` config var. Pipeline routes to format-specific processor based on asset media type (currently only GeoTIFF).
- **`geotiff`** — references GeoTIFF files directly. `urls` entries can be:
  - Local paths relative to the config file: `../data/tiles/`
  - Absolute paths: `/data/geotiffs/file.tif`
  - HTTP URLs: `https://example.com/file.tif` (downloaded to cache)
  - Directory paths: scanned recursively for `.tif`/`.tiff` files

**Rationale:** `stac` is a discovery/download protocol. `geotiff` is a direct file reference. They produce the same output (GeoTIFFs on disk) and share the tile reader. The `geotiff` type is effectively "what's in the cache after a stac download" — pointing at a cache directory should work.

### 2. On-the-fly windowed reads instead of preprocessing

**Decision:** For each (x, y, zoom) tile needed by the export pipeline, read the overlapping pixel window from the relevant GeoTIFF via rasterio, warp to EPSG:4326, and return JPEG bytes. No intermediate tile files on disk.

**Rationale:** The existing pipeline already does per-tile reprojection via `rasterio_warp.py`. The GeoTIFF case is analogous — the only change is *where the pixel data comes from*. Rasterio's windowed reads are efficient: only the needed pixels are loaded.

### 3. Spatial index for GeoTIFF lookup

**Decision:** After downloading/collecting GeoTIFFs, read each file's CRS and bounds from rasterio metadata and build an in-memory spatial index. Linear scan over (bounds, filepath) tuples — fast enough for hundreds of files.

### 4. CRS auto-detected from file metadata

**Decision:** Read CRS directly from each GeoTIFF via rasterio. No `crs` field needed in the source config for `stac` or `geotiff` types.

### 5. Layer bounds for filtering only

**Decision:** GeoTIFFs define their own extent. Layer `bounds` is optional — only used to clip the output area. If absent, the full extent of all GeoTIFFs is used.

## Risks / Trade-offs

- **Open file handles** → Open GeoTIFFs on-demand per tile, don't keep all files open. Rasterio handles this well with context managers.
- **Multiple GeoTIFFs per tile at low zoom** → For v1, pick the first match. Inputs assumed non-overlapping (swisstopo is a regular grid).
- **Performance vs WMTS** → GeoTIFF windowed reads + warp slightly slower than reading a cached JPEG. Acceptable for an offline build tool.

## Example Configs

**STAC source:**
```yaml
swisstopo_stac:
  type: stac
  defaults:
    layer: ch.swisstopo.pixelkarte-farbe-pk25.noscale
  urls:
    - "https://data.geo.admin.ch/api/stac/v1/collections/${layer}"
  attribution: "© swisstopo"
```

**GeoTIFF source (local cache):**
```yaml
swisstopo_local:
  type: geotiff
  urls:
    - ".cartoload_cache/swisstopo_stac/ch.swisstopo.pixelkarte-farbe-pk25.noscale/"
```

**GeoTIFF source (remote URLs):**
```yaml
swisstopo_remote:
  type: geotiff
  urls:
    - "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk25.noscale/tile1.tif"
    - "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk25.noscale/tile2.tif"
```

**Layer referencing either:**
```yaml
ch_25k_geotiff:
  name: "Switzerland 1:25k GeoTIFF"
  source:
    ref: swisstopo_stac
    layer: ch.swisstopo.pixelkarte-farbe-pk25.noscale
  zoom_levels: [12, 14, 15, 16]
  exporter: garmin_img
  output: ch_25k_geotiff.img
```
