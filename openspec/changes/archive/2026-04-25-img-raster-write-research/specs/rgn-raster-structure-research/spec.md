## ADDED Requirements

### Requirement: RGN2 full subdivision structure documentation

The specification SHALL document the complete RGN2 subdivision record structure for raster IMG files, including all record types that appear before and alongside Type E0 raster records: POI-like records (`0D 01`), polyline-like records (`06 B3`), boundary markers (`BC`/`DE`), and Type E0 raster records.

#### Scenario: RGN2 records extracted from IOM.img smallest subfile

- **WHEN** the RGN2 data section is located via RGN sub-header and extracted from IOM.img subfile `00355951` (2 bitmaps)
- **THEN** the documentation SHALL show the complete byte sequence including: `0D 01` record with its trailing data, `06 B3` record with its trailing data, `BC 00 00` boundary marker, `E0 2B 01` Type E0 record, followed by 4×int32 coordinates and uint32 JPEG block size

#### Scenario: RGN2 records extracted from SwissTopo

- **WHEN** the RGN2 data section is extracted from SwissTopo_West.img
- **THEN** the documentation SHALL show whether SwissTopo uses the same multi-record structure (0D/06/BC/DE/E0) or a simplified format with only Type E0 records

#### Scenario: RGN2 record field meanings documented

- **WHEN** the extracted records are analyzed
- **THEN** each record type SHALL have documented: marker byte(s), field layout, field sizes, and purpose (or "purpose unknown" if unclear)

### Requirement: RGN5 format investigation

The specification SHALL document findings from investigating the RGN5 section, including its position, size, and any identifiable structure or patterns.

#### Scenario: RGN5 section located in IOM.img

- **WHEN** the RGN5 section is located via GMP container section offsets or TRE references and extracted from IOM.img
- **THEN** the documentation SHALL describe: whether RGN5 exists, its size, any observed patterns in the data, and whether it appears to contain tile offset/index data

#### Scenario: RGN5 section checked in SwissTopo

- **WHEN** RGN5 is searched for in SwissTopo_West.img
- **THEN** the documentation SHALL note whether RGN5 is present in single-GMP raster maps

#### Scenario: RGN5 necessity assessed

- **WHEN** RGN5 findings are compared against QMapShack wiki and GMT output
- **THEN** the documentation SHALL state whether RGN5 appears necessary for raster rendering or is auxiliary data
