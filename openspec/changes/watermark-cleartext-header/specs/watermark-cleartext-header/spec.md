## ADDED Requirements

### Requirement: Cleartext header write API
The system SHALL provide a cleartext header that is written at a fixed offset (0x0400) within the watermark region, independent of the encrypted watermark blob. The header SHALL use magic bytes "CH" (0x43, 0x48) and contain UTF-8 key-value metadata readable without a key.

#### Scenario: Write cleartext header alongside encrypted watermark
- **WHEN** `write_watermark("map.img", "user=abc:t=123", key, header="order=gGeN33kt")` is called
- **THEN** a cleartext header blob with magic "CH" SHALL be written at offset 0x0400
- **AND** the encrypted watermark blob with magic "CW" SHALL be written at the HMAC-derived offset
- **AND** both blobs SHALL fit within the watermark region (0x0400–0x0FFF)

#### Scenario: Write fails if header exceeds maximum size
- **WHEN** `write_watermark` is called with a header string longer than 120 bytes UTF-8
- **THEN** the function SHALL raise a `ValueError`

#### Scenario: Write without header is backward compatible
- **WHEN** `write_watermark("map.img", "payload", key)` is called without a header parameter
- **THEN** no cleartext header SHALL be written
- **AND** the encrypted watermark SHALL be written as before

### Requirement: Cleartext header binary format
The cleartext header blob SHALL use the format: magic "CH" (2 bytes), header_length as uint16 LE (2 bytes), flags as uint16 LE (2 bytes, value 0x0001 for version 1), followed by the UTF-8 header string.

#### Scenario: Header binary layout
- **WHEN** a header "order=abc123" (11 bytes) is written
- **THEN** the total blob SHALL be 6 (header) + 11 (data) = 17 bytes
- **AND** the magic SHALL be "CH"
- **AND** the header_length field SHALL be 17 (total blob size)

### Requirement: Cleartext header read API
The system SHALL provide a `read_watermark_header(img_path)` function that reads the cleartext header without requiring a key.

#### Scenario: Read header from file with cleartext header
- **WHEN** `read_watermark_header("map.img")` is called on a file with a cleartext header
- **THEN** the function SHALL return the header string (e.g. "order=gGeN33kt")

#### Scenario: Read header returns None when no header present
- **WHEN** `read_watermark_header("map.img")` is called on a file without a cleartext header
- **THEN** the function SHALL return `None`

#### Scenario: Read header returns None for legacy watermarked files
- **WHEN** `read_watermark_header("map.img")` is called on a file watermarked with the old format (no header)
- **THEN** the function SHALL return `None`

### Requirement: Streaming cleartext header API
The system SHALL provide a `read_watermark_header_bytes(first_chunk: bytes) -> str | None` function that reads the cleartext header from the first 4KB of an IMG file without requiring a key or file path.

#### Scenario: Read header from streaming chunk
- **WHEN** `read_watermark_header_bytes(first_4kb)` is called on data containing a cleartext header
- **THEN** the function SHALL return the header string

### Requirement: CLI read-header command
The system SHALL provide a `cartoload watermark read-header <img-file>` command that reads and prints the cleartext header. No key is required.

#### Scenario: Read header via CLI
- **WHEN** `cartoload watermark read-header map.img` is executed on a file with a cleartext header
- **THEN** the command SHALL print the header string to stdout

#### Scenario: Read header on file without header
- **WHEN** `cartoload watermark read-header map.img` is executed on a file without a cleartext header
- **THEN** the command SHALL print "No cleartext header found" and exit with status 0
