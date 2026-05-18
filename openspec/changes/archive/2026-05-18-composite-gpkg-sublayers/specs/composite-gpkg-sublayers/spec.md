## ADDED Requirements

### Requirement: Download GPKG files for composite sub-layers
The pipeline SHALL download GPKG files for gpkg-type sub-layers within composite layers, using the same download logic as standalone gpkg layers (STAC or local path).

#### Scenario: STAC gpkg sub-layer download
- **WHEN** a composite layer contains a sub-layer with `type: gpkg` and `source_method: stac`
- **THEN** the pipeline SHALL use `GPKGDownloader` to download GPKG assets from the STAC collection

#### Scenario: Local path gpkg sub-layer
- **WHEN** a composite layer contains a sub-layer with `type: gpkg` and `source_method: path`
- **THEN** the pipeline SHALL resolve GPKG files from the configured local paths

#### Scenario: GPKG download failure
- **WHEN** a gpkg sub-layer download fails
- **THEN** the pipeline SHALL raise a `DownloadError` with the source ID and error details

### Requirement: Rasterize gpkg sub-layers for compositing
The pipeline SHALL pre-rasterize vector features from GPKG files onto transparent tiles for each gpkg sub-layer, using `VectorRasterizer` and `StyleEngine`.

#### Scenario: Rasterization with style rules from referenced layer
- **WHEN** a gpkg sub-layer references a layer via `ref:` that has style rules defined
- **THEN** the pipeline SHALL create a `StyleEngine` from the referenced layer's style config and use it to rasterize features

#### Scenario: Rasterization with inline style rules
- **WHEN** a gpkg sub-layer has inline style rules defined directly
- **THEN** the pipeline SHALL use those rules for rasterization

#### Scenario: No style rules on gpkg sub-layer
- **WHEN** a gpkg sub-layer has no style rules (no `rules` or `style` field from ref or inline)
- **THEN** the pipeline SHALL log a warning and skip rasterization for that sub-layer

### Requirement: Composite gpkg tiles with other sub-layers
The composite tile processor SHALL load pre-rasterized gpkg tiles and composite them with other sub-layer tiles using the existing alpha compositing pipeline.

#### Scenario: Loading a pre-rasterized gpkg tile
- **WHEN** the composite processor encounters a gpkg sub-layer for a given (x, y, zoom) tile
- **THEN** it SHALL load the pre-rasterized PNG from the cache directory and treat it as an RGBA image for compositing

#### Scenario: Missing gpkg tile for a coordinate
- **WHEN** a pre-rasterized gpkg tile does not exist for a given (x, y, zoom)
- **THEN** the composite processor SHALL skip that sub-layer for that tile (treat as transparent)

#### Scenario: GPKG tile with opacity
- **WHEN** a gpkg sub-layer has an opacity setting
- **THEN** the composite processor SHALL apply the opacity before compositing with other sub-layers

### Requirement: GPKG sub-layers respect zoom level filtering
GPKG sub-layers SHALL only be rasterized and composited for their configured zoom levels.

#### Scenario: Zoom level outside configured range
- **WHEN** the composite processor processes a tile at a zoom level not in the gpkg sub-layer's `zoom_levels`
- **THEN** the gpkg sub-layer SHALL be skipped for that tile
