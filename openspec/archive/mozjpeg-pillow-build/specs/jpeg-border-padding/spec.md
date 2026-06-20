## MODIFIED Requirements

### Requirement: Mirror-pad tiles before low-quality JPEG encoding
When re-encoding a tile at quality < 85, the system SHALL mirror-pad the tile edges by 16 pixels on all sides, encode the padded image at the target quality, decode it, crop to the original dimensions, and re-encode at the target quality. When built with mozjpeg as the JPEG backend, the encoding SHALL use trellis quantization automatically via Pillow.

#### Scenario: mozjpeg build produces smaller tiles
- **WHEN** Pillow is compiled against mozjpeg (Docker build)
- **THEN** JPEG tiles SHALL be encoded using trellis quantization
- **AND** tiles SHALL be 3-8% smaller than the same quality encoded with libjpeg-turbo
- **AND** visual quality SHALL be the same or better

#### Scenario: Standard Pillow build works as before
- **WHEN** Pillow uses the standard libjpeg-turbo backend (local development)
- **THEN** JPEG tiles SHALL be encoded using standard libjpeg-turbo
- **AND** output SHALL be functionally identical to current behavior
