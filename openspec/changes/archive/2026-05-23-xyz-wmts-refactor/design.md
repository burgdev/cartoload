## Context

cartoload has a single tile source type `wmts` that currently only supports URL-template-based tile fetching with hardcoded Web Mercator (EPSG:3857) tile math. It never reads WMTS GetCapabilities documents. Real WMTS services publish Capabilities XML with layer metadata, TileMatrixSet definitions, multiple CRS options, and bounding boxes — all information that could be auto-discovered.

Current class hierarchy:
```
Source (ABC) → WmtsSource (registered as "wmts")
BaseDownloader (ABC) → WMTSDownloader
LayerProvider (ABC) → WmtsProvider (registered as "wmts")
```

## Goals / Non-Goals

**Goals:**
- Extend `WmtsSource` with Capabilities parsing as a second mode (no renaming)
- Keep existing URL-template mode working unchanged — zero migration
- Add `type: xyz` as an alias for `WmtsSource` (explicit opt-in for URL-template mode)
- Support tile grids from WMTS Capabilities (GoogleMapsCompatible/EPSG:3857 and WGS84/EPSG:4326 initially)
- Auto-detect mode within `WmtsSource` based on URL pattern

**Non-Goals:**
- Full OGC WMTS 1.0.0 compliance (KVP, SOAP, RESTful) — we only support RESTful ResourceURL encoding
- WMTS layer styling/theming — we only fetch raster tiles
- Support for non-rectangular tile matrices
- Caching or incremental refresh of Capabilities documents (fetch on each build for now)
- Tile matrices beyond GoogleMapsCompatible (EPSG:3857) and WGS84 (EPSG:4326) in the initial implementation
- Renaming `WMTSDownloader` — it stays as-is

## Decisions

### D1: Single `WmtsSource` with two modes (no `XyzSource` class)

Keep `WmtsSource` as the single source class. It operates in two modes:
- **Template mode** (current): URL contains `${x}/${y}/${z}` → use hardcoded Web Mercator grid, build URLs from template
- **Capabilities mode** (new): URL is a Capabilities endpoint → parse XML, resolve layer+TileMatrixSet, build URL template from ResourceURL

Both modes produce a `WmtsDownloader` instance configured with a URL template and tile grid parameters. The downloader doesn't know or care which mode produced it.

```
WmtsSource (type: "wmts" or "xyz")
    │
    ├── Template mode (URL with ${x}/${y}/${z})
    │     → hardcoded Web Mercator grid
    │     → URL template from config
    │
    └── Capabilities mode (capabilities_url or Capabilities URL)
          → parse GetCapabilities XML
          → resolve layer + TileMatrixSet
          → URL template from ResourceURL
    │
    ▼
    WmtsDownloader (shared)
    ┌──────────────────────────────────┐
    │ Rate limiting, retry, caching    │
    │ World file generation            │
    │ Multi-URL round-robin            │
    │ Thread pool downloads            │
    └──────────────────────────────────┘
```

**Alternative considered:** Separate `XyzSource` and `WmtsSource` classes. Rejected — the distinction is not user-facing. Users point at a tile service and we figure out the rest. Two classes means more code, migration headaches, and deprecation warnings for no real benefit.

### D2: `type: xyz` as alias for `WmtsSource`

Register `type: xyz` → `WmtsSource`. No deprecation warning — it's just an explicit way to say "I'm using URL-template mode". If someone uses `type: xyz` with a Capabilities URL, that's fine too — auto-detection within `WmtsSource` handles it.

### D3: WMTS Capabilities parsing with stdlib XML

Use Python's `xml.etree.ElementTree` to parse WMTS GetCapabilities XML. No external dependencies.

The parser extracts:
- Layer identifiers and titles
- TileMatrixSet definitions (CRS, scale denominators, matrix dimensions, tile size)
- ResourceURL templates (RESTful encoding) for each layer+TileMatrixSet combination
- Bounding boxes per layer

Returns a `WmtsCapabilities` dataclass used to:
1. Resolve requested layer + TileMatrixSet → URL template + CRS
2. Build tile grid parameters for tile coordinate computation

**Alternative considered:** OWSLib. Rejected — heavy dependency for ~200 lines of stdlib parsing.

### D4: Tile grid computation for Capabilities mode

Template mode keeps the existing hardcoded Web Mercator tile math.

Capabilities mode uses TileMatrixSet parameters from the parsed Capabilities:
- Each `TileMatrix` has: `ScaleDenominator`, `TopLeftCorner`, `TileWidth`, `TileHeight`, `MatrixWidth`, `MatrixHeight`
- Generic formula: pixel span = `scale * 0.00028`, tile span = `pixel_span * tile_size`
- GoogleMapsCompatible: produces identical results to the hardcoded math (verifiable)
- WGS84: uses geographic coordinates

### D5: Auto-detection logic

Within `WmtsSource`:
- URL contains `${x}`, `${y}`, `${z}` → template mode
- URL ends with `WMTSCapabilities.xml` or contains `GetCapabilities`+`WMTS` → Capabilities mode
- `capabilities_url` field present → Capabilities mode (URLs field used as additional endpoints)

In the source registry:
- `${x}/${y}/${z}` patterns → `wmts` (template mode)
- Capabilities URL patterns → `wmts` (Capabilities mode)
- `type: xyz` → `wmts` (alias)

### D6: Config format

**Existing URL-template config (unchanged):**
```yaml
sources:
  swisstopo_wmts:
    type: wmts
    defaults:
      layer: ch.swisstopo.pixelkarte-farbe
      extension: jpeg
    urls:
      - "https://wmts0.geo.admin.ch/1.0.0/${layer}/default/current/3857/${z}/${x}/${y}.${extension:-jpeg}"
    rate_limit_ms: 150
    max_threads: 4
```

**New Capabilities config:**
```yaml
sources:
  swisstopo_wmts:
    type: wmts
    capabilities_url: "https://wmts.geo.admin.ch/1.0.0/WMTSCapabilities.xml"
    layer: ch.swisstopo.pixelkarte-farbe
    tile_matrix_set: 3857  # optional, defaults to GoogleMapsCompatible
    # crs auto-detected from TileMatrixSet
    # urls auto-constructed from ResourceURL in Capabilities
```

**Optional explicit xyz alias:**
```yaml
sources:
  swisstopo_xyz:
    type: xyz  # alias, same behavior as type: wmts
    urls:
      - "https://wmts0.geo.admin.ch/1.0.0/${layer}/default/current/3857/${z}/${x}/${y}.${extension:-jpeg}"
```

## Risks / Trade-offs

- **WMTS Capabilities XML varies between servers** → Mitigated by testing against swisstopo (primary use case). Parse defensively — unknown elements are ignored.
- **Capabilities parsing adds latency** → Only fetched once per build, not per tile. Acceptable.
- **Non-standard tile grids may not render correctly** → Start with GoogleMapsCompatible and WGS84. Log a warning for unrecognized TMS and attempt generic formula.
- **No breaking changes** → Existing configs keep working identically. `type: xyz` is additive.

## Open Questions

- Should we cache the parsed Capabilities document to disk? (Deferred — not needed initially.)
- Should `capabilities_url` also accept a local file path for offline Capabilities? (Nice-to-have, not blocking.)
