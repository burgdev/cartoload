## ADDED Requirements

### Requirement: Watermark write API
The system SHALL provide a `write_watermark(img_path, payload, key)` function that encrypts a UTF-8 string and writes it into the header gap region (0x0400–0x0FFF) of a Garmin IMG file. The watermark offset SHALL be derived from `HMAC-SHA256(key, map_id)` where map_id is read from the file's MPS subfile.

#### Scenario: Write a watermark string to an IMG file
- **WHEN** `write_watermark("map.img", "2026-05-21|order-abc123", key_bytes)` is called
- **THEN** the encrypted payload SHALL be written at the derived offset within 0x0400–0x0FFF
- **AND** the magic bytes "CW" SHALL precede the encrypted payload
- **AND** the original file content outside the watermark region SHALL remain unchanged

#### Scenario: Write fails if payload is too large
- **WHEN** `write_watermark` is called with a string longer than 252 bytes
- **THEN** the function SHALL raise a `ValueError`

#### Scenario: Write overwrites existing watermark
- **WHEN** `write_watermark` is called on a file that already contains a watermark
- **THEN** the old watermark SHALL be replaced with the new one
- **AND** the offset MAY be different (if the payload length changed)

### Requirement: Watermark read API
The system SHALL provide a `read_watermark(img_path, key)` function that reads and decrypts a watermark from a Garmin IMG file.

#### Scenario: Read a watermark from a watermarked file
- **WHEN** `read_watermark("map.img", key_bytes)` is called on a file with a valid watermark
- **THEN** the function SHALL return the original UTF-8 string

#### Scenario: Read returns None when no watermark present
- **WHEN** `read_watermark` is called on a file without a watermark
- **THEN** the function SHALL return `None`

#### Scenario: Read raises on tampered watermark
- **WHEN** `read_watermark` is called on a file where the watermark bytes have been corrupted
- **THEN** the function SHALL raise an exception indicating authentication failure

### Requirement: Watermark binary format
The watermark SHALL use a fixed header: magic bytes "CW" (0x43, 0x57), followed by payload_length (uint16 LE), flags (uint16 LE, zero), then the encrypted blob. The encrypted blob SHALL use AES-256-GCM with a 12-byte random nonce prepended to the ciphertext and 16-byte authentication tag appended.

#### Scenario: Watermark fits in available gap
- **WHEN** a watermark is written with a 24-byte plaintext payload
- **THEN** the total written bytes SHALL be 6 (header) + 12 (nonce) + 24 (ciphertext) + 16 (tag) = 58 bytes
- **AND** the total SHALL not exceed 3,072 bytes (the gap size)

### Requirement: Offset derivation from key and map_id
The watermark offset within the gap SHALL be computed as `0x0400 + (HMAC-SHA256(key, f"{map_id:08X}")[:4] % (3072 - watermark_total_size))`. The map_id SHALL be read from the MPS subfile at offset MPS+0x07 (uint32 LE), located by scanning FAT entries for subfile type "MPS".

#### Scenario: Same key and map_id produce same offset
- **WHEN** `write_watermark` and `read_watermark` are called with the same key on the same file
- **THEN** both SHALL derive the same offset and the watermark SHALL be correctly read back

#### Scenario: Different map_ids produce different offsets
- **WHEN** two IMG files have different map_ids
- **THEN** the watermark offsets SHALL be different (with high probability)

### Requirement: Streaming watermark API
The system SHALL provide a `watermark_bytes(first_chunk: bytes, map_id: int, payload: str, key: bytes) -> bytes` function that injects a watermark into the first 4KB of an IMG file without requiring a file path. The function SHALL return a modified copy of the input bytes with the watermark embedded at the derived offset.

#### Scenario: Inject watermark into first chunk for streaming
- **WHEN** `watermark_bytes(first_4kb, map_id, "order-uuid", key)` is called
- **THEN** the returned bytes SHALL be identical to the input except at the watermark location
- **AND** the returned bytes SHALL be exactly 4096 bytes long

#### Scenario: Streamed watermark can be read back from file
- **WHEN** a file is created by concatenating the output of `watermark_bytes` with the rest of the IMG data
- **THEN** `read_watermark` on the resulting file SHALL return the original payload string

### Requirement: CLI watermark write command
The system SHALL provide a `cartoload watermark write <img-file> <string>` command that writes a watermark. The key SHALL be read from (in priority order): `--key` parameter, `--key-file` parameter (reads key from file), or `CARTOLOAD_WATERMARK_KEY` environment variable.

#### Scenario: Write via CLI with --key parameter
- **WHEN** `cartoload watermark write map.img "order-uuid" --key abc123` is executed
- **THEN** the watermark SHALL be written to the file

#### Scenario: Write via CLI with --key-file parameter
- **WHEN** `cartoload watermark write map.img "order-uuid" --key-file /path/to/keyfile` is executed
- **AND** the key file contains "abc123"
- **THEN** the watermark SHALL be written to the file using the key read from the file

#### Scenario: Write via CLI with env var key
- **WHEN** `CARTOLOAD_WATERMARK_KEY=abc123 cartoload watermark write map.img "order-uuid"` is executed
- **THEN** the watermark SHALL be written to the file

#### Scenario: Write fails with no key
- **WHEN** `cartoload watermark write map.img "order-uuid"` is executed without env var, --key, or --key-file
- **THEN** the command SHALL exit with a non-zero status and print an error message

### Requirement: CLI watermark read command
The system SHALL provide a `cartoload watermark read <img-file>` command that reads and prints the watermark string. The key SHALL be read from (in priority order): `--key` parameter, `--key-file` parameter, or `CARTOLOAD_WATERMARK_KEY` environment variable.

#### Scenario: Read via CLI prints the watermark string
- **WHEN** `cartoload watermark read map.img --key abc123` is executed on a watermarked file
- **THEN** the command SHALL print the original watermark string to stdout

#### Scenario: Read on unwatermarked file
- **WHEN** `cartoload watermark read map.img --key abc123` is executed on a file without a watermark
- **THEN** the command SHALL print "No watermark found" and exit with status 0
