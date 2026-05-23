# Build a Map

This guide walks through building a Garmin IMG map from a tile source.

## Prerequisites

- A configuration file with sources, layers, and targets defined (see [Configuration](../configuration/index.md))

## Basic Build

```bash
cartoload build -c layers.yaml -l my_target
```

This downloads tiles from the configured source, processes them, and writes a Garmin `.img` file. The `-l` flag selects a target (or layer) ID from the config file.

## Build Options

### Select a target

Use `-l` to build a specific target or layer from the config:

```bash
cartoload build -c examples/configs/layers/switzerland.yaml -l ch_swisstopo_basemap
```

Targets are resolved first — if a target with the given ID exists, it is used. Otherwise, the layer definition is auto-wrapped as a single-layer target.

### Override bounds and zoom

Override the bounds defined in the layer config:

```bash
# Using center point + dimensions
cartoload build -c layers.yaml -l my_target \
    -x 7.5 -y 47.0 -W 10 -H 10 \
    -z "12,14,16"

# Using bounding box
cartoload build -c layers.yaml -l my_target \
    -b 7.0 46.5 8.0 47.5 \
    -z "12,14,16"
```

Bounds format: `-b` takes `W S E N` (four decimal degrees). `-x`/`-y` takes a center point, `-W`/`-H` takes dimensions in km.

### Preview images

Generate preview images of each zoom level after building:

```bash
cartoload build -c layers.yaml -l my_target --preview
```

### Force rebuild

Overwrite existing output files:

```bash
cartoload build -c layers.yaml -l my_target -f
```

### Caching

Tiles are cached locally to avoid re-downloading. Control cache behavior:

```bash
# Use a custom cache directory
cartoload build -c layers.yaml -l my_target -C ./my-cache

# Build from cache only (no downloads)
cartoload build -c layers.yaml -l my_target --no-download
```

### Execution mode

Choose between thread-based or process-based parallelism:

```bash
cartoload build -c layers.yaml -l my_target --executor thread
```

### JPEG quality

Control output JPEG quality (1–100):

```bash
cartoload build -c layers.yaml -l my_target -q 90
```

## Output

The build produces:

- `<output-dir>/<target-name>.img` — the Garmin IMG file
- `<cache-dir>/` — downloaded tiles (reused on subsequent builds)

Copy the `.img` file to your Garmin device's `Garmin/` directory.

## Quick Test Build

For testing, use a small area with preview:

```bash
cartoload build \
    -c examples/configs/layers/test.yaml \
    -l ch_basemap_25k \
    -y 46.93459 -x 7.51105 -W 5 -H 5 \
    -f --preview --executor thread
```

This builds a 5x5 km area around the given coordinates.
