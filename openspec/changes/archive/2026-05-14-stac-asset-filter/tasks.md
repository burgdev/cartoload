## 1. Config

- [x] 1.1 Add `asset_filter` to `SourceConfig.defaults` parsing in `config.py` — it's a `dict[str, str] | None` field that flows through `source_args` resolution like `layer`
- [x] 1.2 Pass resolved `asset_filter` from pipeline to `STACDownloader.run()` and through to `query()`

## 2. Downloader

- [x] 2.1 Modify `_find_geotiff_asset()` to accept an optional `asset_filter: dict[str, str]` parameter. When provided, filter candidate assets to those where all filter keys match the asset properties (string equality). When not provided, keep existing behavior
- [x] 2.2 In `query()`, pass `asset_filter` through to `_find_geotiff_asset()`. When filter is set but no assets match for an item, log a warning with item ID and skip the item

## 3. Config & Examples

- [x] 3.1 Add `asset_filter: { geoadmin:variant: komb }` to the `swisstopo_stac` source defaults in `examples/configs/sources/swisstopo.yaml`
- [x] 3.2 Update `docs/configuration/sources.md` to document `asset_filter` for STAC sources

## 4. Tests

- [x] 4.1 Add unit tests for `_find_geotiff_asset` with `asset_filter`: no filter (existing behavior), single-key filter, multi-key filter, filter with no match
- [x] 4.2 Add test for `query()` with `asset_filter`: verify items with no matching assets are skipped with a warning
- [x] 4.3 Add config parsing test: `asset_filter` in defaults, override via source_args, absent (None)
- [x] 4.4 Run `just check` and `just test` to verify everything passes
