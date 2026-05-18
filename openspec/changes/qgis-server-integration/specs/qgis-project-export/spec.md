## ADDED Requirements

### Requirement: CLI command to export QGIS project files
The system SHALL provide a `cartoload export-qgis-project` CLI command that generates a QGIS `.qgs` project file from cartoload layer configs.

#### Scenario: Export a single layer with GPKG source
- **WHEN** the user runs `cartoload export-qgis-project -c config.yaml -l my_layer -o project.qgs`
- **THEN** the command generates a `.qgs` file containing a vector layer referencing the GPKG data source with its QML style applied

#### Scenario: Export a composite layer with multiple sub-layers
- **WHEN** the user runs the command with a layer that has a `layers` field containing multiple sub-layers
- **THEN** the generated `.qgs` file contains multiple map layers, ordered bottom-to-top, each with its data source and style

#### Scenario: Export with --no-download flag
- **WHEN** the user runs the command with `--no-download`
- **THEN** the command generates the project file using existing cached data without downloading

#### Scenario: Missing local data without --no-download
- **WHEN** the user runs the command and a GPKG or GeoTIFF source has no cached data
- **THEN** the command downloads the data before generating the project file

### Requirement: GPKG and GeoTIFF data sources in exported projects
The generated `.qgs` file SHALL reference local GPKG and GeoTIFF data sources with correct provider, CRS, and style configuration.

#### Scenario: GPKG layer with QML style
- **WHEN** a layer has format `gpkg` and a `style` path pointing to a QML file
- **THEN** the `.qgs` file contains a vector layer with `ogr` provider, the GPKG file path as datasource, and the QML style embedded or referenced

#### Scenario: GeoTIFF layer
- **WHEN** a layer has format `geotiff` and a local path source
- **THEN** the `.qgs` file contains a raster layer with `gdal` provider and the GeoTIFF path as datasource

### Requirement: WMTS sources are skipped during export
The command SHALL skip WMTS source layers during project generation, since WMTS layers are remote tile services not suitable for QGIS Server rendering.

#### Scenario: Layer with WMTS source
- **WHEN** a layer's source is of type `wmts`
- **THEN** the command logs a warning and excludes that layer from the generated project

### Requirement: Output project uses EPSG:3857 CRS
The generated `.qgs` project file SHALL use EPSG:3857 (Web Mercator) as the project CRS to match the tile rendering coordinate system.

#### Scenario: Project CRS in generated file
- **WHEN** a project file is generated
- **THEN** the project CRS is set to EPSG:3857 in the `.qgs` XML

### Requirement: Relative data paths in project file
The `.qgs` file SHALL use relative paths for data source references, relative to the project file location.

#### Scenario: GPKG path is relative
- **WHEN** the project is generated at `/cache/project.qgs` and the GPKG is at `/cache/data.gpkg`
- **THEN** the datasource in the `.qgs` file references `data.gpkg` (relative path)
