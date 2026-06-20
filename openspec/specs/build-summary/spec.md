## ADDED Requirements

### Requirement: Build summary printed at start

The system SHALL print a summary table at the start of each build (before any work begins) showing the tile grid computation for all requested zoom levels and the cache status.

#### Scenario: Standard build summary

- **WHEN** the user runs `cartoload build --layer switzerland_25k`
- **THEN** before any processing begins, the system SHALL print:
  ```
  Build plan for switzerland_25k
  Source: swisstopo_wmts (EPSG:3857 → EPSG:4326, reprojection required)
  Bounds: 5.96°E – 10.49°E, 45.82°N – 47.81°N

  Zoom  Tiles       Cached   To process
  ─────────────────────────────────────
  20          4         4            0
  21         12        12            0
  22      1,200     1,200            0
  23      4,800     3,200        1,600
  24     19,200    19,200            0
  ─────────────────────────────────────
  Total  25,216    23,616        1,600

  Cache: 1,600 tiles to download, 1,600 tiles to reproject
  Estimated output: ~1.4 GB
  ```

#### Scenario: All cached — no download needed

- **WHEN** all tiles are already cached and reprojected
- **THEN** the summary SHALL show "To process: 0" for all zoom levels
- **AND** the "To download" and "To reproject" lines SHALL both show 0
- **AND** a note SHALL be printed: "All tiles cached — fast build expected"

#### Scenario: Source already in target CRS

- **WHEN** the source CRS is EPSG:4326 (matching target)
- **THEN** the summary SHALL show "EPSG:4326 → EPSG:4326, no reprojection needed"
- **AND** the "To reproject" column SHALL not appear

### Requirement: Summary reflects actual cache state

The tile counts in the summary SHALL be computed by checking the actual cache directory, not estimated. Cached tile counts SHALL distinguish between download cache (raw tiles present) and reprojection cache (reprojected tiles present).

#### Scenario: Downloaded but not reprojected

- **WHEN** 1,600 tiles are in the download cache but not in the reprojection cache
- **THEN** the summary SHALL show those tiles as "cached" (download) but still count them in "to reproject"

#### Scenario: Fully cached in both tiers

- **WHEN** tiles exist in both the download cache and the reprojection cache
- **THEN** the summary SHALL show them as fully processed with zero work remaining
