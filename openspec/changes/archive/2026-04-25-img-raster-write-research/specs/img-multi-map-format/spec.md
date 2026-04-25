## ADDED Requirements

### Requirement: Multi-map IMG organization documented

The specification SHALL document the multi-map IMG file format where a single IMG container holds multiple GMP subfiles, each representing a separate geographic tile area.

#### Scenario: IOM.img multi-map structure documented

- **WHEN** the IOM.img GMT output is analyzed (51 GMP subfiles)
- **THEN** the documentation SHALL describe: how multiple GMP subfiles are organized in the FAT, how each GMP subfile covers a different geographic bounding box, and how all subfiles share the same zoom level structure `[17,18,19,20,21,22,23,24]` with zoom values `[87,6,5,4,3,2,1,0]`

#### Scenario: MPS multi-map references documented

- **WHEN** the IOM.img MPS subfile (3936 bytes) is analyzed
- **THEN** the documentation SHALL describe how the MPS contains L-records for each of the 51 maps with their individual map IDs, PID=1, FID=2150, and display names

#### Scenario: Comparison with single-map SwissTopo documented

- **WHEN** IOM.img multi-map structure is compared with SwissTopo's single-GMP structure
- **THEN** the documentation SHALL contrast: single-GMP (SwissTopo, all tiles in one subfile) vs multi-GMP (IOM, geographic tiles as separate subfiles), including FAT organization differences and MPS size differences (98 bytes vs 3936 bytes)

### Requirement: Multi-map parameters documented

The specification SHALL document the consistent parameters observed across multi-map IMG files.

#### Scenario: Per-GMP parameters documented from IOM.img

- **WHEN** parameters from all 51 GMP subfiles in IOM.img are examined
- **THEN** the documentation SHALL show that each subfile uses: `priority 20`, `parameters 1 8 36 1`, `CP 1252`, same zoom structure, and a bitmap count matching its geographic tile area

#### Scenario: Parameter differences between IOM and SwissTopo documented

- **WHEN** IOM parameters are compared with SwissTopo parameters
- **THEN** the documentation SHALL note differences: priority (20 vs 24), parameters second value (8 vs 4), and discuss possible implications
