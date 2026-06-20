## Why

The STAC downloader picks GeoTIFF assets arbitrarily — it returns the first asset matching by media type. For collections like swisstopo's pixelkarte, each item has multiple GeoTIFF variants (grayscale, color, relief-shaded) and the code currently downloads whichever happens to be listed first in the JSON. The user has no way to control which variant is selected.

## What Changes

- Add a generic `asset_filter` option to STAC source configs. It accepts a mapping of STAC asset property keys to expected values (e.g. `geoadmin:variant: komb`).
- When `asset_filter` is set, the downloader only selects assets where all specified properties match.
- When `asset_filter` is not set, the current behavior is preserved (pick first GeoTIFF by media type).
- The filter is passed through `defaults` / `source_args` resolution, so it can be overridden per-layer.

## Capabilities

### New Capabilities
- `stac-asset-filter`: Generic property-based filtering of STAC assets during download. Matches asset-level key-value pairs to select the desired variant from items with multiple GeoTIFF assets.

### Modified Capabilities
_(none — this is additive to the existing `stac-source` capability)_

## Impact

- **Code**: `downloader/stac.py` (`_find_geotiff_asset` and/or `query`), `config.py` (parse `asset_filter` from source defaults)
- **Config format**: New optional `asset_filter` field under STAC source `defaults`. Fully backward-compatible — existing configs without it continue to work.
- **Dependencies**: None.
