## 1. Binary Analysis Tooling

- [x] 1.1 Create Python analysis script to parse GMP container header and compute TRE/RGN/LBL section offsets from any GMP subfile in an IMG file
- [x] 1.2 Add FAT chain traversal to the script to reconstruct GMP subfile data from block pointers (needed for IOM.img where subfiles span multiple FAT entries)

## 2. IOM.img Binary Analysis (Primary Target: subfile 00355951)

- [x] 2.1 Extract and document TRE1 (map levels) from subfile `00355951` — verify 8 level records with descending level numbers (87,6,5,4,3,2,1,0) and ascending zoom codes (17,18,19,20,21,22,23,24)
- [x] 2.2 Extract and document TRE2 (group/subdivision) section — verify 16-byte level group records with RGN offset, obj_types, lon/lat center, flags, subdiv_count, next_level_index
- [x] 2.3 Extract and document TRE7 (raster layer) section — verify header (position, size, record_size, flags) and uint32 offset table to RGN2 raster layer descriptions
- [x] 2.4 Extract and document TRE8 (object type parameters) — verify entries `130606` (raster tiles) and `01060D` (DATA_BOUNDS)
- [x] 2.5 Extract and document full RGN2 subdivision structure — verify complete record sequence: `0D 01` POI-like record, `06 B3` polyline-like record, `BC 00 00` boundary marker, `E0 2B 01` Type E0 record, 4×int32 coordinates, uint32 JPEG block size
- [x] 2.6 Extract and investigate RGN5 section — document position, size, byte patterns, and whether it contains tile offset/index data
- [x] 2.7 Cross-validate all IOM findings against QMapShack wiki values for subfile `00355951`

## 3. SwissTopo Binary Analysis

- [x] 3.1 Extract and document TRE1 (map levels) from SwissTopo_West.img — compare level/zoom encoding with IOM.img
- [x] 3.2 Search for TRE2 group section in SwissTopo_West.img — document whether single-GMP raster maps include group subdivisions
- [x] 3.3 Search for TRE7 raster layer section in SwissTopo_West.img — document whether single-GMP raster maps include raster layer pointers
- [x] 3.4 Search for TRE8 object type parameters in SwissTopo_West.img — document whether single-GMP raster maps include object type definitions
- [x] 3.5 Extract and document RGN2 structure from SwissTopo_West.img — determine if it uses multi-record format (0D/06/BC/DE/E0) or simplified Type E0-only format
- [x] 3.6 Search for RGN5 in SwissTopo_West.img and document findings

## 4. Multi-Map Organization Documentation

- [x] 4.1 Document IOM.img multi-map FAT structure — 51 GMP subfiles with geographic bounding boxes, plus 1 MPS subfile (3936 bytes)
- [x] 4.2 Document MPS multi-map reference format — L-records for all 51 maps with PID=1, FID=2150
- [x] 4.3 Document parameter differences: IOM (`priority 20, parameters 1 8 36 1`) vs SwissTopo (`priority 24, parameters 1 4 36 1`)

## 5. Vector Format Reference Documentation

- [x] 5.1 Document vector TRE subdivision format from Willink/Pinns PDF — 14-byte and 16-byte records, object type bit flags, coordinate encoding
- [x] 5.2 Document vector RGN bitstream encoding from Willink/Pinns PDF — element groups, variable bits-per-coordinate, pointer structure
- [x] 5.3 Document vector LBL label encoding from Willink/Pinns PDF — 6-bit/8-bit/10-bit modes, bit-packing, special codes
- [x] 5.4 Document NET/NOD overview from Willink/Pinns PDF — road network graph, routing nodes
- [x] 5.5 Document hybrid raster+vector considerations — shared sections, raster-specific sections, vector-specific sections, existing tools (mkgmap)

## 6. Specification Document Updates

- [x] 6.1 Update `docs/exporters/garmin-img.md` Section 5 (Zoom Level Encoding) with corrected TRE1 format and IOM/SwissTopo comparison
- [x] 6.2 Add new section to `garmin-img.md`: TRE2 Group Section Format with 16-byte record layout and examples from reference files
- [x] 6.3 Add new section to `garmin-img.md`: TRE7 Raster Layer Section with header format and offset table
- [x] 6.4 Add new section to `garmin-img.md`: TRE8 Object Type Parameters with entry format and observed values
- [x] 6.5 Update `garmin-img.md` Section 4.5 (RGN Data Section) with full RGN2 subdivision structure (0D/06/BC/DE/E0 records)
- [x] 6.6 Add new section to `garmin-img.md`: RGN5 section findings (or "not present in SwissTopo" if applicable)
- [x] 6.7 Add new section to `garmin-img.md`: Multi-Map IMG Organization with IOM.img as example
- [x] 6.8 Add new appendix to `garmin-img.md`: Vector IMG Format Reference from Willink/Pinns PDF
- [x] 6.9 Update `docs/exporters/garmin-img-resources.md` with QMapShack wiki details, IOM.img reference, and Willink/Pinns PDF summary

## 7. Format Variant Recommendation

- [x] 7.1 Compare IOM (multi-GMP) and SwissTopo (single-GMP) format completeness — which sections can we fully understand and document?
- [x] 7.2 Write recommendation in `garmin-img.md`: which format variant to target for the writer implementation, with rationale covering documentation coverage, implementation simplicity, and device compatibility
