## ADDED Requirements

### Requirement: Fast build mode flag
The system SHALL accept a `--fast` CLI flag that skips expensive optimization steps to produce faster builds at the cost of larger output files.

#### Scenario: Fast mode skips mirror-padding
- **WHEN** `--fast` is specified and tiles are re-encoded at any quality level
- **THEN** the system SHALL NOT apply mirror-padding
- **AND** the system SHALL encode tiles using Pillow directly (no cjpeg subprocess)

#### Scenario: Fast mode skips cjpeg trellis encoding
- **WHEN** `--fast` is specified
- **THEN** the system SHALL use Pillow for all JPEG encoding regardless of whether cjpeg is available

#### Scenario: Fast mode propagates through pipeline
- **WHEN** `--fast` is specified on the CLI
- **THEN** the flag SHALL be passed through all pipeline stages to the tile encoding function

#### Scenario: Default mode uses cjpeg when available
- **WHEN** `--fast` is NOT specified and cjpeg is available on PATH
- **THEN** the system SHALL use cjpeg for final JPEG encoding to activate trellis quantization
