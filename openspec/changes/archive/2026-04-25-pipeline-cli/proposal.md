## Why

The individual components (config loader, downloader, processor, exporter) are built in isolation. This change wires them together into a working end-to-end pipeline and makes the `build`, `download`, and `split` CLI commands functional. This is step 4 in the SPEC.md implementation order — after the WMTS downloader and Garmin IMG exporter work individually.

## What Changes

- Implement the pipeline orchestration in `pipeline.py`: `build_layer()` loads config → selects downloader → downloads tiles → processes raster → exports to `.img`
- Implement the `build` CLI command: parse `--sources`, `--layers`, `--layer`, `--exporter`, `--bounds`, `--zoom`, `--output-dir`, `--cache-dir`, `--no-download`, `--quality` flags and invoke the pipeline
- Implement the `download` CLI command: download only (no build), respecting `--no-download`
- Implement the `split` CLI command: use `gmt` to split oversized `.img` files into region files when they exceed 4 GB
- Add end-to-end integration test: config → download (mocked) → process (mocked or small real data) → export → validate `.img`

## Capabilities

### New Capabilities

- `pipeline-orchestrator`: End-to-end orchestration of the download → process → export pipeline, selectable by source type and exporter
- `cli-commands`: Functional `build`, `download`, and `split` CLI commands that accept all documented flags

### Modified Capabilities

- `package-skeleton`: `cli.py` stubs become real implementations; `pipeline.py` stub becomes real implementation

## Impact

- **Code**: `src/cartoload/pipeline.py`, `src/cartoload/cli.py` go from stubs to working implementations
- **Dependencies**: No new dependencies — composes existing components
- **Tests**: Integration tests in `tests/test_pipeline.py` and `tests/test_cli.py`
- **Milestone**: After this change, `just build-ch-25k` should produce a valid Garmin `.img` file (assuming real data access)
