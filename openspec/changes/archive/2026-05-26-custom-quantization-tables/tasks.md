## 1. Research and analysis

- [x] 1.1 Extract and document IOM reference quantization tables (luminance + chrominance)
- [x] 1.2 Generate scaled variants for all quality levels using Pillow's quality scaling formula
- [x] 1.3 Benchmark: encode 30 tiles with IOM vs default at quality 16 and 20

## 2. Visual QA

- [x] 2.1 Generate comparison tiles from cache at quality 16 and 20 (30 tiles, zoom 14-16)
- [ ] 2.2 Identify the best preset(s) that provide significant size savings without unacceptable visual degradation
- [ ] 2.3 Test selected preset(s) on Garmin GPS device

## 3. Implementation

- [x] 3.1 Add IOM quantization tables and `iom_qtables_for_quality()` / `get_qtables()` to `garmin_img_writer.py`
- [x] 3.2 Add `--qtables` CLI option to the build command (accepts "iom" or "default")
- [x] 3.3 Add optional `jpeg_qtables` field to layer config settings
- [x] 3.4 Modify `_reencode_jpeg` to accept and use custom qtables when provided
- [x] 3.5 Pass qtables through the export pipeline (CLI → config → exporter → writer)

## 4. Verify

- [x] 4.1 Run existing test suite to ensure no regressions (892 tests pass)
- [ ] 4.2 Build full map with selected preset and compare file size vs default
- [ ] 4.3 Verify output works on GPS device
