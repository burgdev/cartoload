## MODIFIED Requirements

### Requirement: Composite layer respects quality parameter
The build pipeline SHALL apply the `--quality` CLI parameter exclusively during the final IMG write step (`_reencode_jpeg()`). All intermediate pipeline stages (warp, compositing, GeoTIFF reading) SHALL encode tiles at quality 85.

Custom raster quantization tables (`--qtables raster`) SHALL be returned as unscaled base tables. The encoder (Pillow or cjpeg/mozjpeg) SHALL apply quality-based scaling to these base tables exactly once.

When cjpeg is used without custom qtables, it SHALL use `-quant-table 0` (Annex K tables) to match Pillow's default behavior.

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

#### Scenario: Raster qtables are not double-scaled
- **WHEN** `--qtables raster --quality 25` is specified and cjpeg is available
- **THEN** the custom tables SHALL be scaled by the quality parameter exactly once (in the encoder), producing output consistent with Pillow's encoding at the same quality

#### Scenario: cjpeg uses Annex K tables by default
- **WHEN** no custom qtables are provided and cjpeg is available
- **THEN** cjpeg SHALL use `-quant-table 0` (Annex K), producing output comparable to Pillow at the same quality level

## ADDED Requirements

### Requirement: Function name matches user-facing preset
The function `iom_qtables_for_quality` SHALL be renamed to `raster_qtables_for_quality` to match the `--qtables raster` CLI preset name.

#### Scenario: Function renamed
- **WHEN** code references the raster qtables function
- **THEN** it SHALL use the name `raster_qtables_for_quality`, not `iom_qtables_for_quality`
