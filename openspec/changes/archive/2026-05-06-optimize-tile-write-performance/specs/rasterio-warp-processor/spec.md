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
