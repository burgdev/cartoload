## Context

Cartoload currently has these source types: `wmts`, `stac`, `geotiff`, `gpkg`. The `stac` type is really "GeoTIFF fetched via STAC API" — it conflates data format with download method. The `geotiff` type is "GeoTIFF from local path" — same format, different acquisition. The `gpkg` type is "GPKG fetched via STAC API" — different format, same acquisition as `stac`.

The downloader code already shows this split: `STACDownloader` and `GPKGDownloader` share nearly identical STAC query logic (bbox filtering, spatial overlap, cache keys, freshness checking). The only differences are asset detection (GeoTIFF vs GPKG media types) and post-processing (GeoTIFFs are warped; GPKGs are unzipped).

The pipeline dispatches on source type: `stac`/`geotiff` → `build_geotiff_layer()`, `gpkg` → `build_gpkg_layer()`, `wmts` → WMTS pipeline. The processing is fundamentally different per data format, not per download method.

## Goals / Non-Goals

**Goals:**
- Unify `stac` and `geotiff` types into a single `geotiff` type
- Make `gpkg` a data type (not a download-method-specific type)
- Auto-detect source method from URL pattern (STAC collection → `stac`, local path → `path`, other URL → `url`)
- Allow explicit `source` field override when auto-detection isn't enough
- Extract shared STAC query logic into a reusable utility
- Update all example configs

**Non-Goals:**
- Supporting new data formats (geojson, etc.) — that's a separate change
- Changing the WMTS pipeline or source type
- Adding direct URL download support for GeoTIFF/GPKG (only `stac` and `path` for now)
- Changing cache directory structure

## Decisions

### 1. Source method: auto-detect with explicit override

**Decision:** Add an optional `source` field to source configs. Values: `stac`, `path`. If omitted, auto-detect from the URL:
- URL matches STAC pattern (`/collections/` or `/stac/`) → `stac`
- URL is a local path (starts with `./`, `../`, `/`, or no scheme) → `path`

**Rationale:** Most configs will "just work" without the `source` field. Explicit override handles edge cases.

### 2. Remove `stac` from allowed types, merge into `geotiff`

**Decision:** `type: stac` is no longer valid. All raster GeoTIFF sources use `type: geotiff`. The source method determines how files are obtained:
- `source: stac` (auto-detected for STAC URLs) → uses `STACDownloader` to query and download
- `source: path` (auto-detected for local paths) → uses `collect_geotiff_files` directly

**Rationale:** A GeoTIFF is a GeoTIFF regardless of how it's fetched. The processing pipeline is identical (spatial index, pre-warp, tile read, export).

### 3. GPKG sources use the same source method field

**Decision:** `type: gpkg` with `source: stac` (auto-detected) uses `GPKGDownloader`. In the future, `source: path` would load a local `.gpkg` file directly.

**Rationale:** Same pattern as geotiff. Currently only STAC download is implemented for GPKG, but the config model is forward-compatible.

### 4. Extract shared STAC query logic

**Decision:** Create a `StacQuery` utility function/class in `src/cartoload/downloader/stac_query.py` that handles the common STAC collection query pattern (fetching items with bbox, spatial overlap filtering). Both downloaders use it.

**Rationale:** The `query()` methods in `STACDownloader` and `GPKGDownloader` are nearly identical. Extracting the shared logic removes ~60 lines of duplication and makes it easy to add new STAC-based source types later.

### 5. Remove `url_template`, consolidate to `urls`

**Decision:** Remove the `url_template` field from `SourceConfig`. `urls` (a list of strings, or a single string auto-wrapped) becomes the only field for specifying source locations — whether they are URLs, STAC endpoints, or local paths.

**Rationale:** `url_template` and `urls` overlap in purpose. `url_template` is a misnomer when the value is a local filesystem path (e.g., `./cache/geotiffs/`). `urls` already supports lists, template expansion, and single strings. Having one field simplifies config, validation, and downstream code.

For WMTS sources, the first `urls` entry becomes the primary template (same as `url_template` was). Additional entries are fallback mirrors.

**Migration:** Replace `url_template: "..."` with `urls: ["..."]` everywhere.

### 6. Config validation: resolve source method early

**Decision:** Source method resolution happens during config parsing (in `_parse_sources_section`), not at pipeline time. The resolved method is stored on `SourceConfig`.

**Rationale:** Fail fast — invalid source configs are caught before any download attempt. Also makes pipeline dispatch simpler (no runtime URL inspection).

## Risks / Trade-offs

- **Breaking config change** — All configs using `type: stac` must be updated. No backward compatibility. Acceptable since this is pre-release software.
- **Auto-detection false positives** — A URL containing `/collections/` that isn't STAC would be mis-detected. The explicit `source` field handles this.
- **Pipeline refactor scope** — Touching the pipeline dispatch means risk of regressions. Mitigated by existing tests and the test command.
