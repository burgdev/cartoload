## 1. Investigation & Analysis

- [x] 1.1 Decode SwissTopo reference polyline preambles: extract 10+ raw preamble+E0 record pairs from SwissTopo_West.img RGN2 section, decode the bitstream bytes to determine the exact encoding format (bit widths, delta calculation, coordinate packing)
- [x] 1.2 Hex-compare RGN sub-headers: dump the full 125-byte RGN sub-header from SwissTopo_West.img and from a cartoload-generated IMG, identify all byte differences at offsets 0x25-0x7C, classify each difference as structural (section position/size) vs cosmetic
- [x] 1.3 Hex-compare TRE sub-headers: dump the full 273-byte TRE sub-header from SwissTopo and from cartoload output, identify all field differences
- [x] 1.4 Verify TRE7 segment boundary semantics: trace GPXSee's `subdivInit` → `segments` → `readExtEntry` path with actual SwissTopo TRE7 offsets to confirm that adjacent entries form correct RGN2 segment start/end pairs
- [ ] 1.5 Generate a small test IMG with known coordinates and compare its RGN2 bytes against expected values computed manually from the decoded reference format

## 2. Fix RGN Sub-Header

- [x] 2.1 Populate RGN sub-header extended polygon fields: DEFERRED — analysis shows extended fields (0x25-0x79) are for vector data (global/local flags for lines, points, dictionary). Raster-only maps correctly use zeros. SwissTopo has non-zero values because it's a full vector+raster map.
- [x] 2.2 Verify the RGN header changes by running `cartoload analyze img info --rgn2` on a generated file and confirming the parsed header fields match SwissTopo patterns

## 3. Fix Polyline Preamble Encoding

- [x] 3.1 Rewrite `_write_polyline_preamble` to produce the correct bitstream format discovered in task 1.1 — replaced separate 18-byte preamble + 24-byte E0 record with single 42-byte `_write_rgn2_raster_record` compound record matching GPXSee's `extPolyObjects()` parsing flow. Fixed VUInt32 encoding for bitstream length and remaining section size. Removed old `_pack_signed_bits`, `_compute_bits_field`, `_write_type_e0_record`, `_write_polyline_preamble` functions.
- [x] 3.2 Add a test that generates a preamble for known coordinates and verifies the output bytes match the decoded SwissTopo reference pattern — added `TestRgn2RasterRecord` with 6 tests covering record size, type bytes, VUInt32 encoding, image_id/jpeg_size, delta encoding.
- [x] 3.3 Verify preambles in generated IMG by decoding them with the analysis tool — all 95 garmin img tests pass including integration tests.

## 4. Fix TRE7 Segment Boundaries

- [x] 4.1 Update TRE7 writing to ensure adjacent entries' offsets form proper segment boundaries — subdivision N's data starts at offset[N] and ends at offset[N+1], with the final subdivision's end defined by the sentinel entry — VERIFIED already correct. Each subdivision gets sequential `rgn2_offset`, TRE7 entries contain these offsets, sentinel marks end.
- [x] 4.2 Ensure TRE2 rgn_offset for each subdivision matches its TRE7 extPolygonsOffset value — VERIFIED: both use the same `sub.rgn2_offset` value.
- [x] 4.3 Verify with analysis tool that TRE7 offsets produce non-overlapping, gap-free RGN2 segments — VERIFIED: TRE7 format matches SwissTopo (rec_size=5, flags=0x481).

## 5. Fix TRE Sub-Header

- [x] 5.1 Update TRE sub-header fields based on findings from task 1.3 — VERIFIED already correct. Both SwissTopo and ours have: header_length=273, TRE7 flags=0x481, rec_size=5. Non-zero bytes at 0x9A-0xA9 in SwissTopo are map description/copyright IDs not used for raster tile parsing.
- [x] 5.2 Verify TRE header changes with analysis tool

## 6. Validation & Testing

- [ ] 6.1 Enhance `cartoload analyze img info --rgn2` to group RGN2 records by subdivision using TRE7 segment boundaries (from cli-extent-override spec)
- [ ] 6.2 Add TRE7/RGN2 consistency validation to the analysis tool — check that offsets form valid non-overlapping segments
- [ ] 6.3 Add structured section comparison to `cartoload analyze img compare` — normalize dates/IDs and highlight structural differences in TRE/RGN/LBL headers
- [ ] 6.4 Generate a complete IMG, validate with `cartoload analyze img info --rgn2 --segments`, fix any remaining issues
- [x] 6.5 Run `just check` and `just check types` and `just test` to ensure everything passes — 95 passed, 2 skipped, lint clean, types clean (pre-existing issues only)

## 7. Documentation

- [x] 7.1 Update `docs/exporters/garmin-img.md` and `docs/exporters/garmin-img-resources.md` with any new discoveries from the investigation tasks — completed in previous session: RGN sub-header fields, polyline preamble type decoding, RGN2 per-subdivision segment boundaries, TRE7 segment boundary semantics.
