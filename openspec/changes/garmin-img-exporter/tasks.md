## 1. BaseExporter Interface

- [ ] 1.1 Finalize `BaseExporter` in `src/cartoload/exporters/base.py` with abstract methods `export(raster_dataset, layer_config, output_path) -> list[Path]` and `validate(output_path) -> bool`, plus `name` property
- [ ] 1.2 Ensure `BaseExporter` is properly registered as an ABC with `@abstractmethod` decorators and raises `TypeError` on incomplete subclass instantiation

## 2. IMG Header Writer

- [ ] 2.1 Implement `IMGHeaderWriter` class (or header-writing methods on `GarminImgExporter`) that accepts an `IMGHeader` dataclass and writes the binary header: magic bytes, version, creation timestamp, map name (attribution), and subfile directory
- [ ] 2.2 Implement two-pass layout computation: first pass calculates subfile sizes and assigns byte offsets, second pass writes the header with correct offsets
- [ ] 2.3 Write unit test that creates a minimal `IMGHeader`, serializes it, and verifies the magic bytes and field positions match the format spec

## 3. Subfile Writer

- [ ] 3.1 Implement `SubfileWriter` that accepts a `SubfileHeader` and tile data, and writes a complete subfile section (header + tile blocks) to the output stream
- [ ] 3.2 Implement subfile header serialization: tile dimensions, geographic bounds in Garmin coordinate units (degrees * 2^31 / 180), zoom level, and tile count
- [ ] 3.3 Write unit test that creates a `SubfileHeader`, serializes it, and verifies all fields are at the correct byte offsets

## 4. Tile Encoder

- [ ] 4.1 Implement `TileEncoder` that converts raw pixel data (numpy array from GeoTIFF) into the Garmin tile format: tile header (width, height, colour depth) + bit-packed pixel payload
- [ ] 4.2 Handle edge tiles where the geographic boundary produces tiles smaller than the standard 256x256 dimension — pad or truncate per the format specification
- [ ] 4.3 Write unit test that encodes a 256x256 test tile, decodes it back, and verifies pixel data integrity
- [ ] 4.4 Write unit test that encodes an edge tile (e.g., 128x200) and verifies the tile header reflects the actual dimensions

## 5. Multi-Resolution Pyramid

- [ ] 5.1 Implement pyramid generation that accepts a list of zoom levels and produces one subfile per zoom level, ordered from lowest to highest resolution
- [ ] 5.2 Compute the tile grid for each zoom level based on the geographic bounds and the zoom level's tile size (covering the full extent at each resolution)
- [ ] 5.3 Write unit test that creates a pyramid with zoom levels [10, 11, 12] and verifies each subfile has the correct zoom level, tile count, and consistent bounds

## 6. Attribution Embedding

- [ ] 6.1 Implement attribution handling: read `LayerConfig.attribution`, fall back to source attribution if not set, encode into the IMG header map name field
- [ ] 6.2 Implement character set handling for the Garmin-specific extended character set as documented in the format spec
- [ ] 6.3 Implement truncation with warning log when attribution exceeds the map name field's maximum length
- [ ] 6.4 Write unit test that verifies attribution appears in the serialized header and that truncation produces a warning

## 7. Size Limit Handling

- [ ] 7.1 Implement pre-write size accounting: compute encoded tile size before writing, assert it does not exceed 3.5 MB (3,670,016 bytes)
- [ ] 7.2 Implement tile cell splitting: when a tile exceeds 3.5 MB, split into multiple subfile entries sharing the same geographic bounds, and update the draw order table to reference all parts
- [ ] 7.3 Implement 4 GB file limit handling: track cumulative output size, and when it would exceed 4 GB, split along tile row boundaries into a new `.img` file with its own header and subfile directory
- [ ] 7.4 Implement consistent naming for split files (numeric suffix: `name_1.img`, `name_2.img`)
- [ ] 7.5 Write unit test that verifies a tile exceeding 3.5 MB is correctly split and both parts are under the limit
- [ ] 7.6 Write unit test that verifies output exceeding 4 GB is split into multiple files each under 4 GB

## 8. GarminImgExporter Integration

- [ ] 8.1 Implement `GarminImgExporter.export()` in `src/cartoload/exporters/garmin_img.py` that orchestrates the full pipeline: compute layout, write header, write subfiles (tile encoding + pyramid), handle size limits, and return list of output paths
- [ ] 8.2 Implement chunk-based streaming write: do not hold the entire file in memory; write subfiles sequentially using the pre-computed offsets
- [ ] 8.3 Implement `GarminImgExporter.validate()` that runs `gmt -i -v` on the output file, raises on error, and logs a warning if `gmt` is not available

## 9. Testing

- [ ] 9.1 Create `tests/test_exporter_garmin_img.py` with unit tests for IMG header serialization, subfile serialization, tile encoding, pyramid generation, attribution, and size limit handling
- [ ] 9.2 Create integration test that writes a small but complete `.img` file (2-3 zoom levels, small geographic extent) and verifies it passes `gmt -i -v` (skip if `gmt` not available)
- [ ] 9.3 Create binary comparison test: if a known-good `.img` file is available, compare the header and subfile structures byte-for-byte against the writer output
- [ ] 9.4 Mark all tests requiring `gmt` or GDAL system dependencies with `@pytest.mark.gmt` / `@pytest.mark.gdal` so they can be skipped in CI

## 10. Device Testing

- [ ] 10.1 Produce a test `.img` file from swisstopo data (small area, e.g., Zurich city centre, zoom levels 12-14) and load it on a Garmin Fenix watch to verify rendering
- [ ] 10.2 Produce a test `.img` file and load it on a Garmin Oregon or GPSMAP handheld to verify rendering on a different device family
- [ ] 10.3 Test a split file scenario (> 4 GB output) on device to verify both files load and cover the full extent without gaps
- [ ] 10.4 Document device test results and any format corrections needed in `docs/exporters/garmin-img.md`
