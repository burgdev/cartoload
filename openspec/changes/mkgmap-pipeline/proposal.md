## Why

For vector data like skitour routes and hiking trails, a native Garmin vector IMG provides resolution-independent rendering, device-side searchability, and separate enable/disable on the device. mkgmap is the established open-source tool for generating Garmin vector IMG files from OSM data. By integrating mkgmap as an optional pipeline step, cartoload can produce separate vector overlay IMGs alongside raster base maps.

## What Changes

- **GPKG → OSM XML converter**: Uses `ogr2ogr` to convert GeoPackage features to OSM XML format, exposing all GPKG attributes as OSM tags (no tag mapping required)
- **mkgmap style generator**: Converts the style engine's match rules into mkgmap's native style file format (`lines`, `points`, `polygons`, `options`, `version`)
- **TYP file generator**: Converts visual properties (color, width, dash, border) from `LineStyle` into Garmin TYP file format with XPM bitmap patterns for dashed/bordered lines
- **mkgmap runner**: Subprocess wrapper that runs mkgmap with generated style + TYP + OSM input, producing a `.img` file
- **Pipeline integration**: New output path in `build_gpkg_layer()` that produces a separate vector IMG when the layer config requests it

## Capabilities

### New Capabilities
- `mkgmap-pipeline`: Convert GeoPackage data to Garmin vector IMG files via mkgmap, with auto-generated styles and TYP files

### Modified Capabilities

## Impact

- **New module**: `src/cartoload/mkgmap/` — style generator, TYP generator, runner, ogr2ogr wrapper
- **Pipeline**: `build_gpkg_layer()` gains a vector output path
- **Optional dependency**: mkgmap (Java) + ogr2ogr (GDAL) — both must be on PATH; cartoload checks availability and reports clear errors if missing
- **Output**: Separate `.img` file per vector layer, placed alongside raster IMGs
- **Upstream**: Consumes output from `gpkg-download` and `vector-style-engine` changes
