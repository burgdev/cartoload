## Context

The STAC downloader (`downloader/stac.py`) queries a STAC collection for items matching a bounding box, then downloads GeoTIFF assets. The function `_find_geotiff_asset()` picks the first asset matching by media type — it iterates the assets dict and returns the first hit. For swisstopo's `pixelkarte-farbe-pk25.noscale` collection, each item has 3 GeoTIFF assets (`kgrs` = grayscale, `komb` = color palette, `krel` = relief RGB). The current code downloads `kgrs` because it happens to be listed first.

The source config already has a `defaults` dict that supports `${layer}` substitution via `source_args`. This is the natural place to add filtering configuration.

## Goals / Non-Goals

**Goals:**
- Allow users to specify which STAC asset to download when items have multiple GeoTIFF assets.
- Use a generic key-value matching mechanism that works with any STAC provider, not just swisstopo.
- Support override per-layer via `source_args` (same pattern as `layer`).

**Non-Goals:**
- Regex or pattern matching on property values — exact match only.
- Filtering on STAC *item* properties (e.g. datetime) — only asset-level properties.
- Multiple filter groups or OR logic — single AND filter is sufficient.

## Decisions

### 1. Filter location: `defaults.asset_filter` dict

Add `asset_filter` as an optional dict under source `defaults`. This follows the existing pattern where `layer` is already a default. It participates in `source_args` resolution so layers can override it.

Alternative considered: A top-level `asset_filter` on the source config. Rejected because it doesn't fit the existing `defaults`/`source_args` pattern and can't be overridden per-layer.

### 2. Filter application: in `_find_geotiff_asset`

Pass `asset_filter` into `_find_geotiff_asset()` (or its caller). After finding assets by media type, filter candidates by matching all key-value pairs. If the filter is empty or missing, keep current behavior.

Alternative considered: Filter at the `query()` level, rejecting entire STAC items. Rejected because the variant is an asset-level property, not an item-level property — all items have all variants.

### 3. Match semantics: exact string equality

Each key in `asset_filter` maps to an expected string value. An asset matches if it has all specified keys with exactly matching values. Properties with non-string types (numbers, etc.) are compared after converting to string.

### 4. Config resolution: `asset_filter` flows through defaults/source_args

`asset_filter` is resolved the same way as `layer` — merged from `defaults` and `source_args`, then passed to the downloader. This means a layer config can override the variant:

```yaml
# Layer config
layers:
  ch_basemap_color:
    source: swisstopo_stac
    source_args:
      layer: ch.swisstopo.pixelkarte-farbe-pk25.noscale
      asset_filter:
        geoadmin:variant: komb
```

## Risks / Trade-offs

- **[Unknown property names]** → If a user specifies a property key that doesn't exist on any asset, all assets will be filtered out and no download will occur. The code should log a clear warning when zero assets match after filtering.
- **[Case sensitivity]** → Property values are compared case-sensitively. This matches how STAC properties work in practice but could surprise users. No mitigation needed — this is the correct behavior.
