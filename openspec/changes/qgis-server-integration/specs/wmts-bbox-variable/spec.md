## ADDED Requirements

### Requirement: BBOX template variable in WMTS URLs
The WMTS URL builder SHALL support `${bbox}` as a template variable that expands to a comma-separated `west,south,east,north` string in WMS 1.3.0 axis order (depending on CRS).

#### Scenario: QGIS WMS GetMap URL with ${bbox}
- **WHEN** a `wmts` source URL template contains `${bbox}` and a tile at zoom 12, x=2145, y=1432 is being fetched
- **THEN** `${bbox}` is replaced with the computed bounding box as `west,south,east,north` in the CRS specified by the source configuration

### Requirement: Individual coordinate template variables
The WMTS URL builder SHALL support `${west}`, `${south}`, `${east}`, `${north}` as individual template variables for finer control over URL construction.

#### Scenario: URL with individual coordinate variables
- **WHEN** a `wmts` source URL template contains `${west},${south},${east},${north}`
- **THEN** each variable is replaced with the corresponding coordinate value as a decimal string

### Requirement: Backward compatibility with existing WMTS URLs
The addition of bbox variables SHALL NOT change the behavior of existing WMTS URL templates that only use `${x}`, `${y}`, `${z}`, `${zoom}`.

#### Scenario: Existing XYZ tile URL unchanged
- **WHEN** a `wmts` source URL template is `https://tiles.example.com/${z}/${x}/${y}.jpeg`
- **THEN** the tile URL is built exactly as before with no changes to the output
