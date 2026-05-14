## MODIFIED Requirements

### Requirement: Direct tile-to-IMG pipeline replaces GeoTIFF intermediate

The system SHALL use a direct pipeline that reads tiles from cache and writes IMG output without ever creating an intermediate GeoTIFF. The old pipeline (VRT → gdalwarp → gdaladdo → gdal_translate × N) is eliminated entirely.

When creating the downloader, the pipeline SHALL pass resolved `source_args` (merged from source defaults and layer source_args) to the downloader constructor. The downloader SHALL use these args for template variable resolution in URL templates and other source string fields.

#### Scenario: Build with cached tiles

- **WHEN** the user runs `cartoload build` and all tiles for the requested zoom levels and bounds are already in the cache directory
- **THEN** the system SHALL read tiles directly from cache, reproject per-tile if needed, and write IMG output
- **AND** no `gdalbuildvrt`, `gdalwarp`, `gdaladdo`, or `gdal_translate` SHALL be invoked

#### Scenario: Build with some tiles missing

- **WHEN** the user runs `cartoload build` and some tiles are missing from cache
- **THEN** the system SHALL download missing tiles first, then proceed with the direct pipeline
- **AND** no GeoTIFF intermediate SHALL ever be created

#### Scenario: Downloader receives source_args

- **WHEN** a layer defines `source: {ref: swisstopo_wmts, wmts_layer: ch.swisstopo.pixelkarte-farbe}`
- **THEN** `get_downloader()` SHALL receive `source_args: {wmts_layer: ch.swisstopo.pixelkarte-farbe}` and the downloader SHALL resolve these into URL templates
