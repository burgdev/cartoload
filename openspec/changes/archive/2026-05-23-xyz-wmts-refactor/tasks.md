## 1. Register `type: xyz` as alias for WmtsSource

- [x] 1.1 Update `WmtsSource.can_handle()` to also accept `source_config.type == "xyz"`
- [x] 1.2 Register `"xyz"` in the source registry pointing to `WmtsSource` (add `register_source("xyz", WmtsSource)` alongside existing `"wmts"` registration)
- [x] 1.3 Verify: existing tests pass (`just test`)

## 2. WMTS Capabilities parser

- [x] 2.1 Create `src/cartoload/downloader/wmts/capabilities.py` with XML parsing functions using `xml.etree.ElementTree`
- [x] 2.2 Define dataclasses: `WmtsCapabilities`, `WmtsLayer`, `TileMatrixSet`, `TileMatrix`, `ResourceUrl`
- [x] 2.3 Implement parsing of `<Contents>/<Layer>` elements — extract Identifier, Title, BoundingBox, TileMatrixSetLink, ResourceURL, Style
- [x] 2.4 Implement parsing of `<Contents>/<TileMatrixSet>` elements — extract Identifier, SupportedCRS, and TileMatrix entries (ScaleDenominator, TopLeftCorner, TileWidth, TileHeight, MatrixWidth, MatrixHeight)
- [x] 2.5 Implement ResourceURL template variable mapping: `{TileMatrix}` → `${z}`, `{TileCol}` → `${x}`, `{TileRow}` → `${y}`, `{Style}` → style value, `{TileMatrixSet}` → TMS identifier
- [x] 2.6 Add resolution function: given layer ID + TileMatrixSet ID, return the URL template, CRS, and tile format
- [x] 2.7 Write unit tests for Capabilities parsing with a sample WMTS Capabilities XML fixture — verify: `just test`

## 3. WMTS tile grid computation from TileMatrixSet

- [x] 3.1 Create `src/cartoload/downloader/wmts/tile_grid.py` with tile grid math derived from TileMatrixSet parameters
- [x] 3.2 Implement `bbox_to_tile_indices(bbox, tile_matrix_set, zoom)` using the TileMatrix scale, origin, and tile size — generic formula for any TMS
- [x] 3.3 Implement `compute_tile_bounds(x, y, tile_matrix, tile_matrix_set)` returning tile bounding box in the TMS CRS
- [x] 3.4 Verify: GoogleMapsCompatible TMS produces same results as existing hardcoded Web Mercator tile math — verify: unit test comparing both approaches for several bboxes/zoom levels
- [x] 3.5 Verify: WGS84 TMS produces correct geographic tile bounds — verify: unit test with known tile coordinates

## 4. Extend WmtsSource with Capabilities mode

- [x] 4.1 Add `capabilities_url` and `tile_matrix_set` fields to `SourceConfig` dataclass
- [x] 4.2 Add mode detection logic to `WmtsSource`: URL with `${x}/${y}/${z}` → template mode; `capabilities_url` present or URL matches Capabilities pattern → Capabilities mode
- [x] 4.3 Implement Capabilities-mode `download()`: fetch and parse Capabilities, resolve layer+TMS, construct URL template from ResourceURL, create `WmtsDownloader` with resolved parameters
- [x] 4.4 In Capabilities mode, use the TileMatrixSet-based tile grid computation instead of hardcoded Web Mercator math
- [x] 4.5 Verify: Capabilities mode can fetch and parse swisstopo Capabilities and create a working WmtsDownloader — verify: integration test

## 5. Update config and examples

- [x] 5.1 Add WMTS Capabilities example config in `examples/configs/sources/` (alongside existing URL-template config)
- [x] 5.2 Verify: existing URL-template configs still work unchanged — verify: `just test` (869 passed, 2 skipped)

## 6. Tests and final verification

- [x] 6.1 Write test: `type: xyz` resolves to `WmtsSource` and operates in template mode
- [x] 6.2 Write test: `type: wmts` with `capabilities_url` operates in Capabilities mode
- [x] 6.3 Write test: `type: wmts` with URL template operates in template mode (existing behavior preserved)
- [x] 6.4 Run full test suite: `just test` — 869 passed, 2 skipped
- [x] 6.5 Run type checks: `just check types` — no new type errors in changed files
- [x] 6.6 Run linter/formatter: `just check` — all passed
