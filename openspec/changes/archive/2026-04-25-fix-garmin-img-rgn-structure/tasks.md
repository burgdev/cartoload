## 1. IMG Header Fixes

- [x] 1.1 Fix heads field at offset 0x1A-0x1B: change from 0x0001 to 0x0100 (256) in `IMGHeaderWriter` to match SwissTopo reference
- [x] 1.2 Fix MapSource flag at offset 0x0E: change from 0x50 to 0x00 in `IMGHeaderWriter`
- [x] 1.3 Fix TRE header byte at offset 0x42: change from 0x10 to 0x00 in `_build_tre_subheader`
- [x] 1.4 Update tests in `test_exporter_garmin_img.py` to assert new header values (heads=256, MapSource flag=0x00)

## 2. RGN2 Data Structure Fix

- [x] 2.1 Remove `_write_raster_outline_record` calls from `_write_rgn_data_section` — SwissTopo reference does not use `0x0D` outline records per zoom level
- [x] 2.2 Fix polyline preamble to populate bitstream with actual tile coordinate data instead of all-zero bytes
- [x] 2.3 Recalculate RGN2 size computation (remove 20 bytes per zoom level that were used for outline records)
- [x] 2.4 Update RGN2 size assertions in tests to match new structure (no outline records, smaller total)

## 3. Verification

- [x] 3.1 Run all tests and ensure they pass
- [x] 3.2 Build IMG with `cartoload build` and verify with GMT
- [x] 3.3 Binary compare key header fields and RGN2 structure against SwissTopo_West reference
