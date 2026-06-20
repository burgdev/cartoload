## ADDED Requirements

### Requirement: Asset filter configuration

The system SHALL accept an optional `asset_filter` mapping in STAC source `defaults` and/or layer `source_args`. Each key-value pair specifies a STAC asset property that must match for the asset to be selected.

#### Scenario: Asset filter in source defaults

- **WHEN** a STAC source config includes `defaults.asset_filter` with `{"geoadmin:variant": "komb"}`
- **THEN** only assets whose `geoadmin:variant` property equals `"komb"` SHALL be selected for download

#### Scenario: Asset filter overridden by layer source_args

- **WHEN** a STAC source has `defaults.asset_filter: {"geoadmin:variant": "kgrs"}` and a layer has `source_args.asset_filter: {"geoadmin:variant": "komb"}`
- **THEN** the layer-level `asset_filter` SHALL take precedence and only `"komb"` assets SHALL be selected

#### Scenario: No asset filter configured

- **WHEN** no `asset_filter` is present in either `defaults` or `source_args`
- **THEN** the downloader SHALL select the first GeoTIFF asset found by media type (existing behavior preserved)

### Requirement: Multi-key AND matching

When `asset_filter` contains multiple keys, ALL specified properties SHALL match for an asset to be selected (AND logic).

#### Scenario: Multiple filter keys

- **WHEN** `asset_filter` is `{"geoadmin:variant": "komb", "proj:epsg": 2056}`
- **THEN** only assets with BOTH `geoadmin:variant` equal to `"komb"` AND `proj:epsg` equal to `2056` SHALL be selected

### Requirement: Clear warning on zero matches

When `asset_filter` is configured but no assets match, the system SHALL log a warning and skip the item rather than failing the entire download.

#### Scenario: Filter matches nothing for an item

- **WHEN** an item has assets but none match the configured `asset_filter`
- **THEN** a warning SHALL be logged with the item ID and the filter values
- **AND** the item SHALL be skipped (not downloaded)

### Requirement: Asset filter applied to GeoTIFF asset selection

The `asset_filter` SHALL be applied during GeoTIFF asset selection, filtering candidate assets after media type matching but before the final selection.

#### Scenario: Multiple GeoTIFF assets with filter

- **WHEN** a STAC item has 3 GeoTIFF assets with `geoadmin:variant` values `"kgrs"`, `"komb"`, `"krel"`
- **AND** `asset_filter` is `{"geoadmin:variant": "komb"}`
- **THEN** only the `"komb"` asset SHALL be downloaded
