## ADDED Requirements

### Requirement: Source and Provider registry
The system SHALL provide a registry pattern for Sources and LayerProviders, allowing new types to be added without modifying core pipeline code.

#### Scenario: Register a new source
- **WHEN** a module calls `register_source("ftp", FtpSource)`
- **THEN** the system SHALL be able to resolve sources with `type: ftp` to `FtpSource`

#### Scenario: Register a new provider
- **WHEN** a module calls `register_provider("geojson", GeojsonProvider)`
- **THEN** the system SHALL be able to resolve layers with `format: geojson` to `GeojsonProvider`

#### Scenario: Unknown format
- **WHEN** a layer has a `format` value not in the provider registry
- **THEN** the system SHALL raise a clear error listing available formats

#### Scenario: Unknown source type
- **WHEN** a source has a `type` value not in the source registry and auto-detection fails
- **THEN** the system SHALL raise a clear error listing available source types

### Requirement: Source auto-detection
Each Source class SHALL implement a `can_handle(url) -> bool` class method. The system SHALL try registered sources in order to auto-detect the source method when no explicit `type` is provided.

#### Scenario: STAC URL detected
- **WHEN** a source URL contains `/collections/` or `/stac/` in the path
- **THEN** `StacSource.can_handle()` SHALL return `True`

#### Scenario: Local path detected
- **WHEN** a source URL starts with `./`, `../`, `/`, or has no URL scheme
- **THEN** `PathSource.can_handle()` SHALL return `True`

#### Scenario: WMTS URL detected
- **WHEN** a source URL contains tile coordinate variables (`${x}`, `${y}`, `${z}`)
- **THEN** `WmtsSource.can_handle()` SHALL return `True`

#### Scenario: Explicit type overrides auto-detection
- **WHEN** a source config has an explicit `type` field
- **THEN** the system SHALL use that type regardless of URL patterns

### Requirement: Source interface
Each Source SHALL implement `download(layer_config)` and `is_cached(cache_path)`. Sources handle fetching data to cache and managing cache validity via metadata sidecars.

#### Scenario: Download with caching
- **WHEN** `source.download(layer_config)` is called
- **THEN** the source SHALL check cache first, skip if valid, download if stale or missing

#### Scenario: Cache validity check
- **WHEN** `source.is_cached(cache_path)` is called
- **THEN** the source SHALL return `True` if the file exists AND a metadata sidecar exists, OR if a processor completion marker exists

### Requirement: Provider interface
Each LayerProvider SHALL implement `download()`, `prepare()`, `to_raster(x, y, z)`, and `supported_extensions`. The provider delegates downloading to its source and handles format-specific processing.

#### Scenario: Provider delegates to source
- **WHEN** `provider.download()` is called
- **THEN** the provider SHALL call `source.download()` with format-aware filtering (e.g., asset type selection for STAC)

#### Scenario: GeotiffProvider supported extensions
- **WHEN** `GeotiffProvider.supported_extensions` is accessed
- **THEN** it SHALL return `[".tif", ".tiff"]`

#### Scenario: GpkgProvider supported extensions
- **WHEN** `GpkgProvider.supported_extensions` is accessed
- **THEN** it SHALL return `[".gpkg"]`

#### Scenario: Auto-unzip of compressed assets
- **WHEN** a source downloads a `.zip` file containing a format-matching asset (e.g., `.gpkg` inside `.zip`)
- **THEN** the provider SHALL automatically extract the relevant file from the archive
