## ADDED Requirements

### Requirement: tile grid computation from bbox + zoom

The `WMTSDownloader` SHALL provide a method that takes a bounding box (min_lon, min_lat, max_lon, max_lat) in WGS84 and a zoom level, and returns the set of (x, y) tile indices covering that area using the standard Web Mercator (EPSG:3857) tile scheme.

#### Scenario: compute tile grid for a known bbox at zoom 10

- **WHEN** the tile grid computation is called with bbox `(7.0, 46.0, 8.0, 47.0)` and zoom `10`
- **THEN** the result is a set of `(x, y)` tile coordinate tuples that fully cover the bounding box, where each tile index is within the valid range `[0, 2^zoom - 1]`

#### Scenario: bbox spanning the antimeridian

- **WHEN** the tile grid computation is called with a bbox where min_lon > max_lon (e.g., `(179.0, 0.0, -179.0, 1.0)`)
- **THEN** the tile indices wrap around correctly so that tiles on both sides of the antimeridian are included

#### Scenario: single tile bbox

- **WHEN** the tile grid computation is called with a bbox that fits entirely within a single tile
- **THEN** the result contains exactly one `(x, y)` tuple

### Requirement: URL template interpolation

The `WMTSDownloader` SHALL expand a URL template string by substituting `{zoom}`, `{x}`, `{y}`, and `{source_id}` placeholders with actual values for each tile.

#### Scenario: interpolate XYZ URL template

- **WHEN** the URL template is `https://wmts.example.com/tiles/{zoom}/{x}/{y}.jpeg` and the tile coordinates are `(x=543, y=361)` at zoom `10`
- **THEN** the interpolated URL is `https://wmts.example.com/tiles/10/543/361.jpeg`

#### Scenario: interpolate KVP-style WMTS URL

- **WHEN** the URL template is `https://wmts.example.com/wmts?SERVICE=WMTS&REQUEST=GetTile&LAYER=basemap&TILEMATRIXSET=3857&TILEMATRIX={zoom}&TILECOL={x}&TILEROW={y}&FORMAT=image/jpeg` and the tile coordinates are `(x=543, y=361)` at zoom `10`
- **THEN** the interpolated URL contains `TILEMATRIX=10&TILECOL=543&TILEROW=361`

#### Scenario: interpolate with source_id

- **WHEN** the URL template contains `{source_id}` and the source ID is `swisstopo_wmts`
- **THEN** the interpolated URL has `swisstopo_wmts` in place of `{source_id}`

### Requirement: concurrent downloads with thread limit

The `WMTSDownloader` SHALL download tiles concurrently using `concurrent.futures.ThreadPoolExecutor` with a configurable `max_workers` parameter (default 4).

#### Scenario: download with default concurrency

- **WHEN** `WMTSDownloader` downloads a grid of 100 tiles with `max_workers=4`
- **THEN** at most 4 tiles are being fetched simultaneously at any point during the download

#### Scenario: download with custom concurrency

- **WHEN** `WMTSDownloader` is configured with `max_workers=8`
- **THEN** at most 8 tiles are being fetched simultaneously

#### Scenario: download single tile

- **WHEN** the tile grid contains exactly one tile
- **THEN** the tile is downloaded successfully without spawning a thread pool (or with `max_workers=1`)

### Requirement: rate limiting between requests

The `WMTSDownloader` SHALL enforce a minimum delay between consecutive HTTP requests. The delay SHALL be configurable (default 150ms).

#### Scenario: rate limiting enforced

- **WHEN** the downloader makes requests with a configured delay of 200ms
- **THEN** the elapsed time between the start of consecutive requests is at least 200ms

#### Scenario: rate limiting with multiple threads

- **WHEN** 4 threads are downloading with a 150ms delay
- **THEN** each thread enforces the delay independently, so the aggregate throughput is approximately 4 / 0.150 requests per second

### Requirement: caching to disk (skip existing)

The `WMTSDownloader` SHALL store downloaded tiles in the cache directory at `cache/{source_id}/{zoom}/{x}/{y}.{ext}`. If a tile file already exists at that path, the download SHALL be skipped.

#### Scenario: cache miss downloads tile

- **WHEN** a tile at `(zoom=10, x=543, y=361)` does not exist in the cache
- **THEN** the tile is downloaded and written to `cache/{source_id}/10/543/361.jpeg`

#### Scenario: cache hit skips download

- **WHEN** a tile at `(zoom=10, x=543, y=361)` already exists in the cache
- **THEN** no HTTP request is made for that tile and the progress bar increments

#### Scenario: atomic cache write

- **WHEN** a tile is being written to cache
- **THEN** the tile is first written to a `.tmp` file in the same directory and then atomically renamed to the final path

#### Scenario: cache directory is created

- **WHEN** the cache directory `cache/{source_id}/{zoom}/{x}/` does not exist
- **THEN** the directory is created before writing the tile file

### Requirement: retry on HTTP errors

The `WMTSDownloader` SHALL retry failed tile downloads on HTTP 429 (Too Many Requests) and 5xx (server error) status codes. Retries SHALL use exponential backoff with a maximum of 3 attempts.

#### Scenario: retry on HTTP 503

- **WHEN** a tile request returns HTTP 503 on the first attempt
- **THEN** the downloader waits (backoff) and retries up to 3 times with exponential backoff (1s, 2s, 4s)

#### Scenario: retry on HTTP 429

- **WHEN** a tile request returns HTTP 429 on the first attempt and succeeds on the second attempt
- **THEN** the tile is downloaded successfully and no further retries are needed

#### Scenario: exhaust retries

- **WHEN** a tile request fails with HTTP 5xx on all 3 attempts
- **THEN** the tile is recorded as failed and the download continues with remaining tiles

#### Scenario: no retry on HTTP 404

- **WHEN** a tile request returns HTTP 404
- **THEN** no retry is attempted and the tile is recorded as failed immediately

### Requirement: rich progress bar output

The `WMTSDownloader` SHALL display download progress using `rich.progress.Progress` with columns showing a spinner, description, progress bar, percentage, tile count (`{done}/{total}`), and elapsed time.

#### Scenario: progress bar during download

- **WHEN** a download of 100 tiles starts
- **THEN** a rich progress bar is displayed showing tiles completed out of total (e.g., `42/100`), percentage, and elapsed time

#### Scenario: progress bar reflects cache hits

- **WHEN** 20 of 100 tiles are already cached and 80 need downloading
- **THEN** the progress bar total is 100 and the cached tiles are counted immediately, then the bar advances as new tiles are downloaded

#### Scenario: progress bar on completion

- **WHEN** all tiles finish downloading
- **THEN** the progress bar shows 100% and the total elapsed time is displayed
