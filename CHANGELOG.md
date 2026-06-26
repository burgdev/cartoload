<!-- Auto generated. Run 'just release' in order to update -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-26

- Initial release
- Convert WMTS and GeoTIFF raster geodata into Garmin GPS raster maps (`*.img`)
- Unified YAML configuration for sources, layers, and styles
- WMTS tile downloading with on-disk caching and JPEG optimization (mozjpeg trellis quantization)
- Custom Garmin IMG binary writer (GMP container with TRE/RGN/LBL sections and RGN2 raster records)
- CLI (`cartoload build`, `cartoload analyze img`) and reusable Python library (`build_layer`, `SourceConfig`, `LayerConfig`)
- `analyze img` tool for inspecting IMG files and exporting a GeoTIFF mosaic for validation
- Docker image bundling GDAL, mozjpeg, and GMapTool (`gmt`)

[0.1.0]: https://github.com/burgdev/cartoload/releases/tag/v0.1.0
