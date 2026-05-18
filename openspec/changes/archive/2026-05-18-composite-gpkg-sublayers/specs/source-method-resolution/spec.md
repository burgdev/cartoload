## MODIFIED Requirements

### Requirement: Pipeline dispatch by type, download by source method
The pipeline SHALL dispatch processing based on data type (`geotiff`, `gpkg`, `wmts`). Within each type, the source method determines how files are obtained. This dispatch SHALL apply both to standalone layers and to sub-layers within composite layers.

#### Scenario: geotiff + stac source
- **WHEN** a layer or composite sub-layer uses a `type: geotiff` source with `source: stac`
- **THEN** the pipeline SHALL use `STACDownloader` to fetch GeoTIFF assets, then process via the GeoTIFF pipeline

#### Scenario: geotiff + path source
- **WHEN** a layer or composite sub-layer uses a `type: geotiff` source with `source: path`
- **THEN** the pipeline SHALL use `collect_geotiff_files` to resolve local paths, then process via the GeoTIFF pipeline

#### Scenario: gpkg + stac source (standalone layer)
- **WHEN** a standalone layer uses a `type: gpkg` source with `source: stac`
- **THEN** the pipeline SHALL use `GPKGDownloader` to fetch GPKG assets, then process via the GPKG rasterization pipeline

#### Scenario: gpkg + path source (standalone layer)
- **WHEN** a standalone layer uses a `type: gpkg` source with `source: path`
- **THEN** the pipeline SHALL load the GPKG file directly from the local path, then process via the GPKG rasterization pipeline

#### Scenario: gpkg + stac source (composite sub-layer)
- **WHEN** a composite sub-layer uses a `type: gpkg` source with `source: stac`
- **THEN** the pipeline SHALL use `GPKGDownloader` to fetch GPKG assets within the composite download stage, then pre-rasterize tiles for compositing

#### Scenario: gpkg + path source (composite sub-layer)
- **WHEN** a composite sub-layer uses a `type: gpkg` source with `source: path`
- **THEN** the pipeline SHALL resolve GPKG files from local paths within the composite download stage, then pre-rasterize tiles for compositing
