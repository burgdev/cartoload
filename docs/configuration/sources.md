# Sources

Source configuration files define geodata providers. Place them in a directory of your choice and pass them via `--sources`.

## Source types

### WMTS

```yaml
sources:
  my_wmts:
    type: wmts
    url_template: "https://example.com/${layer}/${z}/${x}/${y}.png"
    defaults:
      layer: default_layer_name
    attribution: "© Example"
    rate_limit_ms: 150
    max_threads: 4
```

### WMTS with multiple URLs

```yaml
sources:
  swisstopo:
    type: wmts
    defaults:
      layer: ch.swisstopo.pixelkarte-farbe
      extension: jpeg
    urls:
      - "https://wmts0.example.com/${layer}/default/current/3857/${z}/${x}/${y}.${extension:-jpeg}"
      - "https://wmts1.example.com/${layer}/default/current/3857/${z}/${x}/${y}.${extension:-jpeg}"
    attribution: "© Example"
```

### STAC

Queries a STAC API collection endpoint, downloads GeoTIFF assets, and processes them into map tiles.

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

The `${layer}` variable resolves to the collection ID from `defaults` or `source_args`.

#### Asset filtering

When a STAC collection has multiple GeoTIFF assets per item (e.g. different variants or resolutions), use `asset_filter` to select which one to download. Specify key-value pairs that must match the asset's properties:

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
layers:
  my_layer:
    source:
      ref: swisstopo_stac
      asset_filter:
        geoadmin:variant: krel
```

Layer-level `asset_filter` overrides the source-level default. When no filter is set, the first GeoTIFF asset by media type is selected.

### GeoTIFF

References GeoTIFF files directly — local paths (relative to config file or absolute), directories (scanned recursively), or HTTP URLs.

```yaml
sources:
  my_geotiff:
    type: geotiff
    urls:
      - "/data/geotiffs/"                    # directory, scanned recursively
      - "../cache/my_stac/my_collection/"    # relative path to directory
      - "https://example.com/tile.tif"       # remote URL, downloaded to cache
    attribution: "© Example"
```

## Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | yes | Source type: `wmts`, `stac`, or `geotiff` |
| `url_template` | conditional | URL template (use instead of `urls`) |
| `urls` | conditional | List of URLs or paths (use instead of `url_template`) |
| `attribution` | no | Attribution string |
| `defaults` | no | Default variable values for template substitution |
| `asset_filter` | no | Key-value filter for STAC asset selection (nested dict under `defaults` or layer source) |
| `rate_limit_ms` | no | Delay between requests in ms (default: 150) |
| `max_threads` | no | Max download threads (default: 4) |
| `crs` | no | Override source CRS (default: EPSG:3857 for WMTS, auto-detected for stac/geotiff) |

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
