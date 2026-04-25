## Context

The Garmin IMG raster writer in `src/cartoload/exporters/garmin_img_writer.py` produces files that pass GMT validation but lack critical format sections needed for device rendering. Three reference files are available for analysis:

- **IOM.img** (33 MB, Isle of Man) — multi-map file with 51 GMP subfiles, each containing 2-1136 tiles. This matches the file analyzed in the QMapShack wiki (Alex Whiter's document, subfile `00355951.GMP`).
- **SwissTopo_West.img** (1.49 GB) — single-GMP raster map with 32,443 tiles
- **SwissTopo_Est.img** (1.42 GB) — single-GMP raster map with 28,737 tiles

**Device validation:** All three reference files render correctly on Garmin GPSMAP 66i, Fenix 6, and Fenix 7 watches. The IOM.img is an official Garmin-produced file. The SwissTopo files' source is unknown (possibly older Garmin tooling) but they also work on all tested devices.

**Key outcome:** Our writer must produce files that render on real devices. Both format variants work (multi-GMP IOM style and single-GMP SwissTopo style). The research must determine which variant is simpler to implement correctly, and document a clear recommendation.

The QMapShack wiki (`https://github.com/Maproom/qmapshack/wiki/RasterImg_AWhiter`) provides the most detailed reverse-engineering of raster IMG format available, using the IOM file as reference. The Willink/Pinns PDF covers vector format comprehensively. Our current documentation in `docs/exporters/garmin-img.md` covers header, FAT, GMP container, LBL28/LBL29, and Type E0 records but is missing TRE2/TRE7/TRE8 sections and the full RGN2 structure.

## Goals / Non-Goals

**Goals:**

- Validate QMapShack wiki findings against actual binary data in IOM.img
- Discover the complete raster IMG format structure by binary analysis of reference files
- Document all TRE sections (TRE1 level encoding, TRE2 group section, TRE7 raster layers, TRE8 object types)
- Document the full RGN2 subdivision structure including pre-E0 records (0D, 06, BC, DE)
- Investigate RGN5 format
- Document multi-map IMG organization (multiple GMP subfiles per IMG)
- Document vector IMG format from Willink/Pinns PDF for future hybrid use
- Produce a comprehensive updated format specification in `docs/exporters/garmin-img.md`

**Non-Goals:**

- No code implementation — this is research and documentation only
- No changes to the IMG writer (`garmin_img_writer.py`) or model (`garmin_img_model.py`)
- No attempt to write hybrid raster+vector maps (future work)
- No validation against actual Garmin devices (reference files already confirmed working)

## Decisions

### 1. Primary analysis target: IOM subfile `00355951`

**Decision:** Analyze the smallest GMP subfile in IOM.img (`00355951`, 3648 bytes, 2 bitmaps) as the primary binary analysis target.

**Rationale:** This is the same subfile analyzed in the QMapShack wiki, making cross-validation straightforward. Its small size (3648 bytes) makes hex analysis manageable. It contains the full structure (8 zoom levels, 2 bitmaps) in a minimal footprint.

**Alternative:** Analyze SwissTopo subfiles. Rejected because SwissTopo uses single-GMP organization and different parameters (`1 4 36 1` vs `1 8 36 1`), so it may not have all the sections present in multi-map files.

### 2. SwissTopo TRE comparison

**Decision:** Also examine SwissTopo's TRE sections to determine if single-GMP raster maps include TRE2/TRE7/TRE8 or use a simplified structure.

**Rationale:** SwissTopo is our primary production target. If its format differs from IOM's multi-map format, we need to understand both variants. GMT output shows different level/zoom encoding (`levels [20,21,22,23,24], zoom [84,83,2,1,0]`) vs IOM (`levels [17,18,19,20,21,22,23,24], zoom [87,6,5,4,3,2,1,0]`).

### 3. Documentation structure: extend existing spec

**Decision:** Extend `docs/exporters/garmin-img.md` with new sections rather than creating a separate document.

**Rationale:** The existing spec is already comprehensive (530+ lines). Adding new sections maintains a single source of truth. New sections will be clearly marked as "validated against IOM.img" or "validated against SwissTopo".

### 4. Vector format as appendix

**Decision:** Document vector format details in a new appendix section of `garmin-img.md` rather than a separate file.

**Rationale:** The vector format is only needed as reference for potential future hybrid maps. Keeping it in the same document makes cross-referencing easier. The Willink/Pinns PDF is the primary source; we summarize key structures (subdivisions, bitstream encoding, label encoding) relevant to understanding how raster and vector formats might coexist.

### 5. Analysis methodology: targeted hex dumps

**Decision:** Use Python scripts with `struct` module to parse specific offsets rather than full hex dumps.

**Rationale:** The GMP container offsets are known from GMT output. We can compute exact byte positions for TRE/RGN/LBL sections and extract just the fields we need. This is more precise than manual hex analysis and produces reproducible results that can be committed as validation scripts.

## Risks / Trade-offs

**[Risk] QMapShack wiki may be inaccurate or incomplete** → Cross-validate every finding against actual IOM.img binary data. Document confidence levels (high/medium/low) for each discovered field.

**[Risk] SwissTopo format may differ from IOM format** → Analyze both. Document differences explicitly. Our writer needs to produce SwissTopo-style files, so its format takes priority if they differ.

**[Risk] RGN5 format is completely unknown** → Best-effort investigation. Document what we find and mark remaining unknowns. May require a follow-up research change.

**[Risk] Documentation becomes too large** → Focus on fields needed for writing. Document discovered-but-unexplained fields as "purpose unknown" rather than speculating.

**[Trade-off] Research-only change delays writer fix** → Necessary trade-off. Without correct format documentation, further writer changes would be guesswork. The research is a prerequisite for any meaningful fix.

### 6. Format variant recommendation

**Decision:** Research both IOM (multi-GMP) and SwissTopo (single-GMP) formats, then recommend one as the target for our writer based on completeness of documentation and implementation simplicity.

**Rationale:** Both formats render correctly on all tested devices (GPSMAP 66i, Fenix 6, Fenix 7). The IOM format is better documented (QMapShack wiki) but uses a more complex multi-map structure. The SwissTopo format is simpler (single GMP) but has less community documentation. The research will reveal which format's sections we can fully understand and implement.

**Key comparison (preliminary):**

```
                    IOM (multi-GMP)          SwissTopo (single-GMP)
Source              Garmin official          Unknown tooling
GMP subfiles        51 per IMG               1 per IMG
MPS size            3936 bytes               98 bytes
Zoom levels         8 [17..24]               5 [20..24]
Parameters          1 8 36 1                 1 4 36 1
Documentation       QMapShack wiki           Limited
Max file size       Smaller (per subfile)    Up to 4 GB
```

## Open Questions

- Does SwissTopo include TRE2 group sections, or is that specific to multi-map files?
- What is the relationship between level numbers and zoom codes? The IOM file shows them counting in opposite directions (levels DOWN from 87, zoom codes UP from 17).
- What is the `parameters 1 8 36 1` field meaning? SwissTopo uses `1 4 36 1`. The second value differs (8 vs 4).
- Is RGN5 required for raster rendering, or is it auxiliary data?
- Do single-GMP raster maps (like SwissTopo) use the same multi-record RGN2 structure (0D/06/BC/DE/E0), or only the Type E0 records?
- **Which format variant should we target for implementation?** The research must produce a recommendation with clear rationale.
