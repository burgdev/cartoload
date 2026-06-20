## Why

Analysis scripts for the Garmin IMG binary format live in `scripts/` as standalone files with hardcoded paths and no CLI integration. Five one-off polyline preamble exploration scripts are obsolete. The main `img_analysis.py` parser already covers most of what `gmt -i` does — integrating it into the CLI provides a native `gmt` replacement for read-only inspection.

## What Changes

- Move the core IMG parser (`IMGParser` class) from `scripts/img_analysis.py` into `src/cartoload/analysis/` as a reusable package module
- Add two CLI commands under `cartoload analyze img`:
  - `info` — full IMG file analysis, replaces `gmt -i` for read-only inspection. Accepts flags: `--subfile`, `--hex`, `--dump`, `--list`, `--all`, `--raw-offset`, `--raw-size`, `--rgn2`, `--segments`
  - `compare` — side-by-side comparison of two IMG files (RGN headers and RGN2 data)
- Delete five obsolete polyline preamble exploration scripts (phases 1-5)
- Delete all migrated scripts and remove the `scripts/` directory

## Capabilities

### New Capabilities
- `cli-analyze-img`: CLI commands for analyzing Garmin IMG binary files — `info` for inspection (with RGN2 and segment flags), `compare` for side-by-side diff. Replaces `gmt -i` for read-only use.

### Modified Capabilities
<!-- No existing spec-level behavior changes -->

## Impact

- New module: `src/cartoload/analysis/` (package with parser and analysis utilities)
- Modified: `src/cartoload/cli.py` (add `analyze` group)
- New: `src/cartoload/cli_analyze.py` (analyze subcommands)
- Deleted: 9 scripts, entire `scripts/` directory
- No breaking changes to existing CLI commands
