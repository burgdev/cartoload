# AGENTS.md

Guidelines for AI coding agents working on cartoload.

## Workflow

- **Use OpenSpec for all tasks.** Propose changes via `/opsx:propose` (or `/openspec-propose`), then implement with `/opsx:apply`. Explore ideas with `/opsx:explore` before jumping in.
- **Ask for clarification** on anything that is not clear. Do not guess on ambiguous requirements.

## Tooling

- **uv** is the package manager. Use `uv sync`, `uv run`, `uv add` etc. instead of pip.
- Python 3.11+ required.

## Code Changes

- Run `just check` and `just check types` after finishing a session to verify formatting, linting, and type correctness.
- Keep tests passing: run `just test` before considering work done.

## Docs

- Read and keep the docs in `docs/` up to date when changing user-facing behavior.
- Project documentation is built with zensical and deployed to GitHub Pages.
- Some of the referenced sources are under `docs/external_ignored/` (ignored by git)

## Project Structure

- `src/cartoload/` - main package (installed as `cartoload`)
- `tests/` - pytest test suite
- `docs/` - documentation source (markdown)
- `openspec/` - change proposals, designs, specs, and tasks
- `examples/configs/` - example source and layer configs

## Context

- **Branches:** `develop` is the working branch, `main` is for releases.
- **Garmin IMG format:** This is a proprietary binary format with significant complexity. Before modifying any exporter code, read the existing specs and designs in `openspec/specs/` and any open changes in `openspec/changes/` to understand the format.
- **Inspecting IMG files:** Use `cartoload analyze img info <file>` to inspect Garmin IMG binary files. Key flags:
  - `--summary`/`-m` — concise overview (bounds, bitmap stats, encoding, map name)
  - `--section`/`-n` — show a single section (e.g. `--section TRE7`, `--section RGN2`)
  - `--limit` — max entries per section (default: 20, `0` = unlimited)
  - `--rgn2`/`-r` — annotated RGN2 analysis
  - `--segments`/`-g` — TRE7-based zoom level segmentation
  - `--hex <section>`/`-x` — raw hex dumps
  - `--list`/`-l` — list subfiles only
  - `--no-descriptions`/`-q` — hide section descriptions
  - `--no-color` — disable colored output (auto-disabled when piped)
  - Use `cartoload analyze img compare <file1> <file2>` for side-by-side comparison of two IMG files.
- Test command: Run this command for testing (important to use `-x`, `-y`, `-H` and `-W`):
   `cartoload build -S examples/configs/sources/swisstopo.yaml -L examples/configs/layers/switzerland.yaml  -l ch_basemap_test -y 46.93459 -x 7.51105 -W 5 -H 5 -f --preview --executor thread`

## Reference Source Code

- **mkgmap** (Java Garmin IMG writer): `~/git/tmp/mkgmap-r4924` — the definitive open-source reference for Garmin IMG format. Key packages: `uk.me.parabola.mkgmap.reader`, `uk.me.parabola.mkgmap.building`, `uk.me.parabola.mkgmap.general`, `uk.me.parabola.mkgmap.outputs`.
- **GPXSee** (C++ Garmin IMG reader): `~/git/tmp/GPXSee` — useful for understanding how IMG files are parsed. Key directories: `src/map/IMG`, `src/GPXSee` (main app).
- **QMapShack**:

## General Guidelines

### Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### Goal-Driven Execution

**Define success criteria. Loop until verified.**

Follow clearly the assigned OpenSpec tasks!

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
