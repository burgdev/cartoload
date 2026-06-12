## MODIFIED Requirements

### Requirement: Mirror-pad tiles before low-quality JPEG encoding
When re-encoding a tile at quality < 85, the system SHALL mirror-pad the tile edges by 16 pixels on all sides, encode the padded image at the target quality using Pillow, decode it, crop to the original dimensions, and re-encode the final output using cjpeg (mozjpeg with trellis quantization). When cjpeg is not available, the system SHALL fall back to Pillow encoding. When custom quantization tables are provided, the system SHALL pass them to cjpeg via `-qtables FILE` or fall back to Pillow if conversion fails.

#### Scenario: Low quality with cjpeg available
- **WHEN** a tile is re-encoded at quality 30 and cjpeg is on PATH
- **THEN** the system SHALL mirror-pad the tile by 16px, encode the padded image at quality 30 using Pillow, decode it, crop the center, and re-encode the cropped image using cjpeg subprocess with `-quality 30`
- **AND** the cjpeg output SHALL NOT be post-processed with mozjpeg-lossless-optimization (trellis already optimizes)

#### Scenario: Low quality with cjpeg unavailable
- **WHEN** a tile is re-encoded at quality 30 and cjpeg is NOT on PATH
- **THEN** the system SHALL fall back to Pillow encoding for both the padded and final encode
- **AND** the system SHALL apply mozjpeg lossless post-processing to the final bytes

#### Scenario: Low quality with custom qtables
- **WHEN** a tile is re-encoded at quality 30 with custom quantization tables AND cjpeg is available
- **THEN** the system SHALL convert the qtables to cjpeg format and pass them via `-qtables FILE`
- **AND** the system SHALL still use cjpeg for the final encode with trellis

#### Scenario: High quality skips padding
- **WHEN** a tile is re-encoded at quality >= 85 and cjpeg is on PATH
- **THEN** the system SHALL NOT apply mirror-padding
- **AND** the system SHALL encode the tile directly using cjpeg subprocess

#### Scenario: Passthrough mode unchanged
- **WHEN** quality is None (passthrough mode)
- **THEN** the system SHALL return raw tile bytes without any re-encoding, padding, or post-processing
