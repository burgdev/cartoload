## Why

Generated IMG files have multiple binary format differences compared to SwissTopo_West and SwissTopo_Est reference files. GMT shows the map name as `>-  >TestMap` instead of the proper hex ID and name like `09C102B0  >Svizzera_W Raster Map`. Several TRE header fields (TRE5, TRE7 pad, TRE8, TRE9/TRE10, name area) are incorrect, and the RGN1 section is missing entirely. These discrepancies likely prevent Garmin devices from rendering the maps.

## What Changes

- Fix TRE5 section: add 3-byte data (`4b 02 01`) with rec_size=3 and correct pad flag (`01 00 00 00`), matching both SwissTopo references
- Fix TRE8 section: use single entry `06 02 13` (3 bytes, rec_size=3) with pad `00 00 01 00`, matching both SwissTopo references
- Fix TRE7 pad bytes at offset 0x86: change from `01 00 00 00` to `81 04 00 00`
- Fix TRE name area at offset 0xD3: replace ASCII map name with binary zeros (extended TRE field data), matching SwissTopo format
- Fix TRE9/TRE10 descriptors: point to valid section positions with correct rec_size values
- Fix TRE3 copyright section: replace hardcoded bytes with proper label offset indices
- Add RGN1 section data (currently empty in our output, SwissTopo has ~1.3-1.6 KB)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `garmin-img-exporter`: TRE header binary format, TRE extended sections, and RGN1 data must match SwissTopo reference structure

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — TRE header builder, layout computer, section writers
- `tests/test_exporter_garmin_img.py` — tests for corrected binary field values
