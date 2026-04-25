## Context

The Garmin IMG exporter was built during the `garmin-img-exporter` change based on format research from SwissTopo reference files. The current implementation produces IMG files that:

1. GMapTool (`gmt`) rejects with "Wrong header (block size)" error
2. Are significantly undersized (1.4 MB) compared to expected output based on cached tile data (46 MB)

Analysis of the current `garmin_img_writer.py` against the SwissTopo hex dumps reveals several byte-level mismatches in the header, a completely missing FAT chain implementation, and incorrect subfile directory entry layout. The GMP tile index also uses relative offsets that do not account for the header/metadata sections preceding tile data.

**Current state:**

- `IMGHeaderWriter` writes fields at correct conceptual offsets (0x10 DSKIMG, 0x1FE boot sig) but misses several fields
- FAT region is now correctly implemented via `FATWriter` (completed in `fix-garmin-raster-lbl-rgn-sections` change)
- Subfile directory entries are correctly written via `FATWriter` (completed in `fix-garmin-raster-lbl-rgn-sections` change)
- GMP tile data is now stored via LBL28 (image index) + LBL29 (image storage) instead of a tile index table (completed in `fix-garmin-raster-lbl-rgn-sections` change)
- Per-tile geographic bounds are now computed and stored in RGN Type E0 records (completed in `fix-garmin-raster-lbl-rgn-sections` change)
- Remaining issues: header field mismatches at offsets 0x40, 0x0A-0x0D, 0x0E-0x0F, 0x69-0x6A

**Reference data:**

- SwissTopo_West.img and SwissTopo_Est.img in `tests/data/garmin_samples/`
- IOM.img in `tests/data/garmin_samples/` (multi-map raster with 51 GMP subfiles)
- Hex dumps of first 512 bytes in `SwissTopo_West_header_hex.txt` / `SwissTopo_Est_header_hex.txt`
- GMT verbose output in `SwissTopo_*_gmt_output.txt`
- Format specification in `docs/exporters/garmin-img.md` (includes TRE1-TRE10, RGN2 full structure, LBL28/LBL29, multi-map organization, and vector format reference appendix from Willink/Pinns `expl_img2015.pdf` and Mechalas `imgformat-1.0.pdf`)
- Analysis script: `scripts/img_analysis.py` (FAT chain traversal, GMP-relative offset parsing)

## Goals / Non-Goals

**Goals:**

- Produce IMG files that pass `gmt -i -v` validation without errors
- Produce IMG files with correct total size reflecting all tile data
- Byte-accurate header that matches the format Garmin devices expect
- Working FAT chains that allow Garmin tools to traverse subfile data
- Correct GMP internal structure so tile data is locatable
- Automated regression test using `gmt` validation

**Non-Goals:**

- Device testing on physical Garmin hardware (already tracked in `garmin-img-exporter/tasks.md` Section 10)
- Support for encrypted IMG files (XOR byte != 0x00)
- Vector map subfile types (TRE, RGN, LBL, TYP, MDR) - raster maps only need GMP + MPS
- JNX format output (alternative format, out of scope)
- Support for files larger than 4 GB (splitting logic already exists)

## Decisions

### Decision 1: Reverse-engineer header from hex dumps rather than OSM Wiki

The OSM Wiki IMG format sub-pages (Header, FAT, Subfile_Header) are all empty. The mkgmap SVN WebSVN is currently blocked due to bot scraping. We will rely on the SwissTopo hex dump analysis already documented in `docs/exporters/garmin-img.md` (now enriched with IOM.img binary analysis, Willink/Pinns `expl_img2015.pdf` vector format reference, and QMapShack wiki raster format details from the `img-raster-write-research` change) and the reference files in `tests/data/garmin_samples/`.

**Rationale:** The project already has extensive hex-level analysis of two known-good Garmin raster IMG files. The GMT output provides field-level validation. This is sufficient to fix the header issues.

**Alternative considered:** Wait for mkgmap SVN to become accessible again. Rejected because it blocks progress and the reference files are sufficient.

### Decision 2: Sequential FAT chain for raster subfiles

For raster IMG files with only 2 subfiles (GMP and MPS), the FAT chain can be simple and sequential. Each subfile occupies a contiguous range of blocks. The FAT entries form a simple linked list: block N points to block N+1, with the last block in each chain pointing to an end marker.

**Rationale:** SwissTopo reference files use this pattern (GMP blocks are contiguous, MPS blocks follow). Sequential layout avoids fragmentation and simplifies the writer. The 4 GB file limit and typical raster map sizes (1-2 GB) mean fragmentation is unnecessary.

**Alternative considered:** Allocate blocks non-contiguously with a proper free-block allocator. Rejected as over-engineering for the current use case.

### Decision 3: Two-pass layout with FAT chain construction

~~The current two-pass approach (compute sizes, then write) will be extended to a three-phase approach~~

**Completed:** The two-pass layout with FAT chain construction is now implemented in `FATWriter` (completed in `fix-garmin-raster-lbl-rgn-sections` change). FAT entries are generated from computed block ranges with sequential block chains.

### Decision 4: Fix GMP tile data offsets to be absolute within GMP section

~~The GMP tile index currently stores offsets relative to the start of the tile data section within the GMP subfile. This should be changed to offsets relative to the start of the GMP subfile.~~

**Completed:** The tile index table has been entirely replaced by LBL28 (image index with uint32 offsets to LBL29) + LBL29 (concatenated JPEG storage). This was completed in the `fix-garmin-raster-lbl-rgn-sections` change.

### Decision 5: Header field-by-field alignment with reference hex dumps

The header writer will be updated field-by-field to match the SwissTopo reference files. Key differences identified:

| Offset      | Current                 | Reference                 | Issue                             |
| ----------- | ----------------------- | ------------------------- | --------------------------------- |
| 0x08-0x09   | Not written (zeros)     | `00 00`                   | OK (same)                         |
| 0x0A-0x0D   | `unknown_size_field` LE | `00 00 04 7a` (BE-ish)    | Byte order may be wrong           |
| 0x0E-0x0F   | `checksum_or_id` = 0    | `00 50` / `00 86`         | Should be non-zero, file-specific |
| 0x40        | Not written             | `08` (length of "GARMIN") | Missing length prefix for creator |
| 0x1C0-0x1CF | Zeros                   | FAT descriptor data       | Missing FAT descriptor block      |
| 0x69-0x6A   | Zeros                   | `00 01 20`                | Missing flags/version bytes       |

**Rationale:** Byte-accurate reproduction of the reference format is the safest approach since no definitive specification exists.

## Risks / Trade-offs

- **[Incorrect field interpretation]** The hex dump analysis may misinterpret some fields. Mitigation: Validate every fix against `gmt` output. If `gmt` passes, the field interpretation is correct enough.

- **[Format variation across Garmin tools/devices]** Different Garmin devices and tools may accept different variations. Mitigation: Target `gmt` as the canonical validator, since it's the most widely used inspection tool. Device testing is tracked separately.

- **[FAT entry format uncertainty]** The exact binary format of FAT entries (4-byte pointers? chain vs bitmap?) is estimated from hex dumps, not confirmed from source code. Mitigation: Use the simplest possible chain format (sequential blocks) and validate with `gmt`.

- **[Breaking existing tests]** The header and subfile directory format changes will break existing unit tests that check specific byte offsets. Mitigation: Update all affected tests to match the corrected format.

- **[Checksum at 0x0E-0x0F]** The purpose and generation algorithm for this field is unknown. Setting it to a constant may cause issues on some Garmin firmware versions. Mitigation: Copy the approach from reference files; if that fails, investigate further.

## Open Questions

- What is the exact checksum/ID algorithm for offset 0x0E-0x0F? The SwissTopo files use `00 50` and `00 86`. Is this a hash, a counter, or random? For now we will set it to `0x0050` as a safe default.
- What does the FAT descriptor block at 0x1C0 encode? The reference shows `01 00 00 ff 60 64 00 00 ...` but the interpretation is unclear. Need to investigate whether this is a partition table entry or FAT metadata.
- Should the `map_name` at offset 0x49 include a length byte at 0x40, or is 0x40 a separate field that just happens to equal the creator string length? The reference shows `08` at 0x40 which is the length of "GARMIN", suggesting it is a Pascal-style length-prefixed string.
