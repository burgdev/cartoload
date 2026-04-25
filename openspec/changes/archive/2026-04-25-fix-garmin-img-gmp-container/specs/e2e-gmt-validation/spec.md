## ADDED Requirements

### Requirement: E2E test downloads tiles and generates valid IMG

An end-to-end test must download a small area from a WMTS source, generate an IMG file, and validate it with GMT.

#### Scenario: E2E test with 2 zoom levels

- **WHEN** the E2E test runs
- **THEN** it downloads tiles for a small area (e.g., 8.5-9.0°E, 47.0-47.5°N) at zoom levels 10 and 12
- **AND** it generates an IMG file from the downloaded tiles
- **AND** the IMG file passes GMT validation (`gmt -i -v` exits with code 0)
- **AND** the IMG file size is > 0 bytes

#### Scenario: E2E test is skipped if GMT is not installed

- **WHEN** the E2E test runs and GMT is not available on PATH
- **THEN** the test is skipped (not failed)

#### Scenario: E2E test verifies tile count

- **WHEN** the E2E test generates an IMG file
- **THEN** GMT output shows the expected number of bitmaps matching the number of tiles downloaded
