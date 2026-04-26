## Context

Analysis scripts for the Garmin IMG binary format currently live in `scripts/` as standalone Python files. They import each other via `sys.path` hacks and have hardcoded file paths (e.g., `/home/tobias/kdrive/garmin/IOM.img`). The core `IMGParser` class in `scripts/img_analysis.py` is imported by most other scripts. The existing CLI (`src/cartoload/cli.py`) uses Click with a `main` group containing `build`, `download`, `split`, and `list` commands.

The `info` command already covers most of what `gmt -i` does (FAT, GMP, TRE, RGN, LBL parsing). The three RGN2-focused scripts (`analyze_rgn2.py`, `rgn2_segmented_analysis.py`, `rgn2_deep_analysis.py`) are different views of the same data — they collapse naturally into flags on `info` and a separate `compare` command.

## Goals / Non-Goals

**Goals:**
- Provide a native `gmt -i` replacement via `cartoload analyze img info`
- Collapse 4 scripts into 2 commands with flags (`info` + `compare`)
- Extract `IMGParser` into a reusable package module
- Remove hardcoded paths — all file paths come from CLI arguments
- Delete obsolete exploration scripts

**Non-Goals:**
- Replacing `gmt` write operations (splitting, merging) — that's the exporter's job
- Refactoring the IMGParser internals (move as-is, clean up later)
- Unit testing the analysis commands (they are developer tools for inspecting binary files)

## Decisions

### 1. Two commands: `info` + `compare` (not four subcommands)

**Decision:** `cartoload analyze img info <file> [flags]` and `cartoload analyze img compare <file1> <file2>`.

**Rationale:** The three RGN2 scripts are just different lenses on the same data:
- `analyze_rgn2.py` → `info --rgn2` (annotated hex dump + field annotations)
- `rgn2_segmented_analysis.py` → `info --segments` (split RGN2 by zoom level using TRE7)
- `rgn2_deep_analysis.py` → `compare` (side-by-side needs two files, so it stays separate)

This avoids command proliferation and keeps the CLI discoverable.

### 2. `info` replaces `gmt -i`

**Decision:** The `info` command should be the go-to for IMG inspection, covering what `gmt -i` does natively.

**Rationale:** `img_analysis.py` already parses FAT, GMP, TRE, RGN, LBL. With `--list`, `--hex`, `--dump`, `--all`, it covers the common inspection workflows. No need to shell out to `gmt` for read-only analysis.

### 3. Module layout: `src/cartoload/analysis/`

**Decision:** Create `src/cartoload/analysis/` with:
- `__init__.py` — re-exports IMGParser
- `img_parser.py` — IMGParser class (moved from `scripts/img_analysis.py`)
- `rgn2.py` — RGN2 analysis functions (from `analyze_rgn2.py` and `rgn2_segmented_analysis.py`)
- `compare.py` — comparison functions (from `rgn2_deep_analysis.py`)

**Rationale:** The parser is substantial (~500 lines). Keeping it in its own file avoids a giant module. RGN2 and comparison logic are extracted from their respective scripts.

### 4. CLI commands in separate file

**Decision:** Create `src/cartoload/cli_analyze.py` with the `img` Click group and its subcommands. Register the `analyze` group in `cli.py`.

**Rationale:** The main `cli.py` already has substantial code. Keeping analyze commands separate maintains organization.

### 5. Move as-is, don't refactor

**Decision:** Move the analysis logic with minimal changes — only remove hardcoded paths, adapt `print()` to Click's `click.echo()`.

**Rationale:** These are developer tools. Getting them accessible matters more than perfect API design.

## Risks / Trade-offs

- **Large module move** → The IMGParser is ~500 lines. Moving it in one chunk risks import breakage. Mitigation: move as-is first, then wire up CLI.
- **Hardcoded test data paths** → Scripts have hardcoded paths. These become CLI arguments instead.
- **info flag explosion** → Too many flags on `info` could make it unwieldy. Mitigation: `--rgn2` and `--segments` are the only new flags beyond what the script already had.
