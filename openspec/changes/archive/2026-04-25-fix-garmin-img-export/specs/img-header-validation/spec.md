## ADDED Requirements

### Requirement: Header DSKIMG magic at correct offset

The IMG header SHALL contain the ASCII string "DSKIMG" at offset 0x10 (bytes 16-21). This is the primary format identifier for Garmin disk image files.

#### Scenario: Magic bytes verification

- **WHEN** an IMG file is written
- **THEN** bytes at offset 0x10 through 0x15 SHALL be exactly `44 53 4B 49 4D 47` ("DSKIMG" in ASCII)

### Requirement: Header format version field

The IMG header SHALL contain a 2-byte little-endian format version at offset 0x16. The value SHALL be 0x0002 (version 2), matching the format used by Garmin MapSource and BaseCamp.

#### Scenario: Version field matches reference

- **WHEN** an IMG file is written
- **THEN** the 2-byte value at offset 0x16 SHALL be `02 00` (LE uint16 = 2)

### Requirement: Header creation date encoding

The IMG header SHALL contain a 6-byte creation date at offset 0x39 encoded as: year (2 bytes LE), month (1 byte), day (1 byte), hour (1 byte), minute (1 byte), second (1 byte).

#### Scenario: Date matches SwissTopo reference encoding

- **WHEN** the creation date is April 16, 2022, 15:03:56
- **THEN** bytes at offset 0x39-0x3E SHALL be `E6 07 04 10 0F 03 38`
- **AND** year bytes `E6 07` decode to 2022 (0x07E6)
- **AND** month byte `04` = April
- **AND** day byte `10` = 16 (0x10)
- **AND** hour byte `0F` = 15
- **AND** minute byte `03` = 3
- **AND** second byte `38` = 56

#### Scenario: Current date encoding

- **WHEN** the creation date is set to the current time
- **THEN** the 6 bytes SHALL decode correctly back to the original datetime

### Requirement: Creator string with length prefix

Offset 0x40 SHALL contain a 1-byte length value equal to the length of the creator string. The creator string itself SHALL be written at offset 0x41, null-padded to 8 bytes total. The default creator SHALL be "GARMIN" (length = 6).

#### Scenario: Default creator GARMIN

- **WHEN** the creator is "GARMIN" (6 characters)
- **THEN** byte at offset 0x40 SHALL be `06` (length of "GARMIN")
- **AND** bytes 0x41-0x46 SHALL be `47 41 52 4D 49 4E` ("GARMIN")
- **AND** bytes 0x47-0x48 SHALL be `00 00` (null padding to 8 bytes)

#### Scenario: Eight-character creator

- **WHEN** the creator is exactly 8 characters long
- **THEN** byte at offset 0x40 SHALL be `08`
- **AND** all 8 bytes at 0x41-0x48 SHALL be the creator characters with no null padding

### Requirement: Map name at offset 0x49

The map name SHALL be written at offset 0x49 as a null-terminated ASCII string, padded to 32 bytes with null bytes. Names longer than 32 bytes SHALL be truncated to 32 bytes.

#### Scenario: Short map name

- **WHEN** the map name is "TestMap" (7 characters)
- **THEN** bytes 0x49-0x4F SHALL be "TestMap" in ASCII
- **AND** bytes 0x50-0x68 SHALL be all zeros (null padding)

#### Scenario: Max length map name

- **WHEN** the map name is exactly 32 characters
- **THEN** all 32 bytes at 0x49-0x68 SHALL be the map name characters with no null terminator (fully packed)

### Requirement: Boot signature at offset 0x1FE

The last 2 bytes of the 512-byte header (offset 0x1FE-0x1FF) SHALL contain the standard x86 boot sector signature `55 AA` (0xAA55 in little-endian).

#### Scenario: Boot signature present

- **WHEN** an IMG file is written
- **THEN** the byte at offset 0x1FE SHALL be `55` and offset 0x1FF SHALL be `AA`

### Requirement: XOR byte indicates no encryption

Offset 0x1A SHALL contain the XOR encryption byte. For unencrypted files, this SHALL be `00`. The writer SHALL always produce unencrypted files.

#### Scenario: Unencrypted file

- **WHEN** an IMG file is written
- **THEN** byte at offset 0x1A SHALL be `00`

### Requirement: Header total size is exactly 512 bytes

The complete IMG header SHALL be exactly 512 bytes. Bytes not explicitly assigned to a field SHALL be zero.

#### Scenario: Header length

- **WHEN** the header is serialized
- **THEN** the output SHALL be exactly 512 bytes

### Requirement: GMT validation passes

The written IMG file SHALL pass validation by GMapTool (`gmt -i -v`) without reporting "Wrong header (block size)" or other structural errors.

#### Scenario: GMT header validation

- **WHEN** an IMG file is written with correct structure
- **AND** `gmt -i -v <file>` is executed
- **THEN** gmt SHALL NOT report "Wrong header" errors
- **AND** gmt SHALL report the correct block size (32768)

#### Scenario: GMT subfile enumeration

- **WHEN** an IMG file is written with GMP and MPS subfiles
- **AND** `gmt -i -v <file>` is executed
- **THEN** gmt SHALL report "sub-files 2"
- **AND** gmt SHALL list the GMP and MPS subfiles with correct sizes
