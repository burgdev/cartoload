## Why

The generated Garmin IMG file passes GMT validation but does not display on actual Garmin GPS devices. Binary comparison against the SwissTopo_West.img reference file reveals several header field mismatches that likely cause device rejection.

## What Changes

- Fix IMG header `heads` field at offset 0x1A-0x1B: change from 1 to 256 to match SwissTopo reference
- Fix IMG header MapSource flag at offset 0x0E: change from 0x50 to 0x00 to match SwissTopo reference
- Fix TRE header byte at offset 0x42: change from 0x10 to 0x00 to match SwissTopo reference
- Fix polyline preamble `0x06` records: populate with actual coordinate data instead of all-zero bitstream (SwissTopo reference has real geographic data in these records)
- Fix `0x0D` raster outline records: populate with actual coordinate data instead of all zeros
- Remove `0x0D` outline records from RGN2 — SwissTopo reference does NOT use outline records per zoom level (it starts directly with `0x06`+`0xE0` pairs)

## Capabilities

### New Capabilities

- `img-header-geometry`: Fix IMG header disk geometry fields (heads, MapSource flag) to match Garmin device expectations for 32KB-block raster maps

### Modified Capabilities

(none — no existing specs need modification)

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — IMG header fields, RGN2 data writing, polyline preamble content, outline record handling
- `tests/test_exporter_garmin_img.py` — test assertions must match new header values and RGN2 structure
