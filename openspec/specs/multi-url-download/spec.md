## ADDED Requirements

### Requirement: Multiple URL templates per source

The system SHALL support multiple URL templates for a single source. When multiple URLs are configured, the downloader SHALL distribute tile requests across all URLs to parallelize downloads and respect per-host rate limits.

#### Scenario: Multiple URLs in config

- **WHEN** a source config specifies a list of URL templates
  ```yaml
  urls:
    - "https://server1.example.com/tile/{z}/{x}/{y}.jpeg"
    - "https://server2.example.com/tile/{z}/{x}/{y}.jpeg"
    - "https://server3.example.com/tile/{z}/{x}/{y}.jpeg"
  ```
- **THEN** the downloader SHALL distribute tile requests round-robin or randomly across the URLs
- **AND** each URL SHALL be treated as an independent endpoint for rate limiting purposes

#### Scenario: Single URL backward compatible

- **WHEN** a source config specifies a single `url` field (string, not list)
- **THEN** the downloader SHALL behave exactly as before — all tiles from the single URL
- **AND** no behavior change from the current single-URL implementation

### Requirement: Per-URL rate limiting

The system SHALL apply rate limits per URL rather than globally. This allows higher aggregate throughput when using multiple URLs from different servers.

#### Scenario: Three URLs with 150ms rate limit each

- **WHEN** three URLs are configured with a rate limit of 150ms
- **THEN** each URL SHALL have its own rate limiter allowing one request every 150ms
- **AND** the aggregate download rate SHALL be up to 3x the single-URL rate (subject to thread pool size)

#### Scenario: Mixed rate limits across URLs

- **WHEN** different URLs have different rate limits (via per-URL configuration)
- **THEN** each URL's rate limiter SHALL respect its configured delay
- **AND** the overall throughput SHALL be the sum of individual URL throughputs

### Requirement: Thread pool scaled to URL count

The default thread pool size SHALL scale with the number of configured URLs to maximize parallelism while respecting rate limits. The formula SHALL be `max(4, len(urls) * 2)`.

#### Scenario: Three URLs configured

- **WHEN** three URLs are configured and no explicit `max_threads` is set
- **THEN** the thread pool SHALL use `max(4, 3 * 2)` = 6 threads

#### Scenario: Explicit thread count overrides

- **WHEN** the user sets `max_threads: 12` in the source config
- **THEN** the thread pool SHALL use exactly 12 threads regardless of URL count

### Requirement: Graceful handling of URL failures

The downloader SHALL handle per-URL failures gracefully. If one URL returns errors, the downloader SHALL redistribute its pending tiles to the remaining healthy URLs.

#### Scenario: One URL returns 503

- **WHEN** URL 2 of 3 starts returning HTTP 503 errors
- **THEN** the downloader SHALL temporarily stop sending requests to URL 2
- **AND** tiles originally assigned to URL 2 SHALL be redistributed to URLs 1 and 3
- **AND** a warning SHALL be logged

#### Scenario: All URLs fail

- **WHEN** all configured URLs return errors for multiple consecutive attempts
- **THEN** the download SHALL fail with a clear error message indicating all URLs are unavailable
