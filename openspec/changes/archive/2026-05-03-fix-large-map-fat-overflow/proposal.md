## Why

Building a map for all of Switzerland (585k tiles, ~11 GB) fails with `ValueError: byte must be in range(0, 256)`. The Garmin IMG FAT format has two size limits:

1. **FAT part number**: 1-byte field, max 256 entries per subfile → ~1.88 GB per GMP subfile
2. **FAT block numbers**: uint16, max 65535 blocks × 32KB = ~2 GB **total per IMG file**

The previous file splitting logic divided by zoom level, but a single zoom level (e.g. zoom 16 with 438k tiles, ~7.8 GB) can still exceed both limits.

## What Changes

- Partition tiles into geographic latitude bands when total data exceeds ~1.8 GB
- Write separate IMG files per band (each under the ~2 GB total limit)
- Each IMG file has its own FAT, GMP container, TRE/RGN/LBL/NET sub-headers, and unique map ID
- GPXSee loads all `.img` files from a directory, so multiple files render correctly
- Preserve existing single-file behavior for maps under ~1.8 GB

## Capabilities

### New Capabilities

- `multi-img-export`: Support writing multiple IMG files for large maps, each covering a geographic latitude band and staying under the ~1.8 GB FAT size limit

### Modified Capabilities

- `garmin-img-exporter`: The split logic produces multiple IMG files (one per geographic band) instead of failing with struct overflow. File naming: `{name}_1.img`, `{name}_2.img`, etc.

## Impact

- `src/cartoload/exporters/garmin_img.py` — split logic uses geographic bands → multiple IMG files
- `src/cartoload/exporters/garmin_img_writer.py` — removed multi-GMP code (was infeasible due to uint16 block number limit)
- `src/cartoload/exporters/garmin_img_model.py` — `GMPGroup` dataclass for band partitioning
- Users get multiple `.img` files for maps > ~1.8 GB; single file for smaller maps (unchanged)
