## 1. Fix TRE1 Zoom Code Inheritance

- [x] 1.1 Fix `_compute_zoom_codes` in `garmin_img.py`: change `if i <= 1` to `if i == 0` so only level 0 gets the `0x80` inherited flag. Update the comment block to reflect the correct IOM pattern.
- [x] 1.2 Verify the fix produces correct codes for 8 levels: `[0x87, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00]` and 5 levels: `[0x84, 0x83, 0x02, 0x01, 0x00]` by running existing tests or adding a quick unit test.

## 2. Populate RGN Sub-Header Extended Fields

- [x] 2.1 Update `_build_rgn_subheader` in `garmin_img_writer.py` to accept the RGN2 end position (rgn2_pos + rgn2_size) for computing lines/points/dict offsets.
- [x] 2.2 Write byte 0x25 = 0x02 in the RGN sub-header.
- [x] 2.3 Write polygon local flag bitmasks at offsets 0x29, 0x2D, 0x31, 0x35: `[0x00000000, 0x200000FF, 0x0003FCFD, 0x00000000]`.
- [x] 2.4 Write lines section offset/size at 0x39/0x3D (offset = end of RGN2, size = 0).
- [x] 2.5 Write lines local flag bitmasks at offsets 0x45, 0x49, 0x4D, 0x51: `[0x00000000, 0x2000003F, 0x00000FFD, 0x00000000]`.
- [x] 2.6 Write points section offset/size at 0x55/0x59 (offset = end of RGN2, size = 0).
- [x] 2.7 Write points local flag bitmasks at offsets 0x61, 0x65, 0x69, 0x6D: `[0x00000000, 0x20003FFF, 0x0FFFF73F, 0x00000000]` (corrected from initial spec to match actual SwissTopo reference values).
- [x] 2.8 Write dict offset/size at 0x71/0x75 (offset = end of RGN2, size = 0) and dict info at 0x79 = 1 (corrected from initial spec value of 0 to match SwissTopo reference).
- [x] 2.9 Update all call sites of `_build_rgn_subheader` to pass the new RGN2 end position parameter.

## 2b. Fix TRE2 Subdivision Field Bugs (discovered during PDF cross-check)

- [x] 2b.1 Fix TRE2 `next_level_index` to use 1-based global subdivision numbering (was 0-based). Verified against mkgmap source (`subdivnum = 1`) and Oppmann PDF spec.
- [x] 2b.2 Fix TRE2 width bit 15 semantics: changed from "has children" (set on ALL non-last subdivisions) to "end of chain" (set only on LAST subdivision at each non-last zoom level). Verified against Oppmann PDF spec and mkgmap `Subdivision.setLast(true)`.
- [x] 2b.3 Update both subdivided and legacy TRE2 writing paths in `garmin_img_writer.py`.
- [x] 2b.4 Update `Subdivision` docstring and `encode_tre2_width` docstring in `garmin_img_model.py`.

## 3. Validate and Test

- [x] 3.1 Run `just check` and `just check types` to verify formatting, linting, and type correctness.
- [x] 3.2 Run `just test` to ensure all existing tests pass.
- [x] 3.3 Generate a test IMG: `cartoload build -S examples/configs/sources/swisstopo.yaml -L examples/configs/layers/switzerland.yaml -l ch_basemap_test -y 46.93459 -x 7.51105 -W 5 -H 5 -f --preview`
- [x] 3.4 Verify TRE1 zoom codes with `cartoload analyze img info <file> --summary` — confirm level [1] shows `zoom=6` not `zoom=134`.
- [x] 3.5 Verify RGN header with `cartoload analyze img info <file> --rgn2` — confirm non-zero local flags at 0x2D, 0x31, 0x49, 0x4D, 0x65, 0x69.
- [ ] 3.6 Open generated IMG in GPXSee and verify it renders correctly (no regression).
- [ ] 3.7 Copy to Garmin GPSMAP 66i and verify rendering at all zoom levels (overview through detailed). Confirm tiles are visible and not blurry/stretched.
- [x] 3.8 Run `cartoload analyze img compare` against IOM reference to verify structural alignment.

## 4. Documentation Updates (PDF cross-check)

- [x] 4.1 Add Oppmann PDF documents as resources in `garmin-img-resources.md` with full description.
- [x] 4.2 Fix TRE2 subdivision field documentation in `garmin-img.md`: RGN offset is uint32 with flag bits 31-28, width bit 15 = end of chain (not has-children), next_level is 1-based.
- [x] 4.3 Fix RGN sub-header documentation in `garmin-img.md`: complete field map with correct SwissTopo reference values, encoding flag at 0x25, local flag bitmasks, section positions.
- [x] 4.4 Fix zoom code documentation in `garmin-img.md`: only level 0 gets inherited (not two levels), correct IOM zoom codes from `0x87, 0x86, ...` to `0x87, 0x06, ...`.
- [x] 4.5 Correct points local flag values from spec values to actual SwissTopo reference: `0x20003FFF` / `0x0FFFF73F` (not `0x200007FF` / `0x003FF73F`).
- [x] 4.6 Correct RGN5 dict info from 0 to 1 (SwissTopo reference).
