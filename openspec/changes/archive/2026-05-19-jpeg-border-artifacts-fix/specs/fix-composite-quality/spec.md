## MODIFIED Requirements

### Requirement: Composite layer respects quality parameter
The build pipeline SHALL apply the `--quality` CLI parameter exclusively during the final IMG write step (`_reencode_jpeg()`). All intermediate pipeline stages (warp, compositing, GeoTIFF reading) SHALL encode tiles at quality 85.

#### Scenario: Quality parameter reduces composite IMG file size
- **WHEN** a composite layer is built with `--quality 30`
- **THEN** the resulting IMG file size SHALL be comparable to a single-layer build with the same quality setting (not 2-3x larger)

#### Scenario: All intermediate encodings use high quality
- **WHEN** tiles are processed through warp, compositing, or GeoTIFF reading
- **THEN** each intermediate JPEG encoding SHALL use quality 85 regardless of the `--quality` CLI flag

#### Scenario: Quality applied once at final write
- **WHEN** tiles are written to the IMG file
- **THEN** the target quality SHALL be applied exactly once in `_reencode_jpeg()`, after all intermediate processing is complete

#### Scenario: Default quality when not specified
- **WHEN** a build is run without `--quality`
- **THEN** the pipeline SHALL use quality 85 as default (existing behavior)
