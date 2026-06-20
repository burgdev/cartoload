# cartoload

Convert raster geodata into Garmin GPS raster maps (`*.img`).

`cartoload` is an open-source CLI tool and Python library that converts geodata from WMTS or GeoTIFF source into raster maps for Garmin GPS devices. It is the pipeline engine behind the [Cartoload](https://cartoload.com) service, but is fully usable standalone.

## Installation

```bash
pip install cartoload
```

or just run it with `uvx`

```bash
uvx cartoload --help
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

### Docker Build

```bash
just docker build [--mkgmap]
./cartoload-docker build -c config.yaml -l my_layer          # server image
./cartoload-docker --local build -c config.yaml -l my_layer   # local image
./cartoload-docker --local --mkgmap build ...                  # local mkgmap image
```

## License

`LGPL` - see [LICENSE](https://github.com/burgdev/cartoload/blob/main/LICENSE) file.
