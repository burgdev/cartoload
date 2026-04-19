# Sources

Source configuration files define geodata providers. Place them in a directory of your choice and pass them via `--sources`.

## Source types

### WMTS

```yaml
sources:
  my_wmts:
    type: wmts
    url_template: "https://example.com/{layer}/{z}/{x}/{y}.png"
    attribution: "© Example"
    rate_limit_ms: 150
    max_threads: 4
```

### GeoTIFF (STAC)

```yaml
sources:
  my_stac:
    type: geotiff
    stac_url: "https://stac.example.com/"
    attribution: "© Example"
```
