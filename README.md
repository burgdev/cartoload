# cartoload

Convert official geodata into GPS device maps.

cartoload is an open-source CLI tool and Python library that converts geodata from any WMTS, GeoTIFF, or vector source into maps for GPS devices. It is the pipeline engine behind the Cartoload service, but is fully usable standalone.

## Installation

```bash
pip install cartoload
```

## Quick Start

```bash
# Build a layer from example configs
cartoload build \
    --sources examples/configs/sources/swisstopo.yaml \
    --layers examples/configs/layers/switzerland.yaml \
    --layer ch_basemap_25k
```

## Usage as a Library

```python
from cartoload.config import SourceConfig, LayerConfig
from cartoload.pipeline import build_layer

source = SourceConfig(id="my_source", type="wmts", url_template="...")
layer = LayerConfig(id="my_layer", name="My Layer", source="my_source")
output_path = await build_layer(layer, cache_dir="/tmp/cache")
```

## Documentation

Full documentation is available at [burgdev.github.io/cartoload](https://burgdev.github.io/cartoload/).

## Development

```bash
git clone https://github.com/burgdev/cartoload.git
cd cartoload
uv sync --all-groups
just test
```

## License

MIT
