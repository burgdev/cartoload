## 0. Critical Bug Fixes

- [x] 0.1 Fix LBL28/LBL29/RGN2 position fields in headers - they contain garbage values instead of GMP-relative offsets

## 1. Reference File Export Validation

- [x] 1.1 Implement basic GeoTIFF export: read LBL28/LBL29/RGN2 from SwissTopo, decode first 10 tiles, write to GeoTIFF
- [x] 1.2 Verify exported GeoTIFF works: export succeeded for generated file, SwissTopo uses different format (vector+raster)
- [x] 1.3 Add `cartoload analyze img export` CLI command with -o/--output flag
- [x] 1.4 Add --bbox and --zoom filtering to export command
- [x] 1.5 Add export statistics output (tiles processed, bounds, resolution)

## 2. Binary Comparison Implementation

- [x] 2.1 Implement header field normalization: normalize dates, map IDs, UUIDs in TRE/RGN/LBL headers
- [x] 2.2 Implement structural comparison: section positions, sizes, counts (compare SwissTopo vs generated file)
- [x] 2.3 Implement header field comparison: byte-by-byte diff of normalized headers with field names
- [x] 2.4 Implement RGN2 sample comparison: compare first 10 RGN2 records byte-by-byte
- [x] 2.5 Add comparison depth flags: --headers-only, --sample-size N, --full
- [x] 2.6 Run comparison on SwissTopo vs generated test file, document all differences found

## 3. Coordinate Validation Tools

- [x] 3.1 Implement Web Mercator → WGS84 validation: verify TileExtractor bounds computation against WMTS spec
- [x] 3.2 Implement Garmin coordinate encoding validation: verify _deg_to_garmin() matches reference files
- [x] 3.3 Implement RGN2 E0 record validation: check coordinate byte positions, byte order, field values
- [x] 3.4 Implement subdivision delta validation: verify lon_delta/lat_delta encoding in bytes 2-5
- [x] 3.5 Add coordinate validation to analyze command: --tile-details flag shows decoded coordinates
- [x] 3.6 Run coordinate validation on both SwissTopo and generated files, identify discrepancies

## 4. Zoom Level Investigation

- [x] 4.1 Extract and compare TRE1 sections: SwissTopo vs generated file zoom level encoding
- [x] 4.2 Analyze zoom level_number usage: determine if it affects coordinate scaling or display
- [x] 4.3 Test hypothesis: regenerate test file with SwissTopo-style zoom levels (16-20), check if display improves
- [x] 4.4 Document zoom level encoding findings in analysis results

## 5. Bug Fixes Based on Findings

- [x] 5.1 Fix Web Mercator to WGS84 conversion bugs (if found in coordinate validation) — No bugs found
- [x] 5.2 Fix Garmin coordinate encoding bugs (if found: wrong formula, byte order, field positions) — No bugs found
- [x] 5.3 Fix subdivision delta encoding bugs — FIXED: lon_delta/lat_delta were in 24-bit map units but GPXSee expects level-space; now right-shifted by (24 - level_number)
- [x] 5.4 Fix zoom level encoding (if investigation shows this affects display) — Zoom levels don't affect raster display
- [x] 5.5 Fix JPEG-coordinate linkage (if LBL28/LBL29/RGN2 indices are misaligned) — No misalignment found

## 8. Level Number Precision Fix

- [x] 8.1 Identify root cause of missing tiles: GPXSee copyPolys() filters tiles using single-point boundingRect from delta encoding; quantization step (0.0027° at level_number=17) exceeds tile height (0.001875°)
- [x] 8.2 Implement level_number remapping: map to 24-N+1..24 so most detailed level has shift=0
- [x] 8.3 Verify tests pass (96/96 pass)
- [x] 8.4 Update documentation with level_number remapping and boundingRect filtering details

## 9. GPSMAP 66i Crash Investigation

- [x] 9.1 Compare LBL header format with SwissTopo: same hdrLen, same offsets — NOT the crash cause
- [x] 9.2 Check file size constraints: 234 MB is reasonable (SwissTopo is 1.4 GB)
- [ ] 9.3 Test with remapped level_numbers (13-24 instead of 6-17) on device
- [ ] 9.4 If still crashing, investigate TRE7 sentinel change impact on Garmin firmware

## 6. Verification & Testing

- [x] 6.1 Generate new test IMG with all fixes applied
- [ ] 6.2 Export both SwissTopo and new test file as GeoTIFF, visually compare in QGIS
- [x] 6.3 Run binary comparison: verify structural differences are minimized
- [x] 6.4 Run coordinate validation: verify all tiles pass validation
- [ ] 6.5 Test in GPXSee: verify tiles display correctly with proper spacing
- [ ] 6.6 Test on Garmin device (if available): verify map loads and displays

## 7. Documentation & Cleanup

- [x] 7.1 Document all findings in a summary report (what was wrong, what was fixed)
- [x] 7.2 Update analyze command help text with new export/validation options (implemented as CLI command with help)
- [x] 7.3 Add example usage to docs: exporting IMG to GeoTIFF, comparing files (documented in SUMMARY.md)
- [x] 7.4 Run `just check` and `just check types` and `just test` (414/421 tests passing, 7 pre-existing failures unrelated to our changes)
- [x] 7.5 Update MEMORY.md with key findings about LBL header offsets and LBL29 size calculation
