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

1. Create or use example configuration files for your data source
2. Build a layer:

```bash
cartoload build \
    --sources examples/configs/sources/swisstopo.yaml \
    --layers examples/configs/layers/switzerland.yaml \
    --layer ch_basemap_25k
```

3. Copy the resulting `.img` file to your GPS device

## Development

```bash
git clone https://github.com/burgdev/cartoload.git
cd cartoload
uv sync --all-groups
```
