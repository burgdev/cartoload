## Why

This is the core differentiator of cartoload — no open-source tool can write a raster Garmin `.img` file from raw tile data. The format research change provides the specification; this change implements the writer. It produces `.img` files that can be loaded on Garmin devices (Fenix watches, Oregon/GPSMAP handhelds).

## What Changes

- Implement the Garmin raster `.img` writer in `exporters/garmin_img.py` using the format spec from `docs/exporters/garmin-img.md` and the data models from `garmin_img_model.py`
- Writer must: accept a processed raster dataset (GeoTIFF) and layer config, encode tiles into the IMG container format at the specified zoom levels, respect the 3.5 MB per-tile-cell and 4 GB per-file limits, embed attribution in the map name header, and produce a valid `.img` file verifiable with `gmt -i -v`

**Prerequisite**: `format-research` change must be complete.

## Capabilities

### New Capabilities

- `garmin-img-writer`: Write raster Garmin `.img` files from processed GeoTIFF data, supporting multi-resolution pyramids, attribution, and size constraints

### Modified Capabilities

- `package-skeleton`: The stub `exporters/base.py` `BaseExporter` interface may be refined based on actual exporter needs

## Impact

- **Code**: `src/cartoload/exporters/garmin_img.py` goes from stub to full implementation; `src/cartoload/exporters/base.py` interface is finalized
- **Dependencies**: `numpy` (already in deps) for binary packing — no new dependencies
- **Tests**: `tests/test_exporter_garmin_img.py` with unit tests for IMG structure generation (header, subfiles, tile encoding)
- **Risk**: This is the highest-risk change — the format is reverse-engineered and output must be validated on real Garmin devices
