## 1. Create analysis package

- [x] 1.1 Create `src/cartoload/analysis/__init__.py` re-exporting IMGParser
- [x] 1.2 Move IMGParser class from `scripts/img_analysis.py` to `src/cartoload/analysis/img_parser.py` (remove hardcoded paths, keep all parsing logic as-is)
- [x] 1.3 Extract RGN2 analysis functions from `scripts/analyze_rgn2.py` and `scripts/rgn2_segmented_analysis.py` into `src/cartoload/analysis/rgn2.py` (remove hardcoded paths, accept data as parameters)
- [x] 1.4 Extract comparison functions from `scripts/rgn2_deep_analysis.py` into `src/cartoload/analysis/compare.py` (remove hardcoded paths, accept paths as parameters)

## 2. Add CLI commands

- [x] 2.1 Create `src/cartoload/cli_analyze.py` with `img` Click group and `info`/`compare` subcommands
- [x] 2.2 Implement `info` command with options: `--subfile`, `--hex`, `--dump`, `--list`, `--all`, `--raw-offset`, `--raw-size`, `--rgn2`, `--segments`
- [x] 2.3 Implement `compare` command accepting two IMG file paths
- [x] 2.4 Register `analyze` group in `src/cartoload/cli.py`

## 3. Cleanup

- [x] 3.1 Delete all 5 polyline preamble scripts from `scripts/`
- [x] 3.2 Delete the 4 migrated scripts from `scripts/`
- [x] 3.3 Remove `scripts/` directory

## 4. Documentation

- [x] 4.1 Add `analyze` section to `docs/cli.md` documenting `info` and `compare` commands with all flags and usage examples
- [x] 4.2 Add `analyze img` to AGENTS.md as the recommended way to inspect IMG files (replaces `gmt -i` for read-only analysis)

## 5. Verify

- [x] 5.1 Run `just check` and `just check types` — all pass
- [x] 5.2 Run `cartoload analyze img --help` — shows info and compare
- [x] 5.3 Run `cartoload analyze img info tests/data/garmin_samples/IOM.img --list` — lists subfiles
