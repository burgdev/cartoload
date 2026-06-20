## Context

Cartoload generates Garmin IMG raster maps that render correctly in GPXSee but fail on Garmin GPS devices (confirmed on GPSMAP 66i). Investigation comparing our generated files against two known-working references (IOM.img — official Garmin sample, SwissTopo Est/West — third-party raster maps) revealed two distinct bugs.

**Current TRE1 zoom codes** (8 levels, our file):
```
[0] 0x87 (inherited)  [1] 0x86 (inherited)  [2] 0x05  ...  [7] 0x00
```

**Correct TRE1 zoom codes** (8 levels, IOM reference):
```
[0] 0x87 (inherited)  [1] 0x06 (no inherit)  [2] 0x05  ...  [7] 0x00
```

The `_compute_zoom_codes` function applies `0x80` to the first two levels (`if i <= 1`) but the IOM reference only applies it to the first. The existing spec `dynamic-zoom-codes` already specifies the correct pattern.

**Current RGN sub-header** (offsets 0x25–0x7C): all zeros.

**Reference RGN sub-header** has local flag bitmasks and section offsets for polygons, lines, points, and dictionary — fields the Garmin device firmware needs to decode extended object types including raster tiles.

## Goals / Non-Goals

**Goals:**
- Fix TRE1 zoom codes so level 1 is not marked inherited (matching the `dynamic-zoom-codes` spec)
- Populate RGN sub-header extended fields to match the pattern observed in both reference files
- Verify generated IMG files render correctly on both GPXSee and Garmin GPSMAP 66i hardware

**Non-Goals:**
- Changing the raster tile encoding (E0 records, polyline preambles) — already works
- Changing subdivision structure or tiling logic
- Supporting vector map features (only raster maps are in scope)
- Investigating other Garmin device models

## Decisions

### Decision 1: Only level 0 gets the inherited flag

**Choice:** Change `if i <= 1` to `if i == 0` in `_compute_zoom_codes`.

**Rationale:** Both reference files confirm this. The IOM (8 levels) only marks level 0 as inherited. The SwissTopo (5 levels) marks levels 0 and 1 as inherited — but those levels genuinely have no raster data (0 subdivs with rgn_offset > 0). For our use case where all non-overview levels have data, only level 0 should be inherited.

**Alternative considered:** Make the number of inherited levels configurable or data-driven (count levels with no raster data). Rejected because: (a) adds unnecessary complexity for a fixed pattern, (b) the existing spec `dynamic-zoom-codes` already prescribes the correct formula, (c) the implementation just needs to match the spec.

**Note on SwissTopo 5-level pattern:** SwissTopo has `[0x84, 0x83, 0x02, 0x01, 0x00]` with two inherited levels. This is because its level 1 has 2 subdivisions but 0 raster data — it's a genuine overview level. Our generated files always put raster data starting from level 2, so level 1 always has its own data and should NOT be inherited. If SwissTopo-style overview structures are needed in the future, this decision can be revisited.

### Decision 2: RGN header local flags use fixed bitmasks from reference files

**Choice:** Hardcode the local flag values observed in both IOM and SwissTopo:
- `polygonsLclFlags = [0x200000FF, 0x0003FCFD, 0x00000000]`
- `linesLclFlags = [0x2000003F, 0x00000FFD, 0x00000000]`
- `pointsLclFlags = [0x200007FF, 0x003FF73F, 0x00000000]` (IOM value; SwissTopo has slightly different values for wider type range)

**Rationale:** These bitmasks are identical between IOM and SwissTopo (for polygons and lines). They define which object types have local fields — this is a format constant, not application data. Hardcoding avoids premature abstraction.

**Alternative considered:** Compute bitmasks dynamically based on actual object types present. Rejected because: (a) the values are format constants, (b) both references use identical values regardless of their content, (c) dynamic computation adds complexity with no benefit.

### Decision 3: RGN section offsets point to existing RGN2 data for polygons, zero for lines/points

**Choice:** Set `_polygons.offset/size` to the existing RGN2 position/size. Set `_lines` and `_points` offsets to the end of RGN2 data with size 0. Set `_dict` offset to the end of RGN2 with size 0. Set `info` field at 0x79 to 0.

**Rationale:** Our raster maps store all data in RGN2 as polygon objects (type 0x06). Lines and points sections are empty but need valid offsets (not zero) per the reference pattern. The dictionary section is unused. The `info` field controls Huffman table loading — 0 means no compression table.

## Risks / Trade-offs

- **[Fixed bitmasks may not cover future object types]** → The hardcoded flag values cover types 0–13 which is sufficient for raster maps. If vector features are added later, the flags would need updating. Mitigation: add a comment explaining the values and when to update.

- **[SwissTopo uses different pointsLclFlags]** → SwissTopo has `[0x20003FFF, 0x0FFFF73F, 0x00000000]` vs IOM's `[0x200007FF, 0x003FF73F, 0x00000000]`. The difference is in the type range covered. For raster-only maps, IOM's values are sufficient. Mitigation: use the IOM values as baseline since our raster maps are structurally closer to IOM.

- **[Device testing required]** → The zoom code fix alone may not fully resolve rendering. The RGN header fields are also needed. Both changes should be applied together and tested on hardware before declaring success. Mitigation: test incrementally if possible.
