# Layers

Layer configuration files define map layers to build. They reference source IDs from source config files.

## Simple layer

A simple layer references a single source and produces one IMG file:

```yaml
bounds:
  west: 6.5
  east: 7.5
  south: 46.5
  north: 47.0

layers:
  my_layer:
    name: "My Layer"
    description: "Layer description"
    type: raster
    source: my_wmts
    wmts_layer: my_wmts_layer_name
    zoom_levels: [10, 12, 14]
    exporter: garmin_img
    output: my_layer.img
```

### Source reference

The `source` field can be either a string (source ID) or a dict with a `ref` key plus variable overrides:

```yaml
# String form (backward compatible)
source: my_wmts

# Dict form (with variable overrides)
source:
  ref: my_wmts
  layer: my_wmts_layer_name
  extension: png
```

When using the dict form, all keys except `ref` become `source_args` — these override source `defaults` for template variable resolution.

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Display name for the layer |
| `description` | no | Layer description |
| `type` | no | Layer type (default: `raster`) |
| `source` | yes* | Source ID (string) or dict with `ref` + args |
| `source_args` | no | Template variable overrides (merged with source `defaults`) |
| `wmts_layer` | no | Backward compat: maps to `source_args.layer` |
| `extension` | no | Backward compat: maps to `source_args.extension` (default: `jpeg`) |
| `zoom_levels` | yes | List of zoom levels to include |
| `exporter` | no | Export format (default: `garmin_img`) |
| `output` | yes | Output filename |
| `bounds` | top-level | Geographic bounds (`west`, `east`, `south`, `north`) in degrees |

*`source` is not required for composite layers (see below).

### wmts_layer vs source_args

The `wmts_layer` and `extension` fields are backward-compatible shorthands that map into `source_args`:

```yaml
# Old style (backward compat)
source: swisstopo_wmts
wmts_layer: ch.swisstopo.pixelkarte-farbe
extension: png

# New style (dict source)
source:
  ref: swisstopo_wmts
  layer: ch.swisstopo.pixelkarte-farbe
  extension: png

# Equivalent explicit source_args
source: swisstopo_wmts
source_args:
  layer: ch.swisstopo.pixelkarte-farbe
  extension: png
```

If both a shorthand field and the corresponding `source_args` key are provided, `source_args` takes precedence.

## Composite layers

Composite layers combine multiple raster sub-layers into a single IMG file. This is useful for overlaying thematic data (ski routes, hiking trails) on top of a basemap.

Instead of a `source` field, composite layers define a `layers` list of sub-layers that are blended bottom-to-top using alpha compositing (painter's algorithm).

```yaml
bounds:
  west: 5.96
  east: 10.49
  south: 45.82
  north: 47.81

layers:
  ch_basemap:
    name: "Switzerland 1:25k"
    source: swisstopo_wmts
    wmts_layer: ch.swisstopo.pixelkarte-farbe
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 17]
    exporter: garmin_img
    output: ch_basemap.img

  ch_ski_hikes:
    name: "Switzerland Ski and Hikes"
    description: "Basemap with ski and hiking route overlays"
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 17]
    exporter: garmin_img
    output: ch_ski_hikes.img
    layers:
      - ref: ch_basemap
      - name: "Skiroutes"
        source:
          ref: swisstopo_wmts
          layer: ch.swisstopo.skiroutes
        zoom_levels: [9, 11, 12, 13, 14, 15]
        extension: png
        opacity: 0.6
      - ref: ch_basemap
        opacity: {12: 0.3, 14: 0.8}
        zoom_levels: [8, 9, 11]
```

### Sub-layer types

Each entry in the `layers` list is either an **inline** sub-layer or a **ref** sub-layer:

#### Inline sub-layer

Defines a sub-layer with its own source (string or dict form):

```yaml
- name: "Skiroutes"
  source:
    ref: swisstopo_wmts
    layer: ch.swisstopo.skiroutes
  zoom_levels: [9, 11, 12, 13, 14, 15]
  extension: png
  opacity: 0.6
```

#### Ref sub-layer

References an existing top-level layer (DRY config). Optional overrides for `zoom_levels` and `opacity`:

```yaml
- ref: ch_basemap
  zoom_levels: [8, 9, 11, 12, 13]
  opacity: 0.8
```

Ref sub-layers cannot point to other composite layers.

### Sub-layer fields

| Field | Required | Description |
|-------|----------|-------------|
| `source` | inline only | Source ID (string) or dict with `ref` + args |
| `wmts_layer` | inline only | Backward compat: maps to `source_args.layer` |
| `extension` | no | Backward compat: maps to `source_args.extension` (default: `jpeg`) |
| `source_args` | no | Template variable overrides (merged with source `defaults`) |
| `zoom_levels` | yes | Zoom levels this sub-layer contributes to |
| `opacity` | no | Uniform float (0.0–1.0, default 1.0) or per-zoom dict `{zoom: opacity}` |
| `ref` | ref only | ID of an existing top-level layer |

### Opacity

Opacity controls how transparent a sub-layer appears:

- **Uniform**: a float between 0.0 (fully transparent) and 1.0 (fully opaque)
- **Per-zoom**: a mapping from zoom level to opacity value

```yaml
opacity: 0.6                    # uniform
opacity: {12: 0.3, 14: 0.8}    # per-zoom
```

### Tile fallback

When a sub-layer declares a zoom level but a specific tile is unavailable (404 from server), the system automatically falls back to the closest lower zoom level in the sub-layer's `zoom_levels` list and upscales that tile. If no lower-zoom fallback exists, the sub-layer is skipped for that tile position.

Fallback only applies when the zoom level is *declared* but the tile is missing. Zoom levels intentionally omitted from `zoom_levels` are not subject to fallback.
