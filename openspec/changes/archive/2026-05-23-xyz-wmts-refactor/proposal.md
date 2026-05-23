## Why

The current `wmts` source only supports URL templates with `${x}/${y}/${z}` placeholders — it never reads WMTS GetCapabilities. This means users must manually construct the exact URL template, know the TileMatrixSet identifier, CRS, and tile format. A real WMTS Capabilities endpoint already provides all of this information.

## What Changes

- **Extend `WmtsSource` with Capabilities parsing**: The existing `WmtsSource` gains a second mode — if the config provides a `capabilities_url`, it fetches and parses the WMTS GetCapabilities XML to discover layers, TileMatrixSets, CRSs, tile formats, and bounding boxes. The existing URL-template mode continues to work unchanged.
- **Auto-detect mode within `WmtsSource`**: URLs with `${x}/${y}/${z}` placeholders → URL template mode (current behavior). URLs pointing to a Capabilities endpoint (`WMTSCapabilities.xml` or containing `GetCapabilities`) → Capabilities mode.
- **Add `type: xyz` as alias**: `type: xyz` resolves to `WmtsSource` — useful for users who want to be explicit about using URL-template mode. No deprecation warnings, no breaking changes.
- **Share downloader infrastructure**: Both modes use the same `WmtsDownloader` for actual tile fetching — rate limiting, caching, retry logic, world file generation, and multi-URL support.

## Capabilities

### New Capabilities
- `wmts-capabilities`: WMTS GetCapabilities parsing and tile matrix resolution. Covers parsing a WMTS Capabilities XML document, extracting layer info, TileMatrixSet definitions, and constructing tile download URLs.

### Modified Capabilities
- `source-provider-registry`: `type: xyz` registered as alias for `WmtsSource`. Auto-detection expanded: URLs with `${x}/${y}/${z}` → `wmts` (template mode), Capabilities URLs → `wmts` (Capabilities mode).
- `source-method-resolution`: Dispatch scenarios updated for `type: xyz` (resolves to `WmtsSource`).
- `source-crs`: WMTS Capabilities mode reads CRS from TileMatrixSet. Template mode defaults to EPSG:3857 as before. Both support explicit `crs` override.

## Impact

- **No breaking config changes**: Existing `type: wmts` configs continue to work identically
- **Code**: `WmtsSource` extended with Capabilities mode; new `wmts/capabilities.py` module for XML parsing; `wmts/tile_grid.py` for TileMatrixSet-based grid computation
- **Config**: New WMTS Capabilities example config added alongside existing URL-template configs
- **Dependencies**: stdlib `xml.etree.ElementTree` for XML parsing (no new external deps)
- **Tests**: Existing WMTS tests unchanged; new tests for Capabilities parsing, tile grid math, and auto-detection
