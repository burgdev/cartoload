## Context

The cartoload project generates Garmin IMG raster map files from WMTS tiles. The generated file passes GMT validation but does not display on Garmin GPS devices. Binary comparison against the SwissTopo_West.img reference (which works on Garmin devices) reveals several mismatches in the IMG header and RGN2 data section.

The project targets the SwissTopo single-map raster format: 32KB blocks, 1 GMP subfile, priority 24.

### Key Reference Comparison

| Field                 | SwissTopo_West (works)   | Our output (broken)                  |
| --------------------- | ------------------------ | ------------------------------------ |
| Heads (0x1A)          | 256 (0x0100)             | 1 (0x0001)                           |
| MapSource flag (0x0E) | 0x00                     | 0x50                                 |
| TRE+0x42              | 0x00                     | 0x10                                 |
| RGN2 structure        | `0x06`+`0xE0` pairs only | `0x0D` outline + `0x06`+`0xE0` pairs |
| `0x06` preamble data  | Real coordinates         | All zeros                            |

## Goals / Non-Goals

**Goals:**

- Fix IMG header fields to match SwissTopo reference exactly
- Fix RGN2 data section to match SwissTopo reference structure
- Generated IMG files display correctly on Garmin GPS devices

**Non-Goals:**

- Support for multi-map GMP format (IOM style)
- EPSG:21781 Swiss projection support
- Optimizing tile download or processing performance

## Decisions

### Decision 1: Match SwissTopo single-map format exactly

The SwissTopo_West.img reference file is known to work on Garmin devices. We should match its binary format field-by-field rather than guessing at Garmin's requirements.

**Alternative considered:** Implement IOM multi-map format — rejected because SwissTopo single-map is simpler and proven to work.

### Decision 2: Remove `0x0D` outline records from RGN2

SwissTopo reference does NOT use `0x0D` raster outline records at the start of each zoom level. The RGN2 data starts directly with `0x06` preamble + `0xE0` tile record pairs. Our current code writes an `0x0D` record (20 bytes) at the start of each zoom level, which adds ~80 bytes of incorrect data for 4 zoom levels and shifts all subsequent tile offsets.

### Decision 3: Fix heads field to 256

The SwissTopo reference uses heads=256 at offset 0x1A. Our code writes heads=1. This is part of the disk geometry that Garmin devices may validate.

### Decision 4: Fix polyline preambles with real coordinate data

The SwissTopo reference populates the `0x06` preamble bitstream with actual coordinate data. Our code writes all zeros. While degenerate polylines may work, matching the reference format is safer.

## Risks / Trade-offs

- **[Risk]** Fixing multiple fields at once makes it harder to identify which specific fix resolves the device issue → **Mitigation**: Fix all identified differences in one change; if the map still doesn't display, at least we've eliminated all known mismatches
- **[Risk]** Removing `0x0D` outline records may break GMT validation → **Mitigation**: Re-run GMT and all tests after the change; GMT detected bitmaps via the `0xE0` records, not the outline records
- **[Risk]** The polyline preamble bitstream format is not fully documented → **Mitigation**: Use the SwissTopo reference's exact binary pattern as a template
