## ADDED Requirements

### Requirement: STAC source queries collection endpoint

The system SHALL accept `type: stac` sources that use `urls`/`url_template` with `${layer}` variable substitution to define STAC collection endpoints. The system SHALL query the STAC API, download GeoTIFF assets, and cache them locally.

#### Scenario: STAC source with layer variable

- **WHEN** a source config specifies `type: stac` with `urls: ["https://data.geo.admin.ch/api/stac/v1/collections/${layer}"]` and `defaults: {layer: my_collection}`
- **THEN** the system SHALL resolve the URL to `https://data.geo.admin.ch/api/stac/v1/collections/my_collection`
- **AND** query the STAC API for items in that collection within the layer bounds
- **AND** download GeoTIFF assets to `cache/{source_id}/{collection_id}/`

#### Scenario: STAC source with source_args override

- **WHEN** a layer specifies `source: {ref: my_stac, layer: other_collection}`
- **THEN** the `${layer}` variable SHALL resolve to `other_collection` (overriding the default)
- **AND** the STAC query SHALL use the overridden collection ID

#### Scenario: STAC items cached

- **WHEN** STAC items are downloaded
- **THEN** each item's GeoTIFF asset SHALL be cached at `cache/{source_id}/{collection_id}/{item_id}.tif`
- **AND** subsequent builds SHALL skip already-cached items

#### Scenario: Layer bounds filter STAC query

- **WHEN** a layer specifies bounds
- **THEN** the STAC query SHALL include a bbox filter matching the layer bounds
- **AND** only items intersecting the bounds SHALL be downloaded
