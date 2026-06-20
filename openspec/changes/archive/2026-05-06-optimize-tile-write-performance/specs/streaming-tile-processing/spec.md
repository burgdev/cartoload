## MODIFIED Requirements

### Requirement: Stream tiles directly from cache as JPEG bytes

When the source CRS matches the target CRS (EPSG:4326), the system SHALL read tiles from cache and re-encode them at the configured quality level before writing to the IMG file. When reprojection is needed, the system SHALL warp in-process via rasterio and encode to JPEG at the configured quality using PIL. The streaming writer SHALL use a persistent executor across all batches and a batch size of 5000 tiles.

#### Scenario: CRS match — quality re-encoding

- **WHEN** a source tile is already in EPSG:4326 and the user specifies `--quality 50`
- **THEN** the system SHALL decode the cached JPEG, re-encode it at quality=50 using PIL, and write the re-encoded bytes to the IMG file
- **AND** the output file size SHALL reflect the specified quality level

#### Scenario: CRS match — high quality passthrough

- **WHEN** a source tile is already in EPSG:4326 and the user specifies `--quality 95` (at or above typical server quality)
- **THEN** the system SHALL decode the cached JPEG and re-encode it at quality=95
- **AND** the output SHALL be visually indistinguishable from the source

#### Scenario: Reprojection needed — quality applied via PIL

- **WHEN** a source tile is in EPSG:3857 and needs reprojection to EPSG:4326
- **THEN** the system SHALL warp the tile in-process using rasterio and encode JPEG bytes via PIL at the configured quality
- **AND** no TIFF file SHALL be written to disk at any point

#### Scenario: Quality default preserves existing behavior

- **WHEN** the user does not specify `--quality` (default 85)
- **THEN** the system SHALL re-encode tiles at quality=85
- **AND** output sizes SHALL be comparable to the current behavior since SwissTopo serves tiles at approximately Q85

### Requirement: Batch I/O for LBL28 offset writes

The system SHALL write all LBL28 image index offsets as a single buffered write operation rather than individual per-tile writes.

#### Scenario: LBL28 offsets written as single buffer

- **WHEN** the streaming writer has accumulated all LBL28 offsets for a GMP subfile
- **THEN** the system SHALL pre-allocate a bytearray, pack all offsets using `struct.pack_into`, and write the entire buffer with a single `f.write()` call
- **AND** the number of `f.write()` calls for LBL28 SHALL be exactly 1 per GMP subfile

### Requirement: Inline JPEG size tracking during LBL29 streaming

The system SHALL track actual JPEG sizes inline during the LBL29 streaming loop, alongside LBL28 offsets, to simplify the RGN2 jpeg_size fixup pass.

#### Scenario: JPEG sizes tracked inline

- **WHEN** the streaming writer writes a tile's JPEG data to LBL29
- **THEN** the system SHALL append `len(jpeg_data)` to a `jpeg_sizes` list alongside the LBL28 offset
- **AND** the `_fixup_rgn2_jpeg_sizes` function SHALL receive `jpeg_sizes` directly instead of computing sizes from LBL28 offset differences

### Requirement: Increased batch size for tile processing

The system SHALL use a batch size of 5000 tiles (up from 500) for streaming LBL29 writes, bounding per-batch memory to approximately 60 MB.

#### Scenario: Batch size is 5000

- **WHEN** the streaming writer processes tiles
- **THEN** it SHALL process up to 5000 tiles per batch
- **AND** per-batch memory SHALL not exceed ~60 MB (5000 tiles × ~12 KB average JPEG)
