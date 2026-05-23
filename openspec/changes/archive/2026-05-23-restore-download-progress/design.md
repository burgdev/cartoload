## Context

The unified pipeline (`unified_pipeline.py`) handles all build targets through providers. For WMTS sources, the `WmtsProvider` fetches tiles on-demand during export via `to_raster()` → `download_tile()`. This means:

1. The "downloading" stage only initializes the downloader (instant)
2. All actual network I/O happens during the "Exporting to Garmin IMG" stage
3. The existing `WMTSDownloader.download_grid()` has Rich progress bars, but it's never called from the unified pipeline
4. The user sees "Exporting to Garmin IMG" with no feedback while tiles are actually being downloaded

The old `cartoload download` command still calls `download_grid()` directly and shows progress correctly. The unified pipeline bypassed this.

## Goals / Non-Goals

**Goals:**
- Show a Rich progress bar with download progress (tile count, percentage, elapsed time) during the download phase of `cartoload build`
- Pre-fetch all WMTS tiles before the export stage begins, so export works from cache
- Make the "downloading..." messages actually meaningful (not instant for WMTS)

**Non-Goals:**
- Changing the WmtsProvider's on-demand fetch behavior (it stays as a fallback)
- Adding progress bars for GeoTIFF/STAC downloads (different pattern, separate change)
- Changing the export progress bars (they already work)

## Decisions

### Decision: Pre-fetch WMTS tiles via `download_grid()` before export

**Approach:** In the unified pipeline's download stage, when a provider is a `WmtsProvider`, call `downloader.download_grid()` for each zoom level in the layer's bounds. This uses the existing progress-bar-equipped code.

**Rationale:**
- `download_grid()` already has Rich progress bars, handles caching, parallelism, retries, and rate limiting
- Pre-fetching separates the download phase from the export phase, giving clear progress for each
- The WmtsProvider's `to_raster()` then serves from cache (fast, no network I/O during export)
- This matches the existing `cartoload download` command behavior

**Alternative considered:** Add a download progress callback to `WmtsProvider.to_raster()` — rejected because:
- Would require threading download progress through the export pipeline
- Mixing download and export progress reporting is confusing
- The export progress callback interface (`(stage, current, total)`) doesn't naturally support download counting

### Decision: Show per-zoom Rich progress bars during download

The `download_grid()` method already creates per-zoom progress bars. No changes needed to its display format.

### Decision: Only pre-fetch for WMTS providers

GeoTIFF/STAC providers have different download patterns (bulk file downloads, not tile grids). Their progress is handled by their respective downloaders.

## Risks / Trade-offs

- **[Duplicate download logic]** The `WmtsProvider.download()` already initializes the downloader, and now we also call `download_grid()`. → The `download_grid()` call is additive and idempotent (checks cache first).
- **[Memory for tile lists]** `download_grid()` builds the full tile coordinate list. For very large areas this is fine since it already works for `cartoload download`.
