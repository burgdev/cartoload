# Getting Started

## Installation

```bash
pip install cartoload
```

Or using [uv](https://docs.astral.sh/uv/):

```bash
uv tool install cartoload
```

### Docker

Pre-built images are available on GitHub Container Registry:

```bash
docker pull ghcr.io/burgdev/cartoload:latest-base
```

| Variant | Tag suffix | Size | Includes |
|---|---|---|---|
| Base | `-base` | ~640 MB | GDAL, osmium, gmt |
| With mkgmap | `-mkgmap` | ~900 MB | + Java, mkgmap |

Tags follow the pattern `ghcr.io/burgdev/cartoload:<VERSION>-<VARIANT>`, e.g. `v1.2.0-base`.

Use the wrapper script to run cartoload from a pre-built image:

```bash
./cartoload-docker build -c config.yaml -l my_layer
./cartoload-docker -- --help
./cartoload-docker --mkgmap build -c config.yaml -l my_layer
```

The wrapper mounts the current working directory at `/work` inside the container, so relative paths to configs, output, and cache work as expected.

To build locally from the repository (requires [just](https://github.com/casey/just)):

```bash
just docker build              # slim
just docker build mkgmap=yes   # with mkgmap
```

## Quick Start

1. Create or use example configuration files for your data source:

```bash
# Example configs are included for common providers
ls examples/configs/sources/
ls examples/configs/layers/
```

2. Build a target:

```bash
cartoload build \
    -c examples/configs/layers/switzerland.yaml \
    -l ch_swisstopo_basemap
```

The `--layer` (`-l`) flag selects a **target** to build from the `targets:` section of the config file.

3. Copy the resulting `.img` file to your GPS device

## Config structure

cartoload uses a unified config format with two main sections:

- **`sources:`** — where to fetch data from (WMTS services, STAC APIs, local files)
- **`layers:`** — reusable data definitions (source + format + zoom levels, no output)
- **`targets:`** — what to build (output file + ordered list of layer entries)

```yaml
includes:
  - ../sources/swisstopo.yaml

layers:
  my_basemap:
    name: "My Basemap"
    format: wmts
    source:
      ref: swisstopo_wmts
      layer: ch.swisstopo.pixelkarte-farbe
    zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]

targets:
  my_map:
    output: my_map.img
    layers:
      - ref: my_basemap
```

## Next Steps

- [Build a map](guides/build-a-map.md) — full build workflow with all options
- [Analyze IMG files](guides/analyze-img.md) — inspect and compare IMG files
- [Configuration](configuration/index.md) — understand sources, layers, and targets

## Development

```bash
git clone https://github.com/burgdev/cartoload.git
cd cartoload
uv sync --all-groups
```
