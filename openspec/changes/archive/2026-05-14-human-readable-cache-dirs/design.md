## Context

The tile cache currently uses a 12-char SHA-256 hash of the URL template as the directory key (e.g. `cache/swisstopo/a1b2c3d4e5f6/20/420/280.jpeg`). This works for uniqueness but is opaque — there's no way to map a cache directory back to its source URL without checking every config.

Four call sites use cache keys:

- **WMTSDownloader** (`wmts.py`): `_url_cache_key(url_template)` → hash
- **STACDownloader** (`stac.py`): `_get_cache_path()` → same hash on `collection_url + asset_filter`
- **pipeline.py**: imports `_url_cache_key` directly in 2 places to compute cache paths for composites and fallback tiles
- **compositor.py**: receives `cache_key` as a passthrough string parameter

## Goals / Non-Goals

**Goals:**

- Replace hash-based cache keys with a human-readable, URL-path-derived directory name
- Keep the encoding deterministic: same URL always produces the same directory name
- Auto-migrate existing hash-based caches on build (no separate CLI command)
- Keep directory names filesystem-safe (no `:`, `/`, `?`, `#`, etc.)

**Non-Goals:**

- Changing the cache structure below the key level (zoom/x/y.format stays the same)
- Supporting cache sharing across different OS filesystems (names only need to work on the current OS)

## Decisions

### 1. URL encoding algorithm: flat, no host

**Decision**: The following pipeline produces the cache key:

1. **Strip scheme and host** from the URL (e.g. `https://wmts.geo.admin.ch/path` → `path`)
2. **Remove known per-tile template variables**: `${x}`, `${y}`, `${z}`, `${zoom}` and legacy `{x}`, `{y}`, `{z}`, `{zoom}` — both `${VAR}` and `$VAR` forms
3. **Split on `/`**, remove empty segments, strip leading/trailing `.` from each segment (e.g. `.jpeg` → `jpeg`, `1.0.0` stays `1.0.0`)
4. **Append `extra`** string if provided (for STAC asset filters)
5. **Join segments with `-`**
6. **Replace `?` → `-`, `=` → `_`, `&` → `_`** to clean up query-string characters
7. **`urllib.parse.quote(safe="-_.")`** to URL-encode anything still unsafe (ensures filesystem safety)

Truncate to 200 chars as a safety limit.

**Rationale**: The host is redundant — `source_id` already identifies the provider (e.g. `swisstopo`). Stripping it keeps keys short and focused on the layer/path that differentiates cache entries. Using `urllib.parse.quote` as the final step is a standard, well-tested way to guarantee filesystem-safe names without inventing custom encoding. Preserving `.` in safe chars keeps dotted version numbers (`1.0.0`) and file extensions readable.

**Examples**:

```
URL: https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg
  1. Strip scheme+host:  1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg
  2. Remove ${z}/${x}/${y}:  1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857///
  3. Split on /, remove empty, strip .:  ["1.0.0", "ch.swisstopo.pixelkarte-farbe", "default", "current", "3857", "jpeg"]
  4. (no extra)
  5. Join with -:  1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg
  6. Replace ?→-, =→_, &→_:  (no change)
  7. urllib.parse.quote(safe="-_."):  1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg
Key: 1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg
```

```
URL: https://wxs.ign.fr/geoportail/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX=${z}&TILEROW=${y}&TILECOL=${x}
  1. Strip scheme+host:  geoportail/wmts?SERVICE=WMTS&...&TILECOL=${x}
  2. Remove ${x}:  geoportail/wmts?SERVICE=WMTS&...&TILECOL=
  3. Split on /, remove empty, strip .:  ["geoportail", "wmts?SERVICE=WMTS&...&TILECOL="]
     → strip . from "TILECOL=" → "TILECOL"
  4. (no extra)
  5. Join with -:  geoportail-wmts?SERVICE=WMTS&...&TILECOL
  6. Replace ?→-, =→_, &→_:  geoportail-wmts-SERVICE_WMTS_..._TILECOL
  7. urllib.parse.quote(safe="-_."):  geoportail-wmts-SERVICE_WMTS_..._TILECOL
Key: geoportail-wmts-SERVICE_WMTS_REQUEST_GetTile_VERSION_1.0.0_LAYER_${layer}_STYLE_normal_FORMAT_image_png_TILEMATRIXSET_PM_TILEMATRIX_TILEROW_TILECOL
```

```
STAC URL: https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe
Extra: "resolution=10m"
  1. Strip scheme+host:  api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe
  2. (no template vars to remove)
  3. Split, remove empty, strip .:  ["api", "stac", "v1", "collections", "ch.swisstopo.pixelkarte-farbe"]
  4. Append extra:  [..., "resolution=10m"]
  5. Join with -:  api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe-resolution=10m
  6. Replace ?→-, =→_, &→_:  api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe-resolution_10m
  7. urllib.parse.quote(safe="-_."):  api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe-resolution_10m
Key: api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe-resolution_10m
```

**Alternative considered**: Custom character replacement only (no `urllib.parse.quote`) — rejected because it could miss edge-case unsafe characters. Using `quote` as a final safety net is more robust.

### 2. Shared encoding utility with `extra` parameter

**Decision**: Create `url_to_cache_key(url: str, extra: str = "") -> str` in `src/cartoload/downloader/cache_key.py`. The `extra` string is appended as an additional segment before joining and encoding.

**Rationale**: Both downloaders currently implement the same hash strategy independently. A shared utility avoids drift. The `extra` parameter (string, not dict) is simple and sufficient — STAC passes the concatenated filter string.

### 3. Auto-migration on build

**Decision**: When computing a cache path, if the new-style directory doesn't exist but an old hash-based directory does, rename it. Detection: a 12-char all-hex directory name under `source_id/` that was produced by the old `_url_cache_key()`.

The migration logic lives in `cache_key.py` as a helper function `migrate_cache_key(source_cache_dir, new_key)` that:

1. Lists directories under `source_cache_dir`
2. For each that is exactly 12 lowercase hex chars
3. Checks if `new_key` already exists (skip if so)
4. Renames hash dir to `new_key`
5. Logs the migration

This is called from the downloader before returning `source_cache_dir`.

**Alternative considered**: Separate CLI command — rejected because it requires an extra manual step. Auto-migration is seamless.

### 4. Template variable removal

**Decision**: Remove `${x}`, `${y}`, `${z}`, `${zoom}` and their `$VAR` forms (without braces) from the URL path before encoding. After removal, split on `/` and remove empty segments, which naturally handles any resulting `//` or trailing `/`.

**Rationale**: These are per-tile variables that don't differentiate layers — every tile of the same layer has different x/y/z values. Removing them keeps the key focused on layer identity.

## Risks / Trade-offs

- **Collisions**: Two different URLs could theoretically produce the same encoded name. → Mitigation: very unlikely given the full path content remains after host stripping. If needed, append a short hash suffix in a future iteration.
- **Very long URLs**: Some URL templates (e.g. IGN France query-style) are long. → Mitigation: 200-char truncation; given `source_id` prefix, remaining content is unique enough.
- **Template variables in non-standard positions**: A URL might have `${x}` in a query param name rather than a path segment. → Mitigation: simple string replacement handles this uniformly regardless of position.
