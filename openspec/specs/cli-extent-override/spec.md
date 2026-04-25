## ADDED Requirements

### Requirement: Bbox option accepts 4 separate coordinate arguments

The CLI SHALL accept `--bbox W S E N` as four separate float arguments specifying west, south, east, north in WGS84 degrees. The old `--bounds` option SHALL be removed.

#### Scenario: Bbox with valid coordinates

- **WHEN** the user runs `cartoload build --bbox 7.0 46.5 8.0 47.0 --layer ...`
- **THEN** the effective bounds SHALL be `{"west": 7.0, "south": 46.5, "east": 8.0, "north": 47.0}`

#### Scenario: Bbox with wrong number of arguments

- **WHEN** the user runs `cartoload build --bbox 7.0 46.5`
- **THEN** the CLI SHALL exit with an error indicating exactly 4 values are required

### Requirement: Center and dimensions compute bbox from km values

The CLI SHALL accept `--lng`, `--lat`, `--width`, and `--height` options where width/height are in kilometers. The system SHALL compute the bounding box using:

- latitude delta = height_km / 111.32
- longitude delta = width_km / (111.32 × cos(latitude_rad))

#### Scenario: Center with width and height

- **WHEN** the user runs `cartoload build --lng 7.45 --lat 46.9 --width 20 --height 10 --layer ...`
- **THEN** the system SHALL compute a bounding box centered on (7.45, 46.9) with approximately ±10 km east-west and ±5 km north-south

#### Scenario: Center without width or height

- **WHEN** the user runs `cartoload build --lng 7.45 --lat 46.9 --layer ...`
- **THEN** the CLI SHALL exit with an error indicating both `--width` and `--height` are required when using center mode

#### Scenario: Width or height without center

- **WHEN** the user runs `cartoload build --width 20 --height 10 --layer ...`
- **THEN** the CLI SHALL exit with an error indicating `--lng` and `--lat` are required when using dimension mode

### Requirement: Extent options are mutually exclusive

The CLI SHALL reject commands that specify both `--bbox` and center+dimensions simultaneously.

#### Scenario: Both bbox and center specified

- **WHEN** the user runs `cartoload build --bbox 7.0 46.5 8.0 47.0 --lng 7.45 --lat 46.9 --layer ...`
- **THEN** the CLI SHALL exit with an error indicating only one extent mode can be used

### Requirement: Custom extent validated against layer bounds

The system SHALL validate that the requested extent (from any mode) is fully contained within the layer's configured bounds. If the requested extent exceeds the layer bounds, the CLI SHALL exit with an error showing both extents.

#### Scenario: Requested bbox within layer bounds

- **WHEN** the layer bounds are `{"west": 5.96, "east": 10.49, "south": 45.82, "north": 47.81}` and the user requests `--bbox 7.0 46.5 8.0 47.0`
- **THEN** the request SHALL be accepted and used as the effective bounds

#### Scenario: Requested bbox exceeds layer bounds

- **WHEN** the layer bounds are `{"west": 5.96, "east": 10.49, "south": 45.82, "north": 47.81}` and the user requests `--bbox 4.0 45.0 11.0 48.0`
- **THEN** the CLI SHALL exit with an error showing the requested extent and the allowed layer bounds

#### Scenario: No custom extent specified

- **WHEN** the user does not specify any extent override
- **THEN** the layer config bounds SHALL be used as-is (no validation needed)

### Requirement: Extent override works in both build and download commands

The `--bbox`, `--lng`, `--lat`, `--width`, and `--height` options SHALL be available on both the `build` and `download` CLI commands with identical behavior.

#### Scenario: Download with bbox override

- **WHEN** the user runs `cartoload download --bbox 7.0 46.5 8.0 47.0 --layer ...`
- **THEN** only tiles within the requested bbox SHALL be downloaded

#### Scenario: Build with center+dimensions

- **WHEN** the user runs `cartoload build --lng 7.45 --lat 46.9 --width 20 --height 10 --layer ...`
- **THEN** the build SHALL process only the area within the computed bbox
