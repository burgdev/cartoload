## ADDED Requirements

### Requirement: GMP data layout excludes tile index table

The GMP subfile data layout SHALL NOT include a separate tile index table between LBL data sections and JPEG data.

#### Scenario: No tile index table written

- **WHEN** a GMP subfile is written
- **THEN** no uint32 offset array SHALL be written after LBL data sections
- **THEN** LBL29 section SHALL immediately follow LBL28 section with no intervening data structures

### Requirement: GMP layout order with LBL28/LBL29 sections

The GMP subfile data layout SHALL follow the order: container header → copyright → TRE sub-header → map info → RGN sub-header → LBL sub-header → NET sub-header → TRE data → RGN data (Type E0 records) → LBL labels → LBL28 → LBL29.

#### Scenario: Complete GMP layout sequence

- **WHEN** a GMP subfile is written
- **THEN** sections SHALL appear in order:
  1. GMP container header (53 bytes)
  2. Copyright strings (null-terminated)
  3. TRE sub-header (273 bytes)
  4. Map info strings
  5. RGN sub-header (125 bytes)
  6. LBL sub-header (596 bytes, now includes LBL28/LBL29 descriptors)
  7. NET sub-header (100 bytes)
  8. TRE data sections (copyright + subdivisions + map_levels)
  9. RGN data section (Type E0 records, NOT zeros)
  10. LBL labels (tile filenames)
  11. LBL28 (image index)
  12. LBL29 (JPEG storage)

#### Scenario: No data after LBL29

- **WHEN** LBL29 section is written
- **THEN** LBL29 SHALL be the final data section in the GMP subfile
- **THEN** the GMP subfile MAY have padding to align to block size, but no additional data structures

### Requirement: GMP size computation includes LBL28/LBL29

The GMP subfile size calculation SHALL include the sizes of LBL28 and LBL29 sections, and SHALL exclude the removed tile index table.

#### Scenario: GMP size accounts for all sections

- **WHEN** LayoutComputer calculates GMP size
- **THEN** size SHALL include: container header + copyright + sub-headers + TRE data + RGN data (Type E0) + LBL labels + LBL28 + LBL29
- **THEN** size SHALL NOT include: tile index table (removed)

### Requirement: LBL sub-header length accommodates LBL28/LBL29 fields

The LBL sub-header SHALL be large enough to contain section descriptors for labels, LBL28, and LBL29 (minimum 53 bytes of section info after common header).

#### Scenario: LBL sub-header has space for three section descriptors

- **WHEN** LBL sub-header is built
- **THEN** header length (first 2 bytes) SHALL be at least 21 (common header) + 8 (labels) + 8 (LBL28) + 8 (LBL29) = 45 bytes minimum
- **THEN** actual header length SHALL match the value used in reference files (596 bytes)
