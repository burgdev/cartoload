## 1. Cache Key Utility

- [x] 1.1 Create `src/cartoload/downloader/cache_key.py` with `url_to_cache_key(url: str, extra: str = "") -> str` implementing the 7-step algorithm: strip scheme+host, remove `${x}/${y}/${z}/${zoom}` (and `$VAR` forms), split on `/` and remove empty/strip `.`, append `extra`, join with `-`, replace `?→-` and `=&→_`, `urllib.parse.quote(safe="-_.")`, truncate to 200 chars
- [x] 1.2 Write tests for `url_to_cache_key`: verify each step of the algorithm (scheme/host stripping, variable removal, split+strip, extra, join, char replacement, url encoding, determinism, truncation)

## 2. Auto-Migration Helper

- [x] 2.1 Add `migrate_cache_key(source_cache_dir: Path, new_key: str) -> None` to `cache_key.py` — detect 12-char hex dirs under `source_id/`, rename to new key, skip if new key already exists, log migration
- [x] 2.2 Write tests for migration: hash dir renamed, skip when new exists, skip when no hash dirs

## 3. Update WMTS Downloader

- [x] 3.1 Replace `_url_cache_key()` usage in `WMTSDownloader.__init__` with `url_to_cache_key()` from `cache_key.py`; call `migrate_cache_key()` before returning `source_cache_dir`; remove old `_url_cache_key()` function
- [x] 3.2 Update `src/cartoload/pipeline.py` — replace `from .downloader.wmts import _url_cache_key` with import from `cache_key.py`, update both call sites
- [x] 3.3 Update WMTS and pipeline-related tests to use new human-readable cache key paths

## 4. Update STAC Downloader

- [x] 4.1 Replace hash-based cache key in `STACDownloader._get_cache_path()` with `url_to_cache_key()`, passing asset filter as `extra` string; call migration helper
- [x] 4.2 Update STAC-related tests to use new human-readable cache key paths

## 5. Verification

- [x] 5.1 Run `just check` and `just check types` to verify formatting, linting, and type correctness
- [x] 5.2 Run `just test` to verify all tests pass
