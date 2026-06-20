## ADDED Requirements

### Requirement: Auto-migration of hash-based cache directories

The system SHALL automatically migrate old hash-based cache directories (12-char lowercase hex) to the new human-readable format when a build encounters them.

#### Scenario: Hash directory found during build

- **GIVEN** a cache directory `cache/{source_id}/a1b2c3d4e5f6/` exists from a previous version
- **WHEN** the build computes the new cache key for the same URL
- **THEN** the system SHALL rename `a1b2c3d4e5f6` to the new human-readable key
- **AND** log a message indicating the migration
- **AND** proceed with the build using the new path

#### Scenario: New-style directory already exists alongside hash

- **GIVEN** both `cache/{source_id}/a1b2c3d4e5f6/` and `cache/{source_id}/1.0.0-ch.swisstopo-...-jpeg/` exist
- **WHEN** the build runs
- **THEN** the system SHALL use the new-style directory
- **AND** SHALL NOT attempt migration
- **AND** the old hash directory SHALL be left in place

#### Scenario: No hash directories exist

- **GIVEN** a cache directory with no 12-char hex subdirectories
- **WHEN** the build runs
- **THEN** no migration SHALL occur
- **AND** the build SHALL proceed normally
