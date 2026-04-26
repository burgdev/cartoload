## 1. Research: Analyze SwissTopo Reference Subdivisions

- [x] 1.1 Extract subdivision boundaries from SwissTopo_West.img using `scripts/img_analysis.py` — dump all ~598 TRE2 records with their center coordinates, flags, and RGN offsets
- [x] 1.2 Analyze the relationship between tile grid positions and subdivision boundaries — determine the grid algorithm (e.g., how tiles are grouped into subdivisions at each zoom level)
- [x] 1.3 Decode polyline preamble bitstream format from SwissTopo_West RGN2 data — compare known tile bounds with raw preamble bytes to determine the coordinate delta encoding scheme
- [x] 1.4 Analyze TRE7 flag byte values from SwissTopo_West — determine the pattern for the 1-byte flag in each TRE7 entry (rec_size=5 format)
- [ ] 1.5 Document all findings in `docs/exporters/garmin-img.md` — update Section 5.3 (TRE2 raster subdivision format), Section 4.5.1 (polyline preamble encoding), and Section 5.4 (TRE7 raster layer section)

## 2. Data Model: Add Subdivision Support

- [x] 2.1 Add `Subdivision` dataclass to `garmin_img_model.py` with fields: center_lat, center_lon, zoom_level_index, tiles (list of tile indices), rgn2_offset, flags
- [x] 2.2 Add `generate_subdivisions()` function to `garmin_img.py` that takes tile data (with bounds) per zoom level and returns a list of `Subdivision` objects, one per subdivision across all levels
- [x] 2.3 Write unit tests for `generate_subdivisions()` — verify tile assignment, subdivision count increases with zoom level detail, and all tiles are assigned

## 3. Writer: Update TRE2/TRE7/RGN2 for Multiple Subdivisions

- [x] 3.1 Update `LayoutComputer._compute_gmp_size()` to compute subdivision sizes based on actual subdivision counts instead of `n_zoom * 16`
- [x] 3.2 Update `GMPWriter.write()` TRE2 section to write one 16-byte record per spatial subdivision (with per-subdivision center coordinates and RGN2 offsets) instead of one per zoom level
- [x] 3.3 Update `GMPWriter.write()` TRE7 section to write one entry per subdivision with rec_size=5 (uint32 offset + flag byte) instead of rec_size=4 with one entry per zoom level
- [x] 3.4 Update `GMPWriter.write()` TRE1 map_levels_data to use actual subdivision counts per level instead of hard-coded 1
- [x] 3.5 Update `_build_tre_subheader()` TRE7 descriptor to use rec_size=5 and correct flag byte at TRE+0x86

## 4. Writer: Update RGN2 Data and Polyline Preambles

- [x] 4.1 Update `_write_rgn_data_section()` to write RGN2 data grouped by subdivision (not by zoom level) — iterate subdivisions and write each group's preamble+E0 pairs
- [x] 4.2 Implement proper polyline preamble coordinate encoding in `_write_polyline_preamble()` — encode subdivision extent as coordinate deltas instead of all zeros
- [x] 4.3 Update LBL28/LBL29 and image_index numbering to maintain correct tile-to-image mapping when tiles are ordered by subdivision instead of by zoom level

## 5. Integration and Validation

- [x] 5.1 Run existing test suite — all 76 unit tests in `tests/test_exporter_garmin_img.py` SHALL pass without modification
- [x] 5.2 Add new tests for subdivision generation, per-subdivision TRE2/TRE7 writing, and preamble encoding
- [ ] 5.3 Build test map with `cartoload build -z 15` and validate with `gmt -i -v` — verify bitmap detection, subdivision counts, and TRE7 entries
- [ ] 5.4 Build full test map with all zoom levels and validate with `gmt -i -v`
- [ ] 5.5 Copy IMG to Garmin device and verify the map is visible at Guemligen (GPSMAP 66i)
- [ ] 5.6 Update `docs/exporters/garmin-img.md` with final subdivision format, preamble encoding, and TRE7 rec_size=5 documentation
