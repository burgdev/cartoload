## Context

The Garmin raster IMG exporter produces files that pass GMapTool validation but are invisible on physical Garmin devices (GPSMAP 66i confirmed). Both the SwissTopo single-map and IOM multi-map reference files render correctly on the device.

Root cause: The current implementation writes 1 TRE2 subdivision record per zoom level. SwissTopo_West has ~598 spatial subdivisions across 5 zoom levels. The Garmin rendering engine uses these subdivisions as a spatial index to locate tiles by geographic coordinates.

Additionally, the polyline preamble (18-byte `0x06 0xB3` record before each Type E0 tile) currently contains all-zero coordinate data. SwissTopo reference files encode actual geographic extent in these preambles.

Key reference data points:
- SwissTopo_West: 5 zoom levels, subdiv_counts=[1, 3, 138, 156, 300], ~598 total TRE2 records
- TRE7: ~599 entries (one per subdivision), rec_size=5 (uint32 offset + flag byte)
- RGN2: `06 B3 [non-zero 16-byte coord bitstream] E0 [tile record]` pairs, grouped by subdivision
- Single-zoom-level test (`-z 15`, 625 tiles, 1 subdivision) still failed on device

## Goals / Non-Goals

**Goals:**
- Produce Garmin raster IMG files that render on physical devices (GPSMAP 66i and similar)
- Implement SwissTopo-style spatial subdivisions matching the proven reference format
- Generate proper polyline preamble coordinate bitstreams
- Maintain backward compatibility with existing tests and GMapTool validation

**Non-Goals:**
- IOM multi-map format support (alternative approach, not needed now)
- Vector map support
- Routing, search, or POI features
- Optimizing subdivision grid algorithms for performance (correctness first)

## Decisions

### Decision 1: Use SwissTopo single-map format

**Choice:** Implement spatial subdivisions within a single GMP subfile (SwissTopo pattern).

**Alternative considered:** IOM multi-map format (split area into many small GMP subfiles, each with 1 subdivision per level). This would avoid the spatial subdivision problem but introduces multi-subfile FAT management, multi-map MPS records, and 0D/BC/DE RGN2 record format complexity.

**Rationale:** SwissTopo format is confirmed working on the target device. Our RGN2 record format (06+E0 pairs) already matches SwissTopo. The single-map approach produces smaller files with less overhead.

### Decision 2: Subdivision grid strategy

**Choice:** Generate subdivisions by grouping tiles into geographic regions at each zoom level. The number of subdivisions per zoom level increases with detail (fewer for overview zooms, more for detailed zooms) — matching the SwissTopo pattern where subdiv_counts=[1, 3, 138, 156, 300].

**Approach:** At each zoom level, subdivide the tile grid into rectangular regions. Each region becomes one subdivision with its own TRE2 record (center lat/lon, RGN2 offset) and TRE7 entry. The exact grid algorithm should be reverse-engineered from the SwissTopo reference by analyzing the relationship between tile positions and subdivision boundaries.

**Fallback:** If exact grid reproduction proves difficult, use a simple regular grid (e.g., group tiles into NxN blocks) and verify on device.

### Decision 3: Polyline preamble encoding

**Choice:** Encode actual coordinate deltas in the 16-byte polyline preamble bitstream instead of all zeros.

**Rationale:** SwissTopo reference has non-zero preamble data (`06 b3 9cf1f509...`). The Garmin device likely uses this to determine tile visibility. The single-zoom test with zero preambles failed on device, suggesting preambles matter even with 1 subdivision.

**Approach:** Study the SwissTopo preamble encoding by comparing known tile bounds with the raw preamble bytes. The Garmin RGN polyline format uses: direction bit + address flag + extra byte count + coordinate deltas at specified bit width.

### Decision 4: TRE7 rec_size

**Choice:** Switch from rec_size=4 (IOM style) to rec_size=5 (SwissTopo style) with uint32 offset + 1 flag byte per entry.

**Rationale:** Matches SwissTopo reference format. The flag byte semantics need investigation from the reference file.

### Decision 5: Phased implementation

**Choice:** Implement in phases: (1) polyline preamble encoding fix, (2) subdivision grid generation, (3) per-subdivision TRE2/TRE7/RGN2 writing. Test on device after each phase.

**Rationale:** The single-zoom test showed that even 1 subdivision fails, which suggests the polyline preamble may be the first blocker. Fixing preambles first may unblock simple cases before tackling the full subdivision grid.

## Risks / Trade-offs

- **[Polyline bitstream format is partially reverse-engineered]** → Study SwissTopo reference preambles carefully. If exact encoding can't be determined, try with minimal non-zero data. The device test is the ultimate validation.
- **[Subdivision grid algorithm unknown]** → Analyze SwissTopo reference subdiv boundaries to reverse-engineer the algorithm. Start with a simple regular grid as fallback.
- **[TRE7 flag byte semantics unknown]** → Extract flag values from SwissTopo reference and replicate the pattern. May need device testing to confirm correct values.
- **[Large code change surface]** → The writer code has tightly coupled layout computation and writing. Changes to subdivision counts cascade through LayoutComputer, GMPWriter, TRE1/TRE2/TRE7 writing, and RGN2 data grouping. Mitigate with phased approach and device testing after each phase.
