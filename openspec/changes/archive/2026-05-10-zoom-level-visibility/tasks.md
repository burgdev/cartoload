## 1. Update zoom code computation

- [x] 1.1 Modify `_compute_zoom_codes()` to accept a parameter indicating which levels have tiles (e.g., `has_tiles: list[bool]` or pass the tile counts)
- [x] 1.2 Change the inherited flag logic: set 0x80 only on consecutive empty levels from the top (levels before the first level with tiles), not unconditionally on level 0
- [x] 1.3 Update the function signature and add docstring explaining the new inherited flag behavior

## 2. Update callers of _compute_zoom_codes

- [x] 2.1 Update the call site in `garmin_img.py` (around line 920) where `_compute_zoom_codes()` is called — pass tile presence information derived from the tile data or tile metadata
- [x] 2.2 Ensure both the `compressed_tiles` path and the tile metadata path provide correct tile presence info

## 3. Update tests

- [x] 3.1 Update existing tests for `_compute_zoom_codes()` to use the new signature with tile presence parameter
- [x] 3.2 Add test cases for: all levels have tiles (no 0x80), some empty top levels (0x80 on empty prefix only), first level has tiles (no 0x80 anywhere)

## 4. Verification

- [x] 4.1 Generate an IMG file with empty overview levels and verify the TRE1 zoom codes show 0x80 only on the empty levels *(verified — new file shows zoom codes [7,6,5,4,3,2,1,0] with no 0x80 set since all levels have tiles)*
- [ ] 4.2 Open the file in GPXSee and verify the map is visible at the most-zoomed-out scale *(manual verification)*
- [ ] 4.3 Test on GPSMAP 66i and verify the map no longer disappears when zooming out *(manual — device test)*
