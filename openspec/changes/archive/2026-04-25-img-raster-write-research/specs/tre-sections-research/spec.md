## ADDED Requirements

### Requirement: TRE1 level encoding documentation

The specification SHALL document the correct TRE1 (map levels) encoding for raster IMG files, based on binary analysis of reference files. The documentation MUST include the byte-level format of each 4-byte level record, the relationship between level numbers and zoom codes, and the observed pattern that level numbers count DOWN while zoom codes count UP.

#### Scenario: TRE1 format documented from IOM.img

- **WHEN** the TRE1 section is extracted from IOM.img subfile `00355951` (offsets computed from GMP container header)
- **THEN** the documentation SHALL show 8 level records with format `level_number(1) zoom_code(1) subdivision_count(2 LE)` where level numbers descend from 87 to 0 and zoom codes ascend from 17 to 24

#### Scenario: TRE1 format documented from SwissTopo

- **WHEN** the TRE1 section is extracted from SwissTopo_West.img GMP subfile
- **THEN** the documentation SHALL show 5 level records and compare the encoding with IOM.img, noting any differences in level numbering or zoom code assignment

#### Scenario: TRE1 findings cross-validated with QMapShack wiki

- **WHEN** extracted binary data is compared against QMapShack wiki's TRE1 description
- **THEN** each field value MUST match the wiki's documented values for subfile `00355951`

### Requirement: TRE2 group section format documentation

The specification SHALL document the TRE2 (group/subdivision) section format for raster IMG files, including the 16-byte level group record structure, geographic center coordinates, object type flags, subdivision counts, and next-level linkage.

#### Scenario: TRE2 records extracted from IOM.img

- **WHEN** the TRE2 section is located via TRE sub-header subdivision position/size fields and extracted from IOM.img subfile `00355951`
- **THEN** the documentation SHALL show the 16-byte record format: `RGN_offset(3) obj_types(1) lon_center(3) lat_center(3) flags(2) subdiv_count(2 LE) next_level_index(2 LE)` with field meanings and coordinate encoding

#### Scenario: TRE2 records extracted from SwissTopo

- **WHEN** the TRE2 section is extracted from SwissTopo_West.img
- **THEN** the documentation SHALL show whether SwissTopo includes TRE2 group sections and how they compare to IOM.img

#### Scenario: TRE2 terminator documented

- **WHEN** the last TRE2 group record is followed by a terminator
- **THEN** the documentation SHALL describe the terminator format (observed as 4 zero bytes `00 00 00 00`)

### Requirement: TRE7 raster layer section documentation

The specification SHALL document the TRE7 (raster layer) section format, including its header structure (position, size, record_size, flags) and the uint32 offset table pointing to raster layer descriptions in RGN2.

#### Scenario: TRE7 section located and extracted from IOM.img

- **WHEN** the TRE7 section is located via TRE sub-header extended section offsets and extracted from IOM.img subfile `00355951`
- **THEN** the documentation SHALL show the section header format and offset table with uint32 values pointing to RGN2 raster layer descriptions

#### Scenario: TRE7 section checked in SwissTopo

- **WHEN** the TRE7 section is searched for in SwissTopo_West.img
- **THEN** the documentation SHALL note whether TRE7 is present in single-GMP raster maps or specific to multi-map files

### Requirement: TRE8 object type parameter documentation

The specification SHALL document the TRE8 (object type parameters) section format, including the 3-byte entries for raster tiles and DATA_BOUNDS objects.

#### Scenario: TRE8 entries extracted from IOM.img

- **WHEN** the TRE8 section is located and extracted from IOM.img subfile `00355951`
- **THEN** the documentation SHALL show entry format `type(1) param1(1) param2(1)` with values `130606` for raster tiles and `01060D` for DATA_BOUNDS

#### Scenario: TRE8 entries checked in SwissTopo

- **WHEN** the TRE8 section is searched for in SwissTopo_West.img
- **THEN** the documentation SHALL note whether TRE8 is present in single-GMP raster maps
