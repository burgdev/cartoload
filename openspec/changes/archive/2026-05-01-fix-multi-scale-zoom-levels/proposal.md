## Why

Generated Garmin IMG raster maps have two remaining issues:

1. **Missing tiles at detailed zoom levels** — GPXSee's `copyPolys()` filters raster tiles using a single-point `boundingRect` derived from the RGN2 delta encoding. With `level_number` = actual zoom level (e.g., 17), the shift is `24 - 17 = 7`, giving a quantization step of 128 map units (~0.0027 degrees). This exceeds the tile size at zoom 17 (~0.0014 degrees), causing ~25% of tiles to have their boundingRect fall outside the view at certain positions. Result: horizontal band gaps.

2. **Lower zoom levels not used** — The first two levels get the `0x80` inherited flag, causing GPXSee to skip them entirely (`_firstLevel` skips inherited levels). With 12 zoom levels (6-17), levels 6-7 are inherited and never displayed. At display zooms below 8, GPXSee shows the coarsest non-inherited level which may have too few tiles for proper overview coverage.

3. **Failed remapping attempt** — Remapping `level_number` from 6-17 to 13-24 (to match SwissTopo's pattern of high level_numbers) broke tile display completely because GPXSee's `MapData::zoom(int bits)` uses `level_number` for zoom selection. The display zoom range shifted from 4-28 to 11-28, causing wrong level selection at most zoom levels.

The SwissTopo reference file works perfectly with only 5 levels (level_numbers 20-24) because **all tiles are at the same source scale** (1:25000). The different zoom levels represent different geographic coverage areas, not different source resolutions. Our map uses tiles at different source scales per zoom level (zoom 6 = coarse, zoom 17 = detailed), which is a fundamentally different approach.

## Analysis Results

### A. Level Number vs Display Zoom Mapping

**A.1 Zoom pipeline** (confirmed via GPXSee source):
- Display zoom is integer 0-28, derived from map scale: `360 / 2^zoom` degrees/pixel
- `MapData::zoom(int bits)` finds highest Zoom with `bits()` ≤ display zoom
- Zoom range: `Range(max(0, first_non_inherited.bits - 2), 28)`
- First 2 levels get `0x80` inherited flag → skipped by GPXSee (`_firstLevel`)

**A.3/A.4 RASTER RENDERING IS LEVEL-NUMBER INDEPENDENT** (critical finding):
GPXSee renders raster JPEGs at their absolute 32-bit geographic bounds from `readRasterInfo()`, with scaling only to fit JPEG pixel dimensions to the geographic area. The `level_number` (bits/shift) is used ONLY for:
1. Zoom selection (when to show this level)
2. boundingRect computation (filtering in copyPolys)
3. Subdivision width/height encoding

It does NOT affect tile rendering, stretching, or placement. A zoom-6 tile at level_number=20 renders identically to a zoom-6 tile at level_number=6.

**Conclusion: multi-scale tiles work in a single GMP.** The level_number is purely an encoding/selection parameter, not a rendering parameter.

### B. SwissTopo vs Multi-Scale

**SwissTopo**: All tiles at same source scale (1:25000), 5 levels with level_numbers 20-24. Overview levels use fewer tiles covering larger areas — NOT composited or downsampled, just fewer tiles from the same source. Created by Jnx2Img.

**Our approach**: Tiles at different source scales per zoom (zoom 6 = coarse WMTS tiles, zoom 17 = detailed WMTS tiles). This is valid — GPXSee doesn't care about source scale, only absolute bounds.

**IOM**: Multiple GMP subfiles per geographic tile (51 in the IOM example). Not needed for our use case — single GMP handles multi-scale correctly.

### C. TRE2 Width Encoding Limits

The TRE2 width field is uint16 (max usable 0x7FFF = 32767). With shift = 24 - level_number:

| Level# | Shift | Max Decodable Width |
|--------|-------|---------------------|
| 13     | 11    | 180°                |
| 20     | 4     | 11.25°              |
| 22     | 2     | 2.81°               |
| 24     | 0     | 0.70°               |

Zoom-6 tiles (5.625° extent) overflow at level_number >= 22. With 12 levels mapped to 13-24, zoom-6 gets level_number=13 — safe. Zoom-10 tiles (0.35°) are safe at all level_numbers.

### D. Why Previous Remapping (13-24) Failed

The 13-24 remapping was theoretically correct for zoom selection and encoding. The "no tiles" issue was likely caused by a file generation bug (LBL28 had 28,239 entries vs 28,184 RGN2 records — 55 mismatched entries). The subdivision count also changed (285→253), suggesting a generation issue, not a zoom selection issue.

## What Changes

### Approach: Re-apply level_number remapping (13-24) with validation

Based on analysis, the 13-24 remapping is correct:
- Level_numbers 15-24 (non-inherited) cover display zooms 13-28
- Most detailed level (zoom 17 → level_number=24) has shift=0, zero quantization error
- TRE2 encoding is safe for all tile sizes
- Rendering is level_number-independent

Implementation:
1. Re-apply `level_number = 24 - (n_zoom - 1 - z_idx)` remapping
2. Add validation to detect LBL28/RGN2 mismatches during generation
3. Investigate and fix the root cause of the 55-entry mismatch
4. Test with GPXSee to verify tile display

### Alternative: Fewer zoom levels

For configs with many levels (12+), consider recommending fewer levels (5-8) to keep level_numbers higher:
- 5 levels → level_numbers 20-24 (SwissTopo pattern)
- 8 levels → level_numbers 17-24
- 12 levels → level_numbers 13-24 (current remapping)

The quantization error at each level depends on shift:
- shift=0 (level_number=24): zero error
- shift=4 (level_number=20): error up to 15 map units (0.00032°), negligible for any tile
- shift=8 (level_number=16): error up to 255 map units (0.0054°), acceptable for tiles >0.01°
- shift=11 (level_number=13): error up to 2047 map units (0.044°), acceptable for overview tiles

## Implementation Tasks

### Phase 1: Fix LBL28/RGN2 Mismatch

- [ ] 1.1 Investigate root cause of 55-entry LBL28/RGN2 mismatch in previous generation
- [ ] 1.2 Add validation in writer to detect LBL28 entry count ≠ RGN2 record count
- [ ] 1.3 Verify: does the mismatch occur with current code (level_number=zl) or only with remapping?

### Phase 2: Re-apply Level Number Remapping

- [ ] 2.1 Re-apply `level_number = 24 - (n_zoom - 1 - z_idx)` in garmin_img.py
- [ ] 2.2 Add log output showing the level_number mapping (zoom Z → level_number L, shift S)
- [ ] 2.3 Verify TRE2 width encoding is correct for all zoom/level_number combinations
- [ ] 2.4 Verify RGN2 delta encoding is correct for all zoom/level_number combinations

### Phase 3: Validation

- [ ] 3.1 Run all tests (96 Garmin IMG tests)
- [ ] 3.2 Run GMT validation on generated file
- [ ] 3.3 Run parser validation: `cartoload analyze img info <file> --tile-details`
- [ ] 3.4 Verify no LBL28/RGN2 mismatch in generated file
- [ ] 3.5 Test in GPXSee: verify tiles display without gaps at all zoom levels
- [ ] 3.6 Test on Garmin device (if available)

### Phase 4: Documentation & Cleanup

- [ ] 4.1 Update MEMORY.md with level_number remapping analysis findings
- [ ] 4.2 Update garmin-img.md documentation with multi-scale zoom level strategy
- [ ] 4.3 Update SUMMARY.md with fix results

## Capabilities

### New Capabilities
- `zoom-level-analysis`: Tool to analyze and validate level_number mapping strategies, showing quantization error, display zoom mapping, and subdivision compatibility for any given configuration

### Modified Capabilities
- `garmin-img-exporter`: Level_number mapping strategy, zoom level merging, and coordinate encoding adjustments based on analysis results

## Impact

- `src/cartoload/exporters/garmin_img.py` — Level_number computation, zoom level mapping
- `src/cartoload/exporters/garmin_img_writer.py` — TRE1/TRE2/TRE7 encoding with adjusted level_numbers, subdivision size calculations
- `src/cartoload/config.py` — Possibly: zoom level validation, merging configuration
- `examples/configs/layers/*.yaml` — May need updated zoom_levels configurations

## Non-Goals

- Fixing GPSMAP 66i device crash (separate issue, depends on this fix)
- Changing tile download/extraction logic (tiles come from WMTS at whatever zoom the config specifies)
- Supporting vector map data (raster-only maps)
