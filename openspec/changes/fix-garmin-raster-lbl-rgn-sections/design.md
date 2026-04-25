## Context

The Garmin IMG raster format implementation in `garmin_img_writer.py` was developed based on analysis of SwissTopo reference files using GMapTool (GMT) hex dumps, the John Mechalas IMG format specification (2005) (`imgformat-1.0.pdf`), and the Willink/Pinns "Exploring Garmin's IMG Format" (2015) (`expl_img2015.pdf`). The implementation successfully creates the GMP container structure with TRE/RGN/LBL/NET sub-headers and passes GMT's basic structural validation (exit code 0).

However, the QMapShack wiki documents critical raster-specific sections that were not captured in earlier reverse engineering:

1. **LBL28 (Image Index)**: Array of uint32 offsets pointing to individual JPEG images in LBL29
2. **LBL29 (Image Storage)**: Sequential JPEG data storage referenced by LBL28
3. **RGN Type E0 Records**: Per-tile metadata with geographic bounds, JPEG size, and LBL28 index references

Without these sections, GMT cannot locate raster tile data (outputs no "Bitmaps" line) and Garmin devices cannot render the tiles.

**Current implementation issues**:

- LBL sub-header defines only the label section (tile filenames), missing LBL28/LBL29 section descriptors
- RGN data section writes 1582 bytes of zeros instead of Type E0 records
- JPEG tiles written at end of GMP after a custom "tile index table" (not part of the IMG specification)
- GMT detects the GMP structure but cannot find the raster image data

**Constraints**:

- Must maintain compatibility with existing TRE/RGN/LBL/NET sub-header structure (already implemented)
- Two-pass layout computation approach must be preserved (size calculation → binary writing)
- Pure Python implementation with numpy for binary packing (no new dependencies)
- Must pass GMT validation with "Bitmaps NNNN, size XXX" output line

## Goals / Non-Goals

**Goals:**

- Implement LBL28 section with uint32 offset array (one entry per JPEG tile, offsets relative to LBL29 start)
- Implement LBL29 section with concatenated JPEG files (move existing JPEG writing logic)
- Implement RGN Type E0 record generation with per-tile bounds, bits_field encoding, block size, and LBL28 index
- Update LBL sub-header builder to include LBL28/LBL29 section info (position, size fields)
- Update GMP layout computation to account for LBL28/LBL29 sections and RGN Type E0 records
- Remove incorrect "tile index table" currently written at end of GMP
- Verify GMT outputs "Bitmaps" line with correct tile count and total size

**Non-Goals:**

- Device testing on physical Garmin hardware (deferred to separate testing phase)
- Optimization of JPEG compression or tile encoding (existing quality settings unchanged)
- Support for other raster formats (JNX, KMZ) - out of scope
- Vector/raster hybrid maps - separate future enhancement
- Encryption or DRM protection schemes

## Decisions

### Decision 1: LBL28/LBL29 as separate sections within LBL data area

**Choice**: Extend the LBL sub-header to define two additional sections (LBL28 at offset 37-44, LBL29 at offset 45-52), write LBL28 data after LBL labels, then LBL29 data.

**Rationale**: The QMapShack wiki shows LBL28 and LBL29 as distinct sections within the LBL subfile. The LBL sub-header format supports multiple section descriptors (each section has position+size fields). Reference SwissTopo files confirmed via hex analysis show these sections present in working raster IMGs.

**Alternative considered**: Single combined image section - rejected because GMT specifically looks for LBL28 (index) and LBL29 (storage) as separate named sections.

### Decision 2: RGN Type E0 record format based on QMapShack wiki

**Choice**: Each Type E0 record consists of:

- Marker byte: `0xE0`
- bits_field: 1 byte (`0x2B` for <256 images, `0x25` for 256-65536 images) - encodes how many bits represent image index
- Coordinates: 4× uint32 LE (lat_min, lon_min, lat_max, lon_max) in Garmin map units
- Block size: uint32 LE (JPEG file size in bytes)
- Image index: variable-length encoding referencing LBL28 entry

**Rationale**: QMapShack wiki documents this as the structure GMT uses to locate raster tiles. The bits_field determines how to decode the image index (8 bits vs 16 bits), allowing compact encoding.

**Alternative considered**: Custom tile index format - rejected because GMT expects the Type E0 structure and won't recognize custom formats.

### Decision 3: bits_field calculation based on total tile count

**Choice**:

- Total tiles < 256: `bits_field = 0x2B` (8 bits per index, 1 byte follows for image index)
- Total tiles 256-65536: `bits_field = 0x25` (16 bits per index, 2 bytes follow for image index)

**Rationale**: QMapShack wiki example shows `0x2B` for 2 images (Isle of Man), `0x25` for 896 images (Lake District). The bits_field encodes the bit-width of the image index field that follows.

**Alternative considered**: Always use 16-bit indices - rejected as wasteful for small tile counts (most test cases have <256 tiles).

### Decision 4: Remove incorrect tile index table, move JPEGs to LBL29

**Choice**: Delete the "tile index table" (uint32 offset array) currently written before JPEG data at end of GMP. Move JPEG writing logic to LBL29 section writer. Create LBL28 index entries during JPEG writing.

**Rationale**: The custom tile index table is not part of the Garmin raster IMG specification. GMT doesn't look for it. LBL28 serves this purpose and is the standard mechanism.

**Trade-off**: Requires reordering GMP data layout. LBL data sections (labels + LBL28 + LBL29) become much larger. But this is required for spec compliance.

### Decision 5: Coordinate encoding in Type E0 uses Garmin map units (32-bit)

**Choice**: Store tile bounds as 4× uint32 LE in Garmin map units (degrees × 2^31 / 180), not 3-byte map units used in TRE header bounds.

**Rationale**: QMapShack wiki shows 32-bit coordinate values in Type E0 records, distinct from the 3-byte coords in TRE header. The existing `_deg_to_garmin()` helper converts decimal degrees to 32-bit map units.

**Alternative considered**: Reuse 3-byte coords - rejected because QMapShack example shows 4-byte (32-bit) values for Type E0.

### Decision 6: Sequential Type E0 records for all tiles across all zoom levels

**Choice**: RGN data section contains Type E0 records in order: zoom level 0 tiles, then zoom level 1 tiles, etc. Each record references an LBL28 index entry sequentially (index 0, 1, 2, ...).

**Rationale**: Simplifies encoding and matches the sequential JPEG storage in LBL29. GMT doesn't require any specific ordering, so sequential is simplest.

**Alternative considered**: Group by zoom level with metadata headers - rejected as over-engineering without evidence from reference files.

## Risks / Trade-offs

### Risk: bits_field encoding may be incorrect for edge cases

The QMapShack wiki provides only two examples: `0x2B` for 2 images, `0x25` for 896 images. The interpretation (8-bit vs 16-bit index encoding) is inferred but not definitively confirmed.

**Mitigation**: Test with multiple tile counts: 1, 10, 100, 255, 256, 1000, 10000. Verify GMT "Bitmaps" output matches expected tile count. If GMT fails to detect images at certain tile counts, investigate alternative bits_field values.

### Risk: 32-bit coordinate precision may cause tile misalignment on devices

Type E0 records use 32-bit coordinates while TRE header bounds use 3-byte (24-bit) coordinates. Devices may interpret these differently, causing tile rendering offsets.

**Mitigation**: Use reference SwissTopo tile bounds as test cases. If device testing reveals misalignment, compare hex dumps of reference vs generated Type E0 records to identify coordinate encoding differences.

### Risk: RGN data section size estimation may be inaccurate

Each Type E0 record has variable size depending on bits_field and image index encoding. Size calculation must account for all tiles across all zoom levels.

**Mitigation**: Implement careful size accounting in `LayoutComputer._compute_gmp_size()`. Add assertion to verify RGN data section size matches computed size before writing.

### Trade-off: Larger GMP subfile size due to LBL28 overhead

LBL28 adds 4 bytes per tile (uint32 offset). For 32,000 tiles, LBL28 is ~128KB. This is negligible compared to JPEG data (typically >1GB) but increases metadata overhead.

**Acceptance**: This overhead is required for spec compliance. The alternative (no LBL28) produces non-functional files.

### Trade-off: Breaking existing (broken) GMT validation tests

Current tests pass with the incorrect structure because they only check GMT exit code 0, not "Bitmaps" line presence. Fixing the implementation will initially break these tests.

**Mitigation**: Update tests in parallel with implementation. Add explicit assertion for "Bitmaps" line in GMT output. Tests will fail until implementation is complete, then pass with correct structure.

## Open Questions

**Q: Does the image index in Type E0 records use zero-based or one-based indexing?**

The QMapShack wiki doesn't specify. Assumption: zero-based (index 0 → first LBL28 entry → first JPEG in LBL29). Will verify against reference file hex dumps if GMT fails to detect images.

**Q: Do Type E0 records require specific byte alignment or padding?**

Unknown. Will implement sequential packing (no padding) and verify with GMT. If GMT fails, investigate alignment requirements from reference files.

**Q: What is the exact binary encoding of the variable-length image index after bits_field?**

For `bits_field=0x2B` (8 bits), assume 1 byte follows (uint8). For `bits_field=0x25` (16 bits), assume 2 bytes follow (uint16 LE). Will validate with reference file analysis if GMT doesn't detect images.
