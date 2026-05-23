## 1. Add WMTS pre-fetch to unified pipeline download stage

- [x] 1.1 In `unified_pipeline.py`, after calling `provider.download()` for a WmtsProvider, get the underlying `WMTSDownloader` and call `download_grid()` for each zoom level in the layer's bounds (only when `not no_download`)
- [x] 1.2 Ensure the download stage prints the "Layer N/M: downloading..." message BEFORE `download_grid()` starts (so it appears above the Rich progress bar)

## 2. Verify and test

- [x] 2.1 Run `just check` and `just check types` to verify formatting, linting, and type correctness
- [x] 2.2 Run `just test` to verify all tests pass
- [ ] 2.3 Manual test: run the switzerland build command and verify download progress bars appear (user-verified)
