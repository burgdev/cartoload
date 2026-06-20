## MODIFIED Requirements

### Requirement: Download cache structure

The system SHALL maintain a download cache for raw source tiles, organized by source, URL-path-derived cache key, zoom level, and tile coordinates. The cache key SHALL be produced by the following algorithm:

1. Strip scheme and host from the URL
2. Remove per-tile template variables (`${x}`, `${y}`, `${z}`, `${zoom}` and `$VAR` forms)
3. Split on `/`, remove empty segments, strip leading/trailing `.` from each segment
4. Append `extra` string if provided (for STAC asset filters)
5. Join segments with `-`
6. Replace `?` with `-`, `=` and `&` with `_`
7. Apply `urllib.parse.quote(safe="-_.")` for filesystem safety

#### Scenario: WMTS download cache structure with human-readable key

- **WHEN** tiles are downloaded from a WMTS source with URL template `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg`
- **THEN** the cache key SHALL be `1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg`
- **AND** tiles SHALL be stored at `cache/{source_id}/1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg/{zoom}/{x}/{y}.{format}`
- **AND** a world file (`.jgw` or `.pgw`) SHALL accompany each tile for georeferencing

#### Scenario: STAC download cache structure with human-readable key

- **WHEN** GeoTIFF assets are downloaded from a STAC source with collection URL `https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe`
- **THEN** the cache key SHALL be `api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe`
- **AND** assets SHALL be cached at `cache/{source_id}/api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe/{item_id}.tif`
- **AND** if asset filters are provided as `extra`, the encoded filter SHALL be appended to the key

#### Scenario: Query-style URL encoding

- **WHEN** a WMTS URL uses query parameters (e.g. `.../wmts?SERVICE=WMTS&...&TILECOL=${x}`)
- **THEN** `?` SHALL be replaced with `-`
- **AND** `=` and `&` SHALL be replaced with `_`
- **AND** the resulting key SHALL be filesystem-safe

#### Scenario: Cache directory configuration

- **WHEN** the user specifies a custom cache directory via CLI or config
- **THEN** the cache SHALL be created under that directory
- **AND** the default location SHALL be `.cartoload_cache/` relative to the project root

#### Scenario: Cache key determinism

- **WHEN** the same URL template is processed multiple times
- **THEN** the system SHALL always produce the same cache key
- **AND** `https://` and `http://` prefixes SHALL be treated identically (both stripped with host)

#### Scenario: Per-tile template variables removed from key

- **WHEN** a URL template contains `${x}`, `${y}`, `${z}`, `${zoom}` (or `$x`, `$y`, `$z`, `$zoom`)
- **THEN** these variables SHALL be removed before encoding the cache key
- **AND** resulting empty path segments SHALL be removed (no empty segments between separators)
