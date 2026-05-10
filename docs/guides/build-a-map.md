# Build a Map

This guide walks through building a Garmin IMG map from a tile source.

## Prerequisites

- A source configuration file (see [Sources](../configuration/sources.md))
- A layer configuration file (see [Layers](../configuration/layers.md))

## Basic Build

```bash
cartoload build \
    --sources sources.yaml \
    --layers layers.yaml \
    --layer my_layer
```

This downloads tiles, encodes them into JPEG, and writes a Garmin `.img` file.

## Build Options

### Select a layer

Use `--layer` to build a specific layer. Without it, all layers from the config are built.

```bash
cartoload build -S sources.yaml -L layers.yaml -l my_layer
```

### Override bounds and zoom

Override the bounds and zoom levels defined in the layer config:

```bash
cartoload build -S sources.yaml -L layers.yaml -l my_layer \
    --bounds "7.0,8.0,46.5,47.5" \
    --zoom "12,14,16"
```

Bounds format: `"west,east,south,north"` (decimal degrees).

### Preview images

Generate preview images of each zoom level after building:

```bash
cartoload build -S sources.yaml -L layers.yaml -l my_layer --preview
```

### Force rebuild

Overwrite existing output files:

```bash
cartoload build -S sources.yaml -L layers.yaml -l my_layer -f
```

### Caching

Tiles are cached locally to avoid re-downloading. Control cache behavior:

```bash
# Use a custom cache directory
cartoload build -S sources.yaml -L layers.yaml -l my_layer --cache-dir ./my-cache

# Build from cache only (no downloads)
cartoload build -S sources.yaml -L layers.yaml -l my_layer --no-download
```

### Execution mode

Choose between thread-based or process-based parallelism:

```bash
cartoload build -S sources.yaml -L layers.yaml -l my_layer --executor thread
```

### JPEG quality

Control output JPEG quality (1–100, default 85):

```bash
cartoload build -S sources.yaml -L layers.yaml -l my_layer --quality 90
```

## Output

The build produces:

- `<output-dir>/<layer-name>.img` — the Garmin IMG file
- `<cache-dir>/` — downloaded tiles (reused on subsequent builds)

Copy the `.img` file to your Garmin device's `Garmin/` directory.

## Quick Test Build

For testing, use a small area with preview:

```bash
cartoload build \
    -S examples/configs/sources/swisstopo.yaml \
    -L examples/configs/layers/switzerland.yaml \
    -l ch_basemap_test \
    -y 46.93459 -x 7.51105 -W 5 -H 5 \
    -f --preview --executor thread
```

This builds a 5×5 km area around the given coordinates.
