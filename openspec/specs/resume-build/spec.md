## ADDED Requirements

### Requirement: Checkpoint progress after each zoom level

The system SHALL save build progress to a checkpoint file after completing each zoom level. The checkpoint SHALL record which zoom levels have been fully processed, enabling resumption after an interrupted build.

#### Scenario: Checkpoint file created at build start

- **WHEN** a build begins processing tiles
- **THEN** a checkpoint file SHALL be created at `output/{layer_name}.checkpoint`
- **AND** the file SHALL contain: list of completed zoom levels, total tile counts per zoom, timestamp

#### Scenario: Checkpoint updated after each zoom level

- **WHEN** the system finishes processing all tiles for zoom level 22
- **THEN** the checkpoint file SHALL be updated to mark zoom 22 as complete
- **AND** the update SHALL be atomic (write to temp file, then rename) to prevent corruption

#### Scenario: Checkpoint deleted on successful completion

- **WHEN** the build completes successfully (all zoom levels processed, IMG written)
- **THEN** the checkpoint file SHALL be deleted
- **AND** the output IMG file is the signal that the build succeeded

### Requirement: Resume from checkpoint on restart

The system SHALL detect an existing checkpoint file when starting a build and offer to resume from the last completed zoom level.

#### Scenario: Resume with checkpoint present

- **WHEN** the user runs `cartoload build` and a checkpoint file exists from a previous incomplete run
- **THEN** the system SHALL print: "Incomplete build detected: zoom levels [20, 21, 22] complete. Resuming from zoom 23."
- **AND** the system SHALL skip already-completed zoom levels and continue from the next one

#### Scenario: Force restart ignoring checkpoint

- **WHEN** the user runs `cartoload build --force` and a checkpoint file exists
- **THEN** the system SHALL delete the checkpoint and start the build from scratch
- **AND** a warning SHALL be logged: "Discarding checkpoint, starting fresh build"

#### Scenario: Checkpoint corrupt or invalid

- **WHEN** the checkpoint file exists but cannot be parsed (corrupt, wrong format)
- **THEN** the system SHALL delete the checkpoint and start fresh
- **AND** a warning SHALL be logged: "Checkpoint file corrupt, starting fresh build"

### Requirement: Checkpoint survives process kill

The checkpoint file SHALL be written in a human-readable format (JSON) so it can be inspected and manually edited if needed. The file SHALL be flushed to disk after each update (not just buffered).

#### Scenario: Kill -9 during build

- **WHEN** the build process is killed (SIGKILL) during zoom level 23 processing
- **THEN** the checkpoint file SHALL still correctly reflect zoom levels 20-22 as complete
- **AND** zoom level 23 SHALL NOT be marked complete (since it was interrupted)

#### Scenario: Manual checkpoint inspection

- **WHEN** the user examines `output/switzerland_25k.checkpoint`
- **THEN** the file SHALL be readable JSON, e.g.:
  ```json
  {
    "layer": "switzerland_25k",
    "completed_zoom_levels": [20, 21, 22],
    "remaining_zoom_levels": [23, 24],
    "total_tiles": 25216,
    "processed_tiles": 1216,
    "started_at": "2026-04-26T10:00:00Z",
    "updated_at": "2026-04-26T10:12:34Z"
  }
  ```
