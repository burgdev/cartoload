## Phase 1: Fix LBL28/RGN2 Mismatch

- [x] 1.1 Investigate root cause: `generate_subdivisions` was called with remapped level_numbers as keys into `compressed_tiles` (which uses original zoom levels), creating empty subdivisions
- [x] 1.2 Add validation in writer to detect subdivision tile count ≠ compressed_tiles count
- [x] 1.3 Fix: use `sorted(compressed_tiles.keys())` instead of `[z.level_number for z in zoom_levels]` for subdivision generation

## Phase 2: Re-apply Level Number Remapping

- [x] 2.1 Re-apply `level_number = 24 - (n_zoom - 1 - z_idx)` in garmin_img.py
- [x] 2.2 Add `source_zoom` field to `ZoomLevel` to track original WMTS zoom level
- [x] 2.3 Update all `compressed_tiles.get(zoom.level_number, ...)` to use `zoom.source_zoom` (6 occurrences in writer, 2 in garmin_img.py)
- [x] 2.4 Add TRE2 width/height clamping to 0x7FFF for overflow protection at shift=0
- [x] 2.5 Add log output showing zoom → level_number mapping
- [x] 2.6 All 96 Garmin IMG tests pass, 372 total tests pass (6 pre-existing failures unrelated)
- [x] 2.7 Fix DeltaStream bitstream encoding — three bugs found and fixed (104 tests pass):
  - Missing extended bit (1-bit shift causing all delta data misaligned)
  - Wrong bitSize formula for baseSize > 9 (2+baseSize+1 → 2+2*baseSize-9+1)
  - Delta clamping from 2-pair center-based encoding → redesigned to 1 delta pair from bottom-left to top-right
- [x] 2.8 Update garmin-img.md Section 4.5.2 with DeltaStream bitstream format documentation
- [x] 2.9 Update SUMMARY.md with bitstream fix details
- [x] 2.10 Update rgn2-segment-encoding spec with corrected preamble bitstream description

## Phase 3: Validation

- [ ] 3.1 Run GMT validation on generated file
- [ ] 3.2 Run parser validation: `cartoload analyze img info <file> --tile-details`
- [ ] 3.3 Verify no LBL28/RGN2 mismatch in generated file
- [ ] 3.4 Test in GPXSee: verify tiles display without white grid lines at subdivision boundaries
- [ ] 3.5 Test on Garmin device (if available)

## Phase 4: Documentation & Cleanup

- [ ] 4.1 Update MEMORY.md with level_number remapping analysis findings
- [ ] 4.2 Update garmin-img.md documentation with multi-scale zoom level strategy
- [ ] 4.3 Update SUMMARY.md with fix results
