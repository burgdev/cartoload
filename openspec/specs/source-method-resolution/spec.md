## MODIFIED Requirements

### Requirement: Pipeline dispatch by type, download by source method
The pipeline SHALL dispatch processing based on data format (`geotiff`, `gpkg`, `wmts`) specified in the layer's `format` field. Source method (how to fetch) is determined by the source's `type` field or auto-detected from URLs. A single unified pipeline handles all format+source combinations — there SHALL NOT be separate dispatch paths for different formats.

#### Scenario: geotiff format with stac source
- **WHEN** a layer has `format: geotiff` with a source whose type is `stac`
- **THEN** the pipeline SHALL use `StacSource` to fetch GeoTIFF assets, then use `GeotiffProvider` to pre-warp and render tiles

#### Scenario: geotiff format with path source
- **WHEN** a layer has `format: geotiff` with a source whose type is `path`
- **THEN** the pipeline SHALL use `PathSource` to resolve local files, then use `GeotiffProvider` to process them

#### Scenario: gpkg format with stac source
- **WHEN** a layer has `format: gpkg` with a source whose type is `stac`
- **THEN** the pipeline SHALL use `StacSource` to fetch GPKG assets, then use `GpkgProvider` to rasterize and render tiles

#### Scenario: gpkg format with path source
- **WHEN** a layer has `format: gpkg` with a source whose type is `path`
- **THEN** the pipeline SHALL use `PathSource` to resolve local files, then use `GpkgProvider` to process them

#### Scenario: wmts format with wmts source
- **WHEN** a layer has `format: wmts` with a source whose type is `wmts`
- **THEN** the pipeline SHALL use `WmtsSource` to download tile grids, then use `WmtsProvider` to load tiles

#### Scenario: format and source are independent
- **WHEN** a new combination is registered (e.g., `format: geojson` with `source: stac`)
- **THEN** the pipeline SHALL resolve the provider and source independently and combine them without code changes
