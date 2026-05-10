# cartoload

Convert official geodata into GPS device maps.

cartoload is an open-source CLI tool and Python library that converts geodata from WMTS, WMS, GeoTIFF, or vector sources into maps for GPS devices — primarily Garmin IMG format.

## Features

- Download maps from WMTS, XYZ/TMS, and STAC/GeoTIFF sources
- Export to Garmin raster IMG format
- Source-agnostic — configure any WMTS or GeoTIFF provider
- Built-in IMG file analysis and comparison tools
- Usable as CLI tool or Python library

## Quick Start

```bash
pip install cartoload
cartoload build --sources sources.yaml --layers layers.yaml --layer my_layer
```

See [Getting started](getting-started.md) for a full walkthrough.
