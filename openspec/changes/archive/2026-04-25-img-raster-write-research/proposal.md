## Why

The Garmin IMG raster writer produces files that pass GMT validation and show bitmap counts, but the files likely don't render correctly on Garmin devices. Research from the QMapShack wiki (Alex Whiter's analysis), the Willink/Pinns vector format PDF, and a newly added IOM.img reference file (Isle of Man, 51 GMP subfiles) reveals major undocumented format sections that our writer doesn't produce: TRE2 group sections (geographic subdivisions), TRE7 raster layer pointers, TRE8 object type parameters, correct TRE1 level encoding, and the full RGN2 subdivision structure with preceding POI/polyline-like records before each Type E0 raster record. We also lack documentation of the vector format needed for potential future hybrid raster+vector maps.

## What Changes

- **Binary analysis of IOM.img** — hex dump TRE/RGN sections from the smallest GMP subfile (`00355951`, 3648 bytes) to validate QMapShack wiki findings against actual file data
- **Binary analysis of SwissTopo** — examine TRE2/TRE7/TRE8 sections to determine if single-GMP raster maps differ from multi-GMP hybrid maps
- **Document TRE1 level encoding** — correct the zoom level format: level numbers count DOWN (87,6,5,4,3,2,1,0), zoom codes count UP (17,18,19,20,21,22,23,24)
- **Document TRE2 group section format** — 16-byte level group records with RGN offset, object types, geographic center, flags, subdivision count, and next-level index
- **Document TRE7 raster layer section** — uint32 offset table pointing to raster layer descriptions in RGN2
- **Document TRE8 object type parameters** — type definitions for raster tiles (`130606`) and DATA_BOUNDS (`01060D`)
- **Document full RGN2 subdivision structure** — complete record sequence: POI-like (`0D 01`), polyline-like (`06 B3`), boundary markers (`BC`/`DE`), then Type E0 raster record
- **Investigate RGN5 format** — unknown section containing tile offset/index data
- **Document multi-map IMG organization** — single IMG with multiple GMP subfiles, each covering a geographic tile area, with MPS referencing all maps
- **Document vector IMG format** — from Willink/Pinns PDF: TRE subdivisions, RGN bitstream encoding, LBL 6-bit labels, NET/NOD routing (for future hybrid raster+vector use)
- **Update `docs/exporters/garmin-img.md`** with all new format findings
- **Update `docs/exporters/garmin-img-resources.md`** with new reference sources

## Capabilities

### New Capabilities

- `tre-sections-research`: Binary analysis and documentation of TRE1/TRE2/TRE7/TRE8 section formats for raster IMG files, validated against IOM.img and SwissTopo reference files
- `rgn-raster-structure-research`: Binary analysis and documentation of full RGN2 subdivision structure (0D/06/BC/DE/E0 records) and RGN5 format investigation
- `img-multi-map-format`: Documentation of multi-GMP IMG file organization with multiple map subfiles per IMG container
- `vector-format-reference`: Documentation of Garmin vector IMG format (TRE subdivisions, RGN bitstream, LBL encoding, NET/NOD) from Willink/Pinns PDF for future hybrid raster+vector use

### Modified Capabilities

## Impact

**Files Modified**:

- `docs/exporters/garmin-img.md`: Major additions — TRE1/TRE2/TRE7/TRE8 sections, RGN2 full structure, multi-map organization, vector format reference
- `docs/exporters/garmin-img-resources.md`: Add QMapShack wiki details, IOM.img reference info, Willink/Pinns PDF summary

**Reference Files Analyzed**:

- `tests/data/garmin_samples/IOM.img` (33 MB, 51 GMP subfiles, Isle of Man raster map)
- `tests/data/garmin_samples/SwissTopo_West.img` (1.49 GB, single GMP raster map)
- `tests/data/garmin_samples/SwissTopo_Est.img` (1.42 GB, single GMP raster map)

**External Sources**:

- QMapShack wiki (Alex Whiter): `https://github.com/Maproom/qmapshack/wiki/RasterImg_AWhiter` — primary raster format reference
- Willink/Pinns PDF: `https://www.pinns.co.uk/osm/docs/expl_img2015.pdf` — comprehensive vector format reference
- GMapTool (gmt) output for all three reference files

**Dependencies**: No code changes. This is research and documentation only. Findings will feed into a subsequent implementation change to fix the writer.

**Testing Impact**: No test changes. This produces documentation artifacts that will guide future writer fixes.
