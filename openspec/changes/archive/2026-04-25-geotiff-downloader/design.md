## Context

GeoTIFF via STAC API is the preferred source for high-quality basemaps like swisstopo SMR25 (1:25k) and SMR10 (1:10k). The project-scaffolding change established a stub `src/cartoload/downloader/geotiff.py` and `pystac-client>=0.6` is already a runtime dependency in `pyproject.toml`. The WMTS downloader is implemented separately; this change fills in the GeoTIFF downloader so that layers configured with `type: geotiff` sources can be fetched.

Layer configs reference a GeoTIFF source by `source` (e.g., `swisstopo_stac`) and specify a `geotiff_product` identifier (e.g., `ch.swisstopo.swissmap-raster25_komb`). The source config provides the STAC API endpoint via `stac_url`. The downloader queries the STAC API for items matching the product and bounding box, then downloads GeoTIFF assets to a local cache directory.

## Goals / Non-Goals

**Goals:**

- Query STAC API by product ID and bounding box using pystac-client
- Download GeoTIFF assets from STAC items via requests
- Cache downloaded files locally with a structured directory layout
- Skip already-cached files to support resume/re-run
- Show download progress via rich

**Non-Goals:**

- WMTS tile downloading (handled by wmts-downloader change)
- Raster processing (reprojection, VRT mosaic, overviews -- handled by raster-processor change)
- Exporting to Garmin .img (handled by garmin-img-exporter change)
- GeoPackage support (Phase 2)
- STAC API authentication -- swisstopo and similar public catalogs do not require it

## Decisions

### 1. Use pystac-client for STAC queries

**Choice**: Use `pystac-client` (already a dependency) to open a STAC catalog and search by collections and bounding box.

**Rationale**: pystac-client is the standard Python library for STAC API search. It handles pagination, filter encoding, and result streaming. No additional dependency needed.

**Alternative considered**: Raw HTTP requests to the STAC API endpoint -- would require reimplementing pagination, error handling, and filter encoding that pystac-client already provides.

### 2. Download via requests with streaming

**Choice**: Use `requests.get(url, stream=True)` to download GeoTIFF assets, writing chunks to disk.

**Rationale**: `requests` is already a dependency. Streaming avoids loading multi-GB files into memory. Chunk-based writing allows progress tracking.

**Alternative considered**: `urllib` -- requests is already in deps and provides cleaner streaming/progress hooks.

### 3. Cache directory structure: `cache/{source_id}/{product_id}/{filename}`

**Choice**: Cache files at `{cache_dir}/{source_id}/{product_id}/{filename}` where filename is derived from the STAC item ID or asset key.

**Rationale**: This layout mirrors the config hierarchy (source -> product -> files), avoids filename collisions between different products, and makes it easy to inspect or clean cached data per source or product.

### 4. Skip existing files (caching strategy)

**Choice**: Before downloading, check if the target file already exists on disk. If it does and has non-zero size, skip the download.

**Rationale**: GeoTIFF tiles can be very large (hundreds of MB each). Skipping existing files makes re-runs fast and supports interrupted-download resume scenarios. A simple file-existence check is sufficient for now; ETag or Last-Modified validation can be added later if needed.

### 5. Progress output via rich

**Choice**: Use `rich.progress.Progress` to show download progress per file with filename, download speed, and ETA.

**Rationale**: `rich` is already a dependency and used elsewhere in cartoload. Rich's progress bar supports multiple concurrent downloads and provides a polished terminal UI.

## Risks / Trade-offs

- **STAC API coverage varies by provider** -- Not all providers expose the same collections or spatial coverage. The downloader should report clear errors when no items are found for a given product+bbox, rather than silently returning empty results. Users may need to verify STAC catalog contents before configuring layers.
- **Large asset files (multi-GB)** -- Some GeoTIFF tiles are very large. Streaming downloads mitigate memory pressure, but disk space requirements can be substantial. The downloader should log file sizes before starting downloads so users can anticipate disk usage.
- **Network interruptions** -- Large downloads may fail partway. The skip-existing strategy means a partial file would be treated as complete on re-run. Mitigation: after download completes, verify file size matches the Content-Length header. If mismatch, delete and re-download.
- **No STAC authentication** -- Currently only public catalogs are supported. If private STAC endpoints are needed later, an authentication layer would need to be added.
