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

### GeoTIFF (STAC)

```yaml
sources:
  my_stac:
    type: geotiff
    stac_url: "https://stac.example.com/"
    attribution: "© Example"
```

## Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | yes | Source type: `wmts` or `geotiff` |
| `url_template` | conditional | URL template for WMTS (use instead of `urls`) |
| `urls` | conditional | List of URL templates for WMTS (use instead of `url_template`) |
| `stac_url` | conditional | STAC API URL for GeoTIFF sources |
| `attribution` | no | Attribution string |
| `defaults` | no | Default variable values for template substitution |
| `rate_limit_ms` | no | Delay between requests in ms (default: 150) |
| `max_threads` | no | Max download threads (default: 4) |
| `crs` | no | Override source CRS (default: EPSG:3857 for WMTS) |

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

Common config-level variables include `${layer}` (WMTS layer name) and `${extension}` (tile format), but these are not predefined — they must be set via `defaults` or `source_args`.

### Per-tile variables

Resolved at download time for each tile:

| Variable | Description |
|----------|-------------|
| `${x}` | Tile X coordinate |
| `${y}` | Tile Y coordinate |
| `${z}` | Zoom level |
| `${zoom}` | Zoom level (alias for `${z}`) |

These are the only predefined variables. All other variables (e.g., `${layer}`, `${extension}`) are config-level and must be provided via `defaults` or `source_args`.

### Legacy syntax

For backward compatibility, `{x}`, `{y}`, `{z}`, `{zoom}` (without `$`) are also supported in URL templates.
