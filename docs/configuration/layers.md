# Layers and Targets

Layer configuration files define **layer definitions** (reusable data source + processing config) and **build targets** (what to produce). They reference source IDs from source config files.

## Concepts

### Layers (definitions)

Layer definitions describe *what data to use and how to process it*. They are reusable and have no output file or exporter — they are purely definitions.

### Targets (build instructions)

Build targets describe *what to produce*. Each target specifies an output file, an exporter, and an ordered list of layer entries. A target can reference defined layers (by `ref`) or define layers inline.

Single-layer targets are the simplest case — one layer entry producing one file. Composite targets combine multiple layer entries, blended bottom-to-top using alpha compositing (painter's algorithm).

## File structure

A typical layer config file has three sections:

```yaml
includes:
  - ../sources/swisstopo.yaml

# Default bounding box for all layers/targets in this file
bounds:
  west: 5.96
  east: 10.49
  south: 45.82
  north: 47.81

# Layer definitions (reusable, no output)
layers:
  my_basemap:
    name: "My Basemap"
    format: wmts
    source:
      ref: my_wmts
      layer: ch.swisstopo.pixelkarte-farbe
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]

  my_overlay:
    name: "My Overlay"
    format: wmts
    source:
      ref: my_wmts
      layer: ch.swisstopo.skiroutes
      extension: png
    zoom_levels: [11, 12, 13, 14, 15, 16]

# Build targets (what to produce, with output files)
targets:
  my_map:
    name: "My Map"
    output: my_map.img
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]
    layers:
      - ref: my_basemap
      - ref: my_overlay
        opacity: 0.6
        zoom_levels: [13, 14, 15, 16]
```

### Includes

The `includes` directive loads other config files (typically source definitions). Paths are relative to the current file. Includes are processed depth-first with last-file-wins merge semantics.

### File-level bounds

A top-level `bounds` key sets default bounds for all layers and targets in the file. Individual layers and targets can override this.

There are two formats for bounds:

**Anonymous bounds** (file-level default, backward compatible):

```yaml
bounds:
  west: 5.96
  east: 10.49
  south: 45.82
  north: 47.81
```

**Named bounds** (reusable, slug-referenced):

```yaml
bounds:
  switzerland:
    west: 5.96
    east: 10.49
    south: 45.82
    north: 47.81
  bern:
    west: 7.31
    east: 7.57
    south: 46.88
    north: 47.06
```

The loader auto-detects the format: if all keys are in `{west, east, south, north}`, it's anonymous; otherwise it's named bounds.

Layers and targets can reference named bounds by slug:

```yaml
layers:
  my_layer:
    name: "My Layer"
    source: my_source
    zoom_levels: [10, 12]
    bounds: switzerland   # references the named bounds above
```

Or use inline coordinates:

```yaml
targets:
  my_target:
    output: out.img
    layers: [...]
    bounds:               # inline coordinates
      west: 7.0
      east: 8.0
      south: 46.5
      north: 47.0
```

Named bounds are merged across includes with last-file-wins semantics.

## Layer definitions

Each entry under `layers:` is a named, reusable definition:

```yaml
layers:
  ch_basemap:
    name: "Switzerland Basemap"
    description: "Swisstopo national map"
    format: wmts
    source:
      ref: swisstopo_wmts
      layer: ch.swisstopo.pixelkarte-farbe
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]
```

### Layer fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Display name for the layer |
| `description` | no | Layer description |
| `format` | yes | Data format: `geotiff`, `gpkg`, or `wmts` — selects the processing provider |
| `source` | yes | Source ID (string) or dict with `ref` + args (see [Source reference](#source-reference)) |
| `source_args` | no | Template variable overrides (merged with source `defaults`) |
| `zoom_levels` | yes | List of zoom levels to include |
| `bounds` | no | Geographic bounds: inline (`west`, `east`, `south`, `north`), a slug referencing named bounds, or inherited from file-level if omitted |
| `rules` | no | Inline style rules for vector/rasterized layers |
| `style` | no | Path to QML style file for vector/rasterized layers |
| `garmin_types` | no | Garmin type mapping for vector features |

### Source reference

The `source` field can be a string (source ID) or a dict with a `ref` key plus variable overrides:

```yaml
# String form
source: my_wmts

# Dict form (with variable overrides)
source:
  ref: my_wmts
  layer: ch.swisstopo.pixelkarte-farbe
  extension: png
```

When using the dict form, all keys except `ref` become `source_args` — these override source `defaults` for template variable resolution.

### Format field

The `format` field determines how the data is processed:

| Format | Source types | Description |
|--------|-------------|-------------|
| `wmts` | `wmts` | WMTS tile service — tiles downloaded and re-encoded |
| `geotiff` | `stac`, `path` | GeoTIFF raster data — reprojected, mosaicked, and tiled |
| `gpkg` | `stac`, `path` | GeoPackage vector data — rasterized using style rules |

### Backward compat fields

- `wmts_layer` — maps to `source_args.layer`
- `extension` — maps to `source_args.extension`

If both a shorthand field and `source_args` are provided, `source_args` takes precedence.

## Build targets

Each entry under `targets:` defines what to build:

```yaml
targets:
  my_map:
    name: "My Map"
    output: my_map.img
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]
    layers:
      - ref: my_basemap
```

### Target fields

| Field | Required | Description |
|-------|----------|-------------|
| `output` | yes | Output filename (e.g. `my_map.img`) |
| `layers` | yes | Ordered list of layer entries (see [Layer entries](#layer-entries)) |
| `name` | no | Display name |
| `description` | no | Target description |
| `exporter` | no | Export format (default: `garmin_img`) |
| `zoom_levels` | no | List of zoom levels — inherited from referenced layers if omitted |
| `bounds` | no | Geographic bounds: inline, a slug referencing named bounds, or inherited from file-level/referenced layers if omitted |

### Zoom levels and bounds inheritance

Targets can omit `zoom_levels` and `bounds`. When omitted:

- **zoom_levels**: Resolved from the union of all referenced layer definitions' zoom levels
- **bounds**: Resolved from the enclosing bounding box of all referenced layer definitions' bounds

This keeps targets DRY — the data source definitions own the zoom/bounds, and the target just says "build them all."

## Layer entries

Each item in a target's `layers:` list is either a **ref entry** or an **inline entry**:

### Ref entry

References a top-level layer definition. Optional overrides for `zoom_levels` and `opacity`:

```yaml
- ref: my_basemap
  zoom_levels: [8, 9, 11]
  opacity: 0.8
```

### Inline entry

Defines a layer directly in the target (no top-level layer definition needed):

```yaml
- name: "Overlay"
  format: wmts
  source:
    ref: my_wmts
    layer: ch.swisstopo.skiroutes
    extension: png
  zoom_levels: [13, 14, 15, 16]
  opacity: 0.6
```

### Entry fields

| Field | Required | Description |
|-------|----------|-------------|
| `ref` | ref only | ID of a top-level layer definition |
| `source` | inline only | Source ID or dict (same as layer `source`) |
| `format` | inline only | Data format (`geotiff`, `gpkg`, `wmts`) |
| `name` | no | Display name (inherited from ref layer if omitted) |
| `zoom_levels` | no | Zoom levels this entry contributes to |
| `opacity` | no | Uniform float (0.0–1.0, default 1.0) or per-zoom dict |
| `source_args` | no | Template variable overrides |
| `asset_filter` | no | Key-value filter for STAC asset selection |
| `rules` | no | Inline style rules for vector/rasterized layers |
| `style` | no | Path to QML style file |
| `garmin_types` | no | Garmin type mapping for vector features |
| `extension` | no | Backward compat: maps to `source_args.extension` |

An entry must have either `ref` or `source`, but not both.

## Opacity

Opacity controls how transparent a layer entry appears in composite targets:

- **Uniform**: a float between 0.0 (fully transparent) and 1.0 (fully opaque)
- **Per-zoom**: a mapping from zoom level to opacity value

```yaml
opacity: 0.6                    # uniform
opacity: {12: 0.3, 14: 0.8}    # per-zoom
```

## Tile fallback

When a layer entry declares a zoom level but a specific tile is unavailable (404 from server), the system automatically falls back to the closest lower zoom level in the entry's `zoom_levels` list and upscales that tile. If no lower-zoom fallback exists, the entry is skipped for that tile position.

Fallback only applies when the zoom level is *declared* but the tile is missing. Zoom levels intentionally omitted from `zoom_levels` are not subject to fallback.

## Products

A `products` section defines product catalogs for server-side use (e.g., pricing, download tokens). This section is optional and ignored by the CLI pipeline — it exists for the server to consume.

```yaml
products:
  outdoor-summer:
    name: "Outdoor Summer"
    price: 25.0
    currency: CHF
    targets: [ch_outdoor_summer]
    token_max_downloads: 10
    token_expiry_days: 60
    sort_order: 1
```

### Product fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | no | Display name (defaults to the product slug) |
| `price` | no | Price (default: `0.0`) |
| `currency` | no | Currency code (default: `CHF`) |
| `targets` | no | List of target slugs this product includes (validated on load) |
| `token_max_downloads` | no | Max downloads per token (default: `5`) |
| `token_expiry_days` | no | Token validity in days (default: `30`) |
| `sort_order` | no | Display sort order (default: `0`) |

All product target references are validated — a product referencing a nonexistent target slug will raise an error at config load time. Products are merged across includes with last-file-wins semantics.

## Complete example

```yaml
includes:
  - ../sources/swisstopo.yaml

bounds:
  west: 5.96
  east: 10.49
  south: 45.82
  north: 47.81

layers:
  basemap:
    name: "Switzerland Basemap"
    format: wmts
    source:
      ref: swisstopo_wmts
      layer: ch.swisstopo.pixelkarte-farbe
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]

  hiking:
    name: "Hiking Trails"
    format: wmts
    source:
      ref: swisstopo_wmts
      layer: ch.swisstopo.swisstlm3d-wanderwege
      extension: png
    zoom_levels: [11, 12, 13, 14, 15, 16]

  skiroutes:
    name: "Skiroutes"
    format: wmts
    source:
      ref: swisstopo_wmts
      layer: ch.swisstopo-karto.skitouren
      extension: png
    zoom_levels: [11, 12, 13, 14, 15, 16]

targets:
  winter_map:
    name: "Switzerland Winter Outdoor"
    output: ch_winter.img
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]
    layers:
      - ref: basemap
      - ref: hiking
        opacity: {13: 0.4, 14: 0.6, 15: 0.7, 16: 0.7}
        zoom_levels: [13, 14, 15, 16]
      - ref: skiroutes
        opacity: {13: 0.5, 14: 0.6, 15: 0.7, 16: 0.7}
        zoom_levels: [13, 14, 15, 16]

  simple_basemap:
    output: ch_basemap.img
    layers:
      - ref: basemap
```

Note how `simple_basemap` omits `zoom_levels` and `bounds` — they are inherited from the referenced `basemap` layer definition.
