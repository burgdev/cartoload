# Configuration

cartoload uses a unified YAML config format with three sections: **sources** (where to get geodata), **layers** (reusable data definitions), and **targets** (what to build). Configs can be split across files and composed with `includes`.

## How it works

``` mermaid
graph LR
  S["Source config\n(swisstopo.yaml)"] --> B["cartoload build"]
  L["Layer config\n(switzerland.yaml)"] --> B
  B --> O["output.img"]
```

1. **Sources** define geodata providers (e.g., a WMTS tile server, a STAC catalog for GeoTIFFs). Each source gets an ID.

2. **Layers** define reusable data source + processing config — what data to use, format, zoom levels, and bounds. They have no output file.

3. **Targets** define what to produce — an output file, an exporter, and an ordered list of layer entries (references or inline). A single-layer target builds one layer; a composite target blends multiple layers.

4. **Build** combines all three — cartoload downloads tiles from the source, processes them, and exports into a Garmin IMG file.

## Minimal example

**Source config** (`sources.yaml`):

```yaml
sources:
  my_tiles:
    type: wmts
    urls:
      - "https://example.com/${layer}/${z}/${x}/${y}.${extension}"
    defaults:
      layer: topo
      extension: png
    attribution: "© Example"
```

**Layer + target config** (`layers.yaml`):

```yaml
bounds:
  west: 7.4
  east: 7.6
  south: 46.9
  north: 47.0

layers:
  my_map:
    name: "My Map"
    type: raster
    format: wmts
    source: my_tiles
    zoom_levels: [10, 12, 14]

targets:
  my_map:
    output: my_map.img
    layers:
      - ref: my_map
```

**Build**:

```bash
cartoload build -c layers.yaml -l my_map
```

The `-l` flag selects a **target** (or layer) ID to build.

## Detail pages

- [Sources](sources.md) — all source types and their options
- [Layers and Targets](layers.md) — layer definitions, build targets, composite layers, opacity, zoom level inheritance
