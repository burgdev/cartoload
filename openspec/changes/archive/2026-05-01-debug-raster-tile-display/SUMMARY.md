# Garmin IMG Raster Tile Display Debug - Summary Report

## Problem Statement

Generated Garmin IMG files displayed tiles "sporadically" and "spread out" in GPXSee, rather than forming a coherent map. The issue was reported after building a map with 12,681 tiles.

## Investigation Findings

### 1. LBL29 Size Calculation (FIXED)

**Issue**: LBL29 size was being calculated as 0 bytes instead of the actual JPEG data size.

**Root Cause**: The size calculation only checked the `compressed_tiles` dict, but when using subdivisions (which we do for proper multi-zoom maps), tiles are stored in `subdivision.tile_entries`.

**Fix**: Updated `LayoutComputer` and `GMPWriter.write()` to iterate subdivisions:
```python
if subdivisions:
    for sub in subdivisions:
        for tile_entry in sub.tile_entries:
            jpeg_data = tile_entry[0] if isinstance(tile_entry, tuple) else tile_entry
            lbl29_size += len(jpeg_data)
```

### 2. LBL28/LBL29 Descriptor Offsets (FIXED)

**Issue**: LBL28/LBL29 raster descriptors were written at wrong offsets in the LBL sub-header.

**Root Cause**: The writer was using offsets 0x180/0x18E. However, GPXSee (`lblfile.cpp`) reads these at LBL+0x184 and LBL+0x192 respectively (when `hdrLen >= 0x19A`). The LBL header starts 2 bytes before the "GARMIN LBL" string (with hdrLen as uint16 LE).

**Correct layout** (verified against GPXSee source and SwissTopo reference):
- LBL+0x184: LBL28 offset (4 bytes) - raster tile index position
- LBL+0x188: LBL28 size (4 bytes)
- LBL+0x18C: LBL28 record size (2 bytes)
- LBL+0x18E: LBL28 flags (4 bytes)
- LBL+0x192: LBL29 offset (4 bytes) - JPEG tile data position
- LBL+0x196: LBL29 size (4 bytes)

**Old format fallback** (SwissTopo vector+raster): LBL28 at 0x108, LBL29 at 0x116.

**Fix**: Updated offsets to 0x184/0x192 in:
- `garmin_img_writer.py` (writer)
- `img_export.py` (GeoTIFF export tool)
- `img_parser.py` (binary parser)
- All test references in `test_exporter_garmin_img.py`

### 3. TRE1 Map Level Field Order (CONFIRMED CORRECT)

**Issue**: A previous session incorrectly swapped the TRE1 map level fields, putting level_number at byte0 and zoom_code at byte1. This was WRONG and was reverted.

**Correct field order** (verified against SwissTopo reference binary):
- byte0 = zoom_code (with 0x80 flag for inherited levels)
- byte1 = level_number (must be ≤ 24, used by GPXSee as `bits` for coordinate shifting)

**Evidence from SwissTopo TRE1 data**:
```
L0: code=0x84(inherited), level_number=20  (bits=20 ≤ 24 ✓)
L1: code=0x83(inherited), level_number=21
L2: code=2, level_number=22
L3: code=1, level_number=23
L4: code=0, level_number=24
```

GPXSee source (`trefile.cpp:107-111`):
```cpp
_levels[i].level = *zoom;       // byte0 = zoom_code
_levels[i].bits = *(zoom + 1);  // byte1 = level_number
```

The `zoom_shifts` computation `max(0, 24 - zoom.level_number)` was already correct.

### 4. GeoTIFF Export Tool (NEW FEATURE)

Implemented comprehensive export functionality to validate raster data:

**Features**:
- Reads LBL28/LBL29/RGN2 sections directly from IMG binary
- Decodes JPEG tiles and geographic bounds from RGN2 compound records
- Creates georeferenced GeoTIFF mosaic
- Supports both newer format (0x184/0x192 offsets) and older format (0x108/0x116 offsets)
- CLI command: `cartoload analyze img export <img_file> -o <output.tif> [--bbox ...] [--zoom ...] [--max-tiles N]`

**Validation Results**:
- SwissTopo export: 5 tiles at correct coordinates (5.87-5.95°E, 46.26-46.27°N)
- Generated file export: 100 tiles, bounds covering Switzerland correctly

### 5. GMT Validation

The regenerated IMG file passes GMT (Garmin Map Tool) validation:

```
Raster Map
levels [6,7,8,9,10,11,12,13,14,15,16,17]
N: 47.81, S: 45.82, W: 5.96, E: 10.49
```

### 6. Binary Structure Verification

Regenerated test IMG verified at the binary level:
- **TRE1**: All level_number (bits) values ≤ 24 ✓, first two levels have 0x80 inherited flag ✓
- **TRE7**: Sentinel entry contains total RGN2 size (532,602 bytes) ✓
- **TRE7 flags**: 0x81 at TRE+0x86 (bit0=ext polygons, bit7=NT format) ✓
- **LBL28**: 12,681 tile entries at correct offset ✓
- **LBL28/29 descriptors**: At correct offsets 0x184/0x192 ✓
- **RGN2**: Compound raster records (42 bytes each) with correct structure ✓

## Root Cause Analysis

The tiles-not-displaying issue had four contributing causes:

1. **LBL29 size was 0** — GPXSee couldn't locate the JPEG tile data. This was the primary bug.

2. **LBL28/LBL29 descriptors at wrong offsets** — Even if LBL29 size had been correct, GPXSee reads these at 0x184/0x192, not 0x180/0x18E. With the descriptors at the wrong location, GPXSee would read garbage values.

3. **TRE1 field swap (from previous session)** — The incorrect swap of zoom_code/level_number put invalid values (bits > 24) in the level records. GPXSee rejects files with bits > 24. This was reverted to the original correct order.

4. **RGN2 lon_delta/lat_delta in wrong coordinate space** — The deltas were written in 24-bit map units, but GPXSee expects them in level-space and left-shifts by `24 - bits`. For level_number=17, this multiplied deltas by 2^7=128, causing polygon boundingRect to be ~2° off from the actual tile position. copyPolys() then filtered out most tiles whose wrong boundingRect fell outside the view, causing the "spread out" appearance.

## Coordinate Validation Results (Section 3)

### Garmin 32-bit Encoding
- Round-trip validation: **PASS** (13 test values, quantization error < 1e-6 degrees)
- Resolution: ~8.4e-8 degrees per unit (2^31 / 180)

### 24-bit Map Units
- Round-trip validation: **PASS** (13 test values, quantization error < 2.2e-5 degrees)
- Resolution: ~2.1e-5 degrees per unit (2^24 / 360)

### RGN2 Raster Tile Bounds (12,681 tiles)
- **Valid orientation** (top>bottom, right>left): 12,681/12,681 (100%)
- **In map bounds**: 12,615/12,681 (66 overview tiles extend beyond detailed map bounds — expected)
- No coordinate encoding bugs found

### SwissTopo Reference File
- **97,549 raster tiles** correctly parsed from RGN2 compound records
- All records exactly 42 bytes with valid Garmin coordinate bounds

### Parser Bug Fix
- **Fixed**: Label pointer was read as VUInt32 (variable length) instead of uint24 (fixed 3 bytes)
- This caused the parser to read 2 bytes too few, misaligning all subsequent field reads
- After fix: 12,681/12,681 raster records correctly parsed (was 0 before fix for generated file)
- SwissTopo also improved from 0 to 97,549 correctly parsed raster records

### TRE2 Subdivision Parsing
- **Fixed**: Proper mixed-size parsing using level information (16-byte for non-last, 14-byte for last zoom level)
- Now correctly parses 181 subdivisions matching the TRE1 level structure

## Zoom Level Investigation (Section 4)

### Key Finding
**Zoom level_number does NOT affect raster tile display.** GPXSee uses level_number (bits) to compute coordinate shifts for vector features in `extPolyObjects()`, but raster tile bounds are read as absolute 32-bit Garmin coordinates in `readRasterInfo()`, independent of any shift.

- Generated file: level_numbers 6-17 (12 zoom levels)
- SwissTopo: level_numbers 20-24 (5 zoom levels)
- Both are valid; the difference reflects the zoom range each map covers

## Bug Investigation (Section 5)

- **No coordinate encoding bugs** found in Web Mercator → WGS84 conversion
- **No Garmin coordinate encoding bugs** found (deg_to_garmin, deg_to_map_units)
- **No subdivision delta encoding bugs** found (lon_delta/lat_delta in RGN2 records)
- **Zoom level encoding** confirmed correct — does not affect raster display
- **JPEG-coordinate linkage** confirmed correct — LBL28/LBL29/RGN2 indices aligned

## Files Modified

### Core Implementation
- `src/cartoload/exporters/garmin_img_writer.py`
  - Fixed LBL29 size calculation in `LayoutComputer` and `GMPWriter.write()`
  - Fixed LBL28/LBL29 descriptor offsets to 0x184/0x192
  - Reverted TRE1 field order (byte0=zoom_code, byte1=level_number)
  - Fixed RGN2 lon_delta/lat_delta: right-shift by (24 - level_number) before writing as int16

### New Files
- `src/cartoload/analysis/img_export.py` — GeoTIFF export tool

### Parser
- `src/cartoload/analysis/img_parser.py`
  - Fixed TRE1 field labels (byte0=zoom_code, byte1=level_number)
  - Fixed LBL28/29 offsets to 0x184/0x192 with hdrLen check
  - Fixed label pointer reading: uint24 (3 bytes) instead of VUInt32 (variable)
  - Added proper mixed-size TRE2 subdivision parsing (16-byte non-last + 14-byte last level)
  - Added `validate_coordinates()` method with round-trip and bounds validation
  - Fixed non-raster record `rec_end` UnboundLocalError

### CLI
- `src/cartoload/cli_analyze.py` — Added `cartoload analyze img export` command
- Added `--tile-details` flag to `info` command for coordinate validation

### Tests
- `tests/test_exporter_garmin_img.py` — Updated all LBL offset references

### Dependencies
- Added `rasterio` for GeoTIFF export

## Test Results

- All 96 Garmin IMG tests pass, 2 skipped
- GMT validates generated file as "Raster Map"
- GeoTIFF export produces correct georeferenced output
- Coordinate validation: all round-trip tests pass, all tiles have valid orientation

## Missing Tiles Root Cause (Section 8)

**Issue**: Tiles displayed sporadically with horizontal band gaps in GPXSee at certain zoom levels.

**Root Cause**: GPXSee's `copyPolys()` filters raster tiles using `poly.boundingRect`, which is a **single-point rectangle** computed from `subdiv_center + (delta << shift)`. With level_number=17 (shift=7), the quantization step is 0.0027°, which exceeds the tile height of 0.001875°. At certain view positions, the boundingRect point falls outside the view rect even though the actual raster tile covers the view area, causing tiles to be filtered out.

The absolute 32-bit tile bounds from `readRasterInfo()` are used only for rendering, NOT for filtering. So even though the tile data is correct, GPXSee never reaches the rendering step for tiles whose boundingRect point is outside the view.

**Fix**: Remapped level_numbers from actual zoom levels (6-17) to `24-N+1..24` (13-24 for 12 levels). The most detailed level now has level_number=24 (shift=0, no quantization error). This matches the SwissTopo pattern (5 levels → level_numbers 20-24).

**Verification**: 88.1% of tiles previously had boundingRect errors up to 0.0027°. With shift=0 at the most detailed level, there is zero quantization error.

## GPSMAP 66i Crash Investigation (Section 9)

**Issue**: Map crashes on Garmin GPSMAP 66i after recent fixes (was working before).

**Investigation Results**:
- LBL header format matches SwissTopo exactly (same hdrLen=0x254, same offsets 0x184/0x192)
- File size (234 MB) is reasonable (SwissTopo reference is 1.4 GB and works)
- Not caused by LBL28/LBL29 descriptor placement

**Likely cause**: The TRE7 sentinel fix (from all-zeros to correct RGN2 size) now causes the Garmin firmware to actually read raster data, exposing a parsing issue in the firmware. Before the fix, the all-zeros sentinel meant the firmware skipped raster data entirely (no tiles displayed, but no crash).

**Status**: Needs device testing with remapped level_numbers (13-24 instead of 6-17).

## Status

All automated validation complete. Sections 0-5 and 8-9 of the debug plan are done.

**Completed fixes**:
1. LBL29 size calculation (was 0)
2. LBL28/LBL29 descriptor offsets (0x180→0x184, 0x18E→0x192)
3. TRE1 field order confirmed correct (byte0=zoom_code, byte1=level_number)
4. RGN2 delta encoding in level-space (right-shifted by 24-level_number)
5. Level_number remapping (24-N+1..24) to fix boundingRect quantization error
6. DeltaStream bitstream encoding (three bugs fixed, 104 tests pass):
   - Missing extended bit in bitstream (1-bit shift misaligning all delta data)
   - Wrong bitSize formula for baseSize > 9 (GPXSee uses 2+2*baseSize-9, not 2+baseSize+1)
   - Redesigned from 2-pair center-based to 1 delta pair from tile bottom-left to top-right

**Remaining manual tasks**:
- Visual testing in GPXSee: verify white grid lines at subdivision boundaries are resolved
- Testing on Garmin device with remapped level_numbers

**Remaining open question**: SwissTopo uses flag=0x01 for empty overview subdivisions in TRE7, while our file uses flag=0x00 for all entries. This may or may not affect display — our overview levels have tiles assigned rather than being truly empty.
