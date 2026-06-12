## MODIFIED Requirements

### Requirement: Watermark write API
The system SHALL provide a `write_watermark(img_path, payload, key, header=None)` function that encrypts a UTF-8 string and writes it into the header gap region (0x0400–0x0FFF) of a Garmin IMG file. When `header` is provided, a cleartext header blob SHALL also be written at offset 0x0400. The encrypted watermark offset SHALL be derived from `HMAC-SHA256(key, map_id)` where map_id is read from the file's MPS subfile.

#### Scenario: Write a watermark string to an IMG file
- **WHEN** `write_watermark("map.img", "user=abc:t=123", key_bytes)` is called
- **THEN** the encrypted payload SHALL be written at the derived offset within 0x0400–0x0FFF
- **AND** the magic bytes "CW" SHALL precede the encrypted payload
- **AND** the original file content outside the watermark region SHALL remain unchanged

#### Scenario: Write a watermark with cleartext header
- **WHEN** `write_watermark("map.img", "user=abc:t=123", key_bytes, header="order=abc123")` is called
- **THEN** the cleartext header blob SHALL be written at offset 0x0400 with magic "CH"
- **AND** the encrypted payload SHALL be written at the HMAC-derived offset with magic "CW"
- **AND** the two blobs SHALL not overlap

#### Scenario: Write fails if payload is too large
- **WHEN** `write_watermark` is called with a string longer than 252 bytes
- **THEN** the function SHALL raise a `ValueError`

#### Scenario: Write overwrites existing watermark
- **WHEN** `write_watermark` is called on a file that already contains a watermark
- **THEN** the old watermark SHALL be replaced with the new one
- **AND** the offset MAY be different (if the payload length changed)

### Requirement: Watermark read API
The system SHALL provide a `read_watermark(img_path, key)` function that reads and decrypts a watermark from a Garmin IMG file. The function SHALL return a `WatermarkResult` with `header: str | None` and `payload: str | None` fields.

#### Scenario: Read a watermark from a watermarked file with header
- **WHEN** `read_watermark("map.img", key_bytes)` is called on a file with both a cleartext header and encrypted watermark
- **THEN** the function SHALL return a `WatermarkResult` with the decrypted payload string and the cleartext header string

#### Scenario: Read a watermark from a legacy watermarked file
- **WHEN** `read_watermark("map.img", key_bytes)` is called on a file with only an encrypted watermark (no header)
- **THEN** the function SHALL return a `WatermarkResult` with the decrypted payload string and `header=None`

#### Scenario: Read returns None payload when no watermark present
- **WHEN** `read_watermark` is called on a file without an encrypted watermark
- **THEN** the function SHALL return a `WatermarkResult` with `payload=None`

#### Scenario: Read raises on tampered watermark
- **WHEN** `read_watermark` is called on a file where the watermark bytes have been corrupted
- **THEN** the function SHALL raise an exception indicating authentication failure

### Requirement: Streaming watermark API
The system SHALL provide a `watermark_bytes(first_chunk: bytes, map_id: int, payload: str, key: bytes, header: str | None = None) -> bytes` function that injects a watermark into the first 4KB of an IMG file without requiring a file path. When `header` is provided, the cleartext header blob SHALL also be embedded at offset 0x0400. The function SHALL return a modified copy of the input bytes with the watermark (and optional header) embedded.

#### Scenario: Inject watermark with header into first chunk for streaming
- **WHEN** `watermark_bytes(first_4kb, map_id, "user=abc:t=123", key, header="order=xyz")` is called
- **THEN** the returned bytes SHALL contain the cleartext header at offset 0x0400 with magic "CH"
- **AND** the returned bytes SHALL contain the encrypted watermark at the HMAC-derived offset with magic "CW"
- **AND** the returned bytes SHALL be exactly 4096 bytes long

#### Scenario: Inject watermark without header (backward compatible)
- **WHEN** `watermark_bytes(first_4kb, map_id, "payload", key)` is called without header
- **THEN** the returned bytes SHALL contain only the encrypted watermark at the HMAC-derived offset
- **AND** the returned bytes SHALL be exactly 4096 bytes long

#### Scenario: Streamed watermark with header can be read back
- **WHEN** a file is created by concatenating the output of `watermark_bytes` with header and the rest of the IMG data
- **THEN** `read_watermark_header` on the resulting file SHALL return the header string
- **AND** `read_watermark` SHALL return both header and decrypted payload

### Requirement: CLI watermark read command
The system SHALL provide a `cartoload watermark read <img-file>` command that reads and prints the watermark. The key SHALL be read from (in priority order): `--key` parameter, `--key-file` parameter, or `CARTOLOAD_WATERMARK_KEY` environment variable. When both a cleartext header and encrypted payload are present, both SHALL be displayed.

#### Scenario: Read via CLI prints header and payload
- **WHEN** `cartoload watermark read map.img --key abc123` is executed on a file with both header and encrypted watermark
- **THEN** the command SHALL print the cleartext header (labeled "Header") and the decrypted payload (labeled "Payload")

#### Scenario: Read via CLI on file without key but with header
- **WHEN** `cartoload watermark read map.img` is executed without a key on a file with a cleartext header
- **THEN** the command SHALL print the cleartext header
- **AND** the command SHALL print a message indicating the encrypted payload could not be decrypted (no key)

#### Scenario: Read via CLI prints only payload for legacy files
- **WHEN** `cartoload watermark read map.img --key abc123` is executed on a legacy file (no header)
- **THEN** the command SHALL print the decrypted payload
- **AND** no header section SHALL be shown

#### Scenario: Read on unwatermarked file
- **WHEN** `cartoload watermark read map.img --key abc123` is executed on a file without a watermark
- **THEN** the command SHALL print "No watermark found" and exit with status 0
