## Why

The built-in vector rasterizer only supports QML `SimpleLine` symbols. `MarkerLine`, `ArrowLine`, and other symbol types are silently skipped, making many vector styles (ski route dots, direction arrows, point markers) invisible or degraded in rendered output. Building full QML rendering support into cartoload would be significant ongoing effort with little return for a tool focused on Garmin IMG export.

Instead, users who need full QML fidelity can use QGIS Server as an external rendering engine, feeding styled tiles back into the cartoload pipeline through the existing WMTS source type.

## What Changes

- New CLI command `cartoload export-qgis-project` that generates a `.qgs` project file from layer configs, downloading GPKG/GeoTIFF source data as needed
- Add `${bbox}` template variable support to the WMTS URL builder, enabling QGIS WMS `GetMap` URLs as a `wmts` source
- Example `docker-compose.qgis.yml` with a ready-to-use QGIS Server setup
- Documentation guide: "Using QGIS with cartoload" explaining the full workflow

## Capabilities

### New Capabilities
- `qgis-project-export`: Generate QGIS `.qgs` project files from cartoload layer configs, with automatic data download for local sources (GPKG, GeoTIFF)
- `wmts-bbox-variable`: Add `${bbox}` (and individual `${west}`, `${south}`, `${east}`, `${north}`) template variable support to the WMTS URL builder for WMS `GetMap` compatibility

### Modified Capabilities

## Impact

- **CLI**: New `export-qgis-project` command in `cli.py`
- **New module**: `src/cartoload/qgis_project.py` for `.qgs` XML generation
- **WMTS downloader**: Small change to `_build_tile_url()` in `src/cartoload/downloader/wmts.py` to support `${bbox}` and individual coordinate variables
- **Documentation**: New guide at `docs/guides/qgis-integration.md`
- **Docker**: New `docker-compose.qgis.yml` in project root
- **Dependencies**: No new Python dependencies — `.qgs` generation uses `xml.etree.ElementTree` from stdlib
