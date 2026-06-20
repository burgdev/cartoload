## ADDED Requirements

### Requirement: Configurable JPEG quantization tables
The system SHALL accept configurable JPEG quantization tables for tile encoding. When custom tables are provided, the system SHALL use them instead of Pillow's default quality-scaled tables.

#### Scenario: CLI preset selection
- **WHEN** the user specifies `--qtables iom-4x`
- **THEN** the system SHALL use quantization tables derived from the Garmin IOM reference, scaled 4x for higher compression
- **AND** the `quality` parameter SHALL still control the overall compression level

#### Scenario: Default behavior unchanged
- **WHEN** no `--qtables` option is specified
- **THEN** the system SHALL use Pillow's default quantization tables (current behavior)

#### Scenario: Config file override
- **WHEN** a layer config specifies `jpeg_qtables: iom-2x`
- **THEN** the system SHALL use the IOM tables scaled 2x for that layer

### Requirement: IOM-derived quantization table presets
The system SHALL provide preset quantization tables derived from the Garmin IOM reference file. Presets SHALL be named `iom-Nx` where N is the scaling factor applied to the IOM luminance table (chrominance table kept fixed as in the reference).

#### Scenario: iom-1x preset
- **WHEN** `--qtables iom-1x` is specified
- **THEN** the luminance table SHALL match the IOM reference values exactly (high quality, large files)

#### Scenario: iom-4x preset
- **WHEN** `--qtables iom-4x` is specified
- **THEN** the luminance table values SHALL be 4x the IOM reference values (moderate quality, similar compression to quality 25 with better map-optimized shape)

## MODIFIED Requirements

_None_ — the `jpeg-border-padding` requirement's behavior doesn't change; custom tables are applied at the same encoding step.
