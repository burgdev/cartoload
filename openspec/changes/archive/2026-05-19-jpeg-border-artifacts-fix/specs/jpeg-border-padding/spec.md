## ADDED Requirements

### Requirement: Mirror-pad tiles before low-quality JPEG encoding
When re-encoding a tile at quality < 85, the system SHALL mirror-pad the tile edges by 16 pixels on all sides, encode the padded image at the target quality, decode it, crop to the original dimensions, and re-encode at the target quality.

#### Scenario: Low quality eliminates border artifacts
- **WHEN** a tile is re-encoded at quality 30
- **THEN** the system SHALL mirror-pad the tile by 16px, encode the 288×288 padded image at quality 30, decode it, crop the center 256×256, and re-encode at quality 30

#### Scenario: High quality skips padding
- **WHEN** a tile is re-encoded at quality >= 85
- **THEN** the system SHALL NOT apply mirror-padding (direct encode, no overhead)

#### Scenario: Passthrough mode unchanged
- **WHEN** quality is None (passthrough mode)
- **THEN** the system SHALL return raw tile bytes without any re-encoding or padding

#### Scenario: Padding uses mirror reflection
- **WHEN** mirror-padding is applied
- **THEN** the 16px border on each side SHALL be a mirror reflection of the adjacent edge pixels, not zero-padding
