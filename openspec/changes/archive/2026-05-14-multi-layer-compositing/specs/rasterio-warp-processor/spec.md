## MODIFIED Requirements

### Requirement: In-process tile reprojection via rasterio

The system SHALL reproject tiles from source CRS to EPSG:4326 using rasterio's `reproject()` function in-process, without spawning external processes. Output SHALL be JPEG bytes produced via PIL (Pillow) encoding with the specified quality level. When the source CRS matches the target CRS, raw JPEG bytes SHALL be passed through without decoding or re-encoding.

#### Scenario: EPSG:3857 to EPSG:4326 reprojection

- **WHEN** a source tile is in EPSG:3857 and the target CRS is EPSG:4326
- **THEN** the system SHALL open the source JPEG with rasterio, compute the target transform via `calculate_default_transform`, warp using `reproject()` with bilinear resampling into a numpy array, and encode the output to JPEG bytes using PIL's `Image.save(format='JPEG', quality=N)` with the configured quality and `optimize=True`
- **AND** no TIFF intermediate file SHALL be created on disk
- **AND** the output file size SHALL reflect the specified quality level

#### Scenario: Source CRS matches target CRS

- **WHEN** the source CRS is already EPSG:4326
- **THEN** the system SHALL read the raw JPEG bytes from cache and pass them through without decoding or re-encoding
- **AND** no rasterio warp operation SHALL occur

#### Scenario: Quality parameter applied during warp output

- **WHEN** the user specifies `--quality 50` and reprojection is needed
- **THEN** the JPEG output SHALL be encoded at quality=50 using PIL
- **AND** the output file size SHALL be approximately 50% smaller than quality=85 encoding for the same tile

#### Scenario: PNG tile reprojection for compositing

- **WHEN** a source tile is a PNG file in EPSG:3857 and reprojection is needed for compositing
- **THEN** the system SHALL open the PNG with rasterio (preserving all bands including alpha), warp to EPSG:4326, and return the result as a PIL Image in RGBA mode
- **AND** the alpha channel SHALL be preserved through reprojection
- **AND** no JPEG encoding SHALL occur at this stage (the RGBA image is passed to the compositor)

## ADDED Requirements

### Requirement: PNG tile reprojection support

The warp processor SHALL support PNG input tiles in addition to JPEG, preserving the alpha channel during reprojection for use in compositing.

#### Scenario: PNG with alpha channel from EPSG:3857

- **WHEN** a PNG tile with an alpha channel (RGBA) needs reprojection from EPSG:3857 to EPSG:4326
- **THEN** rasterio SHALL read all 4 bands (R, G, B, A), warp all bands together, and produce an RGBA output
- **AND** the alpha channel in the output SHALL correctly reflect the original transparency after reprojection

#### Scenario: PNG without alpha channel

- **WHEN** a PNG tile has only 3 bands (RGB, no alpha)
- **THEN** the system SHALL treat it as fully opaque (alpha = 255) during reprojection
- **AND** the output SHALL be RGBA with a fully opaque alpha channel
