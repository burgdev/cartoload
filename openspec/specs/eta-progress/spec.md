## ADDED Requirements

### Requirement: Progress bars show ETA and time remaining

All progress bars SHALL display estimated time remaining (ETA) in addition to elapsed time. The Rich `TimeRemainingColumn` SHALL be used for this purpose.

#### Scenario: Build progress with ETA

- **WHEN** a build is processing 30,000 tiles
- **THEN** the progress bar SHALL show: elapsed time, estimated remaining time, and current speed (tiles/sec)
- **AND** the ETA SHALL update dynamically based on actual processing speed

#### Scenario: Very fast operations

- **WHEN** a build completes in under 5 seconds (e.g., small area, all cached)
- **THEN** the ETA MAY show "< 1s" or simply not display if insufficient data points exist

### Requirement: Overall build progress across all stages

The system SHALL display a top-level progress indicator covering all build stages: download, reprojection, encoding, and IMG writing. Each stage SHALL also have its own sub-progress.

#### Scenario: Multi-stage progress display

- **WHEN** a build is running with downloads and processing
- **THEN** the display SHALL show:
  ```
  Downloading  ████████░░░░░░░░  12,000/30,000  40%  ETA 2m30s
  ```
- **AND** after downloads complete:
  ```
  Processing   ████████████░░░░  20,000/30,000  67%  ETA 45s
  ```
- **AND** during IMG writing:
  ```
  Writing IMG  ████████████████  25,216 tiles   100%
  ```

#### Scenario: All cached — skip download stage

- **WHEN** all tiles are already cached and no downloads are needed
- **THEN** the download stage SHALL show "All 25,216 tiles cached" and skip immediately to processing

### Requirement: Per-zoom progress breakdown

The system SHALL show which zoom level is currently being processed, with tile counts and progress for that level.

#### Scenario: Processing zoom levels sequentially

- **WHEN** the system processes zoom level 23 (out of [20, 21, 22, 23, 24])
- **THEN** the display SHALL indicate: "Zoom 23: 1,200/4,800 tiles"
- **AND** the overall progress SHALL account for tiles across all zoom levels
