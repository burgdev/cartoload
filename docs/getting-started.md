# Getting Started

## Installation

```bash
pip install cartoload
```

Or using [uv](https://docs.astral.sh/uv/):

```bash
uv tool install cartoload
```

## Quick Start

1. Create or use example configuration files for your data source:

```bash
# Example configs are included for common providers
ls examples/configs/sources/
ls examples/configs/layers/
```

2. Build a layer:

```bash
cartoload build \
    --sources examples/configs/sources/swisstopo.yaml \
    --layers examples/configs/layers/switzerland.yaml \
    --layer ch_basemap_25k
```

3. Copy the resulting `.img` file to your GPS device

## Next Steps

- [Build a map](guides/build-a-map.md) — full build workflow with all options
- [Analyze IMG files](guides/analyze-img.md) — inspect and compare IMG files
- [Configuration](configuration/index.md) — understand sources, layers, and how they fit together

## Development

```bash
git clone https://github.com/burgdev/cartoload.git
cd cartoload
uv sync --all-groups
```
