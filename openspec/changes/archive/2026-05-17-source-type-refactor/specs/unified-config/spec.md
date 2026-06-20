## MODIFIED Requirements

### Requirement: Unified config file format
A config file SHALL be a YAML document that may contain any combination of the following top-level keys: `includes`, `sources`, `layers`, `bounds`, `settings`. All sections are optional.

Source `type` represents the data format: `geotiff`, `gpkg`, or `wmts`. The `stac` type is removed — it was a GeoTIFF fetched via STAC; use `type: geotiff` with the STAC source method instead.

Source `source` is an optional field representing the download method: `stac` or `path`. If omitted, it is auto-detected from the URL.

The `url_template` field is removed. Source locations (URLs, STAC endpoints, local paths) are specified exclusively via `urls`, which accepts a list or a single string (auto-wrapped).

#### Scenario: Config file with all sections
- **WHEN** a config file contains `includes`, `sources`, `layers`, and `bounds` keys
- **THEN** the loader SHALL parse all sections and return them as a unified result

#### Scenario: Source type geotiff with STAC URL (auto-detected)
- **WHEN** a source config defines `type: geotiff` with a `urls` entry containing `/collections/` or `/stac/`
- **THEN** the loader SHALL accept it and set the source method to `stac`

#### Scenario: Source type geotiff with local path (auto-detected)
- **WHEN** a source config defines `type: geotiff` with a `urls` entry that is a local path
- **THEN** the loader SHALL accept it and set the source method to `path`

#### Scenario: Source type gpkg with STAC URL (auto-detected)
- **WHEN** a source config defines `type: gpkg` with a `urls` entry containing `/collections/` or `/stac/`
- **THEN** the loader SHALL accept it and set the source method to `stac`

#### Scenario: Source type with explicit source method
- **WHEN** a source config defines `type: geotiff` and `source: stac`
- **THEN** the loader SHALL use the explicit source method regardless of URL pattern

#### Scenario: Source type stac rejected
- **WHEN** a source config defines `type: stac`
- **THEN** the loader SHALL raise a validation error suggesting `type: geotiff` with STAC source method

#### Scenario: url_template rejected
- **WHEN** a source config uses `url_template` instead of `urls`
- **THEN** the loader SHALL raise a validation error suggesting `urls` as the replacement field

#### Scenario: Source type wmts unchanged
- **WHEN** a source config defines `type: wmts` with `urls`
- **THEN** the loader SHALL accept it as before (wmts has its own tile-based pipeline)

#### Scenario: urls accepts string or list
- **WHEN** a source config provides `urls` as a single string
- **THEN** the loader SHALL auto-wrap it into a list of one entry

#### Scenario: Empty config file
- **WHEN** a config file contains no recognized top-level keys
- **THEN** the loader SHALL return empty sources, empty layers, and no bounds
