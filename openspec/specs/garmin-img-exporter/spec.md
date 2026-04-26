## MODIFIED Requirements

### Requirement: TRE5 extended section format
The TRE5 descriptor at TRE header offset 0x58 SHALL have size=3, rec_size=3. The TRE5 data section SHALL contain exactly 3 bytes: `0x4B, 0x02, 0x01`. The TRE5 pad at offset 0x60-0x63 SHALL be `01 00 00 00`.

#### Scenario: TRE5 descriptor matches SwissTopo reference
- **WHEN** a GMP subfile with subdivisions is written
- **THEN** the TRE5 descriptor position at offset 0x58 points to a separate 3-byte section (not sharing position with TRE8)
- **AND** the TRE5 size field at offset 0x5C is 3
- **AND** the TRE5 rec_size field at offset 0x60 is 3
- **AND** the TRE5 pad bytes at offsets 0x62-0x65 are `01 00 00 00`
- **AND** the TRE5 data bytes are `4B 02 01`

### Requirement: TRE8 object types section
The TRE8 descriptor at TRE header offset 0x8A SHALL have size=3 with a single 3-byte entry `0x06, 0x02, 0x13` (type=0x06, param1=0x02, param2=0x13). The TRE8 pad at offset 0x94 SHALL be `00 00 01 00`.

#### Scenario: TRE8 matches SwissTopo reference format
- **WHEN** a GMP subfile is written
- **THEN** the TRE8 size field at offset 0x8E is 3
- **AND** the TRE8 data section contains exactly 3 bytes: `06 02 13`
- **AND** the TRE8 pad bytes at offsets 0x94-0x97 are `00 00 01 00`

### Requirement: TRE7 pad bytes
The TRE7 pad field at TRE header offset 0x86 SHALL be `0x81, 0x04, 0x00, 0x00` (4 bytes, LE uint32 value 0x0481).

#### Scenario: TRE7 pad matches SwissTopo reference
- **WHEN** a GMP subfile with subdivisions is written
- **THEN** the bytes at TRE header offsets 0x86-0x89 are `81 04 00 00`

### Requirement: TRE name area at offset 0xD3
The TRE header area at offset 0xD3 through 0x110 (end of 273-byte header) SHALL contain binary zeros, not ASCII text.

#### Scenario: Name area contains binary zeros
- **WHEN** a GMP subfile is written with map_name "TestMap"
- **THEN** the bytes at TRE header offset 0xD3 through 0x110 are all `00`
- **AND** no ASCII text from the map name appears at offset 0xD3

### Requirement: TRE9 and TRE10 descriptors
The TRE9 descriptor at TRE header offset 0xAE and TRE10 descriptor at offset 0xBC SHALL point to the RGN1 section position. TRE10 rec_size SHALL be 1.

#### Scenario: TRE9 points to RGN1 position
- **WHEN** a GMP subfile is written
- **THEN** the TRE9 position field at offset 0xAE equals the RGN1 section position
- **AND** the TRE10 position field at offset 0xBC equals the RGN1 section position
- **AND** the TRE10 rec_size field at offset 0xC4 is 1

### Requirement: TRE3 copyright data
The TRE3 copyright data section SHALL contain exactly 6 bytes: `0x0C, 0x00, 0x00, 0x32, 0x00, 0x00`.

#### Scenario: TRE3 copyright matches SwissTopo reference
- **WHEN** a GMP subfile is written
- **THEN** the TRE3 copyright data section bytes are `0C 00 00 32 00 00`
