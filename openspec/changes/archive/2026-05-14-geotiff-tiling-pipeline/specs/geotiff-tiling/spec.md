## ADDED Requirements

### Requirement: GeoTIFF tile reader extracts pixels on-the-fly

The system SHALL read pixel data from GeoTIFF files on-demand for each (x, y, zoom) tile coordinate using rasterio windowed reads. The reader SHALL warp the pixel window from the GeoTIFF's native CRS to EPSG:4326 and return JPEG bytes compatible with the existing export pipeline.

#### Scenario: Tile covered by a single GeoTIFF

- **WHEN** the tile at (x=420, y=280, zoom=12) is needed and a GeoTIFF covers that area
- **THEN** the system SHALL compute the pixel window in the GeoTIFF that corresponds to the tile's geographic extent
- **AND** read only that window via rasterio
- **AND** warp to EPSG:4326 and return JPEG bytes

#### Scenario: Tile not covered by any GeoTIFF

- **WHEN** the tile at (x, y, zoom) falls outside all GeoTIFF extents
- **THEN** the reader SHALL return None
- **AND** the export pipeline SHALL skip that tile

#### Scenario: GeoTIFF in non-Mercator CRS

- **WHEN** a GeoTIFF uses EPSG:2056 (Swiss CH1903+/LV95)
- **THEN** the reader SHALL reproject the pixel window from EPSG:2056 to EPSG:4326
- **AND** the reprojection SHALL use bilinear resampling
- **AND** the output SHALL be geometrically correct in WGS84

### Requirement: Spatial index for GeoTIFF lookup

After downloading GeoTIFFs, the system SHALL read each file's CRS and bounds from rasterio metadata and build an in-memory spatial index for fast lookup.

#### Scenario: Building the spatial index

- **WHEN** GeoTIFF files are downloaded or loaded from a folder
- **THEN** the system SHALL open each file with rasterio, read its CRS and bounding box
- **AND** store a mapping of (bounds, filepath) for lookup

#### Scenario: Finding GeoTIFF for a tile coordinate

- **WHEN** the pipeline needs data for tile (x, y, zoom)
- **THEN** the system SHALL compute the geographic extent of that tile in the GeoTIFF's native CRS
- **AND** check the spatial index for intersecting GeoTIFFs
- **AND** return the first match (inputs are assumed non-overlapping)

### Requirement: Pipeline uses GeoTIFF reader identically to WMTS tiles

The GeoTIFF tile reader SHALL integrate into the existing pipeline by providing the same per-tile JPEG bytes interface. The export pipeline (metadata computation, streaming write, Garmin IMG) SHALL work unchanged.

#### Scenario: GeoTIFF layer uses same export path as WMTS

- **WHEN** a layer uses a `type: geotiff` source and tiles are read from GeoTIFFs
- **THEN** the system SHALL stream JPEG bytes to the Garmin IMG writer using the same code path as WMTS layers
- **AND** the output IMG file SHALL be structurally identical to one produced from WMTS tiles
