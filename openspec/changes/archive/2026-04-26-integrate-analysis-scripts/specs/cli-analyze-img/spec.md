## ADDED Requirements

### Requirement: CLI provides analyze img group with info and compare subcommands
The CLI SHALL provide an `analyze img` command group under the `cartoload` main group with two subcommands: `info` and `compare`.

#### Scenario: Running cartoload analyze img without subcommand
- **WHEN** user runs `cartoload analyze img`
- **THEN** Click displays help text listing available subcommands (info, compare)

#### Scenario: Running cartoload analyze without subgroup
- **WHEN** user runs `cartoload analyze`
- **THEN** Click displays help text listing available subgroups (img)

### Requirement: info subcommand inspects an IMG file
The `cartoload analyze img info` command SHALL accept an IMG file path and display parsed header, FAT, TRE, RGN, and LBL section information. It SHALL serve as a native replacement for `gmt -i` read-only inspection.

#### Scenario: Basic analysis of an IMG file
- **WHEN** user runs `cartoload analyze img info path/to/file.img`
- **THEN** the command parses the IMG header, FAT entries, TRE/RGN/LBL sections and prints a structured summary

#### Scenario: List subfiles only
- **WHEN** user runs `cartoload analyze img info path/to/file.img --list`
- **THEN** the command lists all subfiles found in the FAT and exits without further analysis

#### Scenario: Hex dump of a specific section
- **WHEN** user runs `cartoload analyze img info path/to/file.img --hex rgn2`
- **THEN** the command prints raw hex of the RGN2 section

#### Scenario: Full hex dump with ASCII
- **WHEN** user runs `cartoload analyze img info path/to/file.img --dump tre-header`
- **THEN** the command prints a hex dump with ASCII column of the TRE header

#### Scenario: Select specific subfile
- **WHEN** user runs `cartoload analyze img info path/to/file.img --subfile 00355951`
- **THEN** the command analyzes only the matching GMP subfile

#### Scenario: RGN2 annotated view
- **WHEN** user runs `cartoload analyze img info path/to/file.img --rgn2`
- **THEN** the command displays RGN2 section with annotated hex dumps, field-level annotations, and record type markers

#### Scenario: RGN2 segmented by zoom level
- **WHEN** user runs `cartoload analyze img info path/to/file.img --segments`
- **THEN** the command uses TRE7 offsets to split RGN2 data into per-zoom-level segments and displays each segment with hex dump and marker annotations

#### Scenario: RGN2 annotated and segmented combined
- **WHEN** user runs `cartoload analyze img info path/to/file.img --rgn2 --segments`
- **THEN** the command displays RGN2 data both annotated and segmented by zoom level

#### Scenario: File not found
- **WHEN** user runs `cartoload analyze img info nonexistent.img`
- **THEN** the command reports an error that the file was not found

### Requirement: compare subcommand compares two IMG files
The `cartoload analyze img compare` command SHALL accept two IMG file paths and display a side-by-side comparison of their RGN headers and RGN2 data, showing matching and differing bytes.

#### Scenario: Compare two files
- **WHEN** user runs `cartoload analyze img compare reference.img output.img`
- **THEN** the command analyzes both files and prints a comparison showing matching and differing RGN header bytes, plus RGN2 record-level analysis

#### Scenario: Second file not found
- **WHEN** user runs `cartoload analyze img compare reference.img nonexistent.img`
- **THEN** the command reports which file was not found

### Requirement: Documentation is updated
The `docs/cli.md` file SHALL be updated with an `analyze` section documenting the `info` and `compare` commands, their flags, and usage examples. The `AGENTS.md` file SHALL mention `cartoload analyze img` as the recommended way to inspect IMG files.

#### Scenario: CLI docs include analyze commands
- **WHEN** reading `docs/cli.md`
- **THEN** it contains a section documenting `cartoload analyze img info` and `cartoload analyze img compare` with all flags

#### Scenario: AGENTS.md references analyze
- **WHEN** reading `AGENTS.md`
- **THEN** it mentions `cartoload analyze img` as the tool for inspecting IMG files

### Requirement: Obsolete scripts are deleted
The following script files SHALL be deleted: `polyline_preamble_analysis.py`, `polyline_preamble_phase2.py`, `polyline_preamble_phase3.py`, `polyline_preamble_phase4.py`, `polyline_preamble_phase5.py`. The migrated scripts (`img_analysis.py`, `analyze_rgn2.py`, `rgn2_segmented_analysis.py`, `rgn2_deep_analysis.py`) SHALL also be deleted. The `scripts/` directory SHALL be removed.

#### Scenario: No scripts directory remains
- **WHEN** checking for the scripts directory
- **THEN** it does not exist
