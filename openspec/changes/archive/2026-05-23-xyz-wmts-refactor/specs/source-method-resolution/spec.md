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

#### Scenario: wmts format with wmts source (template mode)
- **WHEN** a layer has `format: wmts` with a source whose type is `wmts` and URL template mode is active
- **THEN** the pipeline SHALL use `WmtsSource` in template mode to download tile grids, then use `WmtsProvider` to load tiles

#### Scenario: wmts format with wmts source (Capabilities mode)
- **WHEN** a layer has `format: wmts` with a source whose type is `wmts` and Capabilities mode is active
- **THEN** the pipeline SHALL use `WmtsSource` in Capabilities mode to resolve tile metadata, then use `WmtsProvider` to load tiles

#### Scenario: wmts format with xyz source alias
- **WHEN** a layer has `format: wmts` with a source whose type is `xyz`
- **THEN** the pipeline SHALL resolve `xyz` to `WmtsSource` and proceed identically to `type: wmts`

#### Scenario: format and source are independent
- **WHEN** a new combination is registered (e.g., `format: geojson` with `source: stac`)
- **THEN** the pipeline SHALL resolve the provider and source independently and combine them without code changes
