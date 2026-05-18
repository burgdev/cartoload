# Sources

Source configuration files define geodata providers. Place them in a directory of your choice and reference them via `includes` in your layer config files, or pass them via `--sources`.

## Source types

Source type (`type`) determines the **fetch method** — how data is downloaded or accessed. This is separate from the **data format** (set on layer definitions via `format`).

| Type | Description | Data formats |
|------|-------------|-------------|
| `wmts` | Web Map Tile Service — downloads individual map tiles | `wmts` |
| `stac` | STAC API — queries collection endpoints, downloads assets | `geotiff`, `gpkg` |
| `path` | Local file path — reads files from disk | `geotiff`, `gpkg` |

Source type is detected automatically from URLs but can be set explicitly with the `type` field.

### WMTS

Downloads map tiles from a Web Map Tile Service. URL templates contain per-tile variables (`${x}`, `${y}`, `${z}`) that are resolved at download time.

```yaml
sources:
  my_wmts:
    type: wmts
    defaults:
      layer: default_layer_name
      extension: jpeg
    urls:
      - "https://wmts.example.com/${layer}/default/current/3857/${z}/${x}/${y}.${extension:-jpeg}"
      - "https://wmts1.example.com/${layer}/default/current/3857/${z}/${x}/${y}.${extension:-jpeg}"
    attribution: "© Example"
    rate_limit_ms: 150
    max_threads: 4
```

Multiple URLs are used as fallback/rotation endpoints (load balancing). All URLs must use the same template.

### STAC

Queries a STAC API collection endpoint and downloads assets (GeoTIFF or GeoPackage). The `${layer}` variable resolves to the collection ID from `defaults` or `source_args`.

```yaml
sources:
  my_stac:
    type: stac
    defaults:
      layer: my_collection_id
    urls:
      - "https://stac.example.com/api/v1/collections/${layer}"
    attribution: "© Example"
```

The data format is determined by the layer's `format` field:
- `format: geotiff` — downloads GeoTIFF assets
- `format: gpkg` — downloads GeoPackage (.gpkg.zip) assets, extracts and caches the .gpkg file

#### Asset filtering

When a STAC collection has multiple assets per item (e.g. different variants or resolutions), use `asset_filter` to select which one to download:

```yaml
sources:
  swisstopo_stac:
    type: stac
    defaults:
      layer: ch.swisstopo.pixelkarte-farbe-pk25.noscale
      asset_filter:
        geoadmin:variant: komb
    urls:
      - "https://data.geo.admin.ch/api/stac/v1/collections/${layer}"
```

`asset_filter` can also be set per-layer via the dict source syntax:

```yaml
source:
  ref: swisstopo_stac
  asset_filter:
    geoadmin:variant: krel
```

Layer-level `asset_filter` overrides the source-level default. When no filter is set, the first asset matching the expected media type is selected.

### Path

References local files — directories (scanned recursively for matching files), individual file paths, or HTTP URLs that get downloaded to cache.

```yaml
sources:
  my_local_data:
    type: path
    urls:
      - "/data/geotiffs/"                    # directory, scanned recursively
      - "../cache/my_stac/my_collection/"    # relative path to directory
      - "https://example.com/tile.tif"       # remote URL, downloaded to cache
    attribution: "© Example"
```

## Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | no | Source type: `wmts`, `stac`, or `path` (auto-detected from URLs if omitted) |
| `urls` | yes | List of URL templates or paths |
| `defaults` | no | Default variable values for template substitution |
| `asset_filter` | no | Key-value filter for STAC asset selection |
| `attribution` | no | Attribution string |
| `rate_limit_ms` | no | Delay between requests in ms (default: 150) |
| `max_threads` | no | Max download threads (default: 4) |
| `crs` | no | Override source CRS (default: EPSG:3857 for WMTS, auto-detected for STAC/path) |

## Template variables

All URL template variables use `${VAR}` syntax. There are two resolution phases:

### Config-level variables

Resolved once at pipeline start from source `defaults` and layer `source_args`:

| Syntax | Description |
|--------|-------------|
| `${VAR}` | Variable substitution |
| `${VAR:-default}` | Substitution with inline default |
| `$VAR` | Bare variable (alphanumeric/underscore only) |
| `$$` | Literal `$` |

Variable resolution order (later overrides earlier):

1. Inline defaults (`${VAR:-default}`)
2. Source `defaults` dict
3. Layer `source_args` (from layer config)

Common config-level variables include `${layer}` (WMTS layer name, STAC collection ID) and `${extension}` (tile format), but these are not predefined — they must be set via `defaults` or `source_args`.

### Per-tile variables

Resolved at download time for each tile (WMTS only):

| Variable | Description |
|----------|-------------|
| `${x}` | Tile X coordinate |
| `${y}` | Tile Y coordinate |
| `${z}` | Zoom level |
| `${zoom}` | Zoom level (alias for `${z}`) |

These are the only predefined variables. All other variables (e.g., `${layer}`, `${extension}`) are config-level and must be provided via `defaults` or `source_args`.

### Legacy syntax

For backward compatibility, `{x}`, `{y}`, `{z}`, `{zoom}` (without `$`) are also supported in URL templates.

## Source type detection

When `type` is not explicitly set, it is auto-detected from the first URL:

| Pattern | Detected type |
|---------|--------------|
| URL contains `${x}`, `${y}`, `${z}` or `{x}`, `{y}`, `{z}` | `wmts` |
| URL contains `/collections/` or `/stac/` | `stac` |
| URL starts with `./`, `../`, `/`, or has no `://` scheme | `path` |
| Other | Error — set `type` explicitly |
