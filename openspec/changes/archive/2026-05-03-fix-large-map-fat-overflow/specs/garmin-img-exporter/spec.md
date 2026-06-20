## MODIFIED Requirements

### Requirement: File size limit enforcement
The export system SHALL validate that no individual GMP subfile exceeds MAX_GMP_SIZE (~1.8 GB). If the total map data exceeds this limit, the system SHALL write multiple GMP subfiles within a single IMG file.

#### Scenario: FAT part number overflow prevention
- **WHEN** writing a GMP subfile that would need more than 256 FAT entries
- **THEN** the system raises a clear error instead of producing corrupt output with part > 255

#### Scenario: Graceful handling of oversized maps
- **WHEN** total map data is 11 GB
- **THEN** the system writes ~7 GMP subfiles within a single `.img` file, each under 1.8 GB
