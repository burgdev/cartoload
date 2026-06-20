## Why

The cartoload CLI currently only supports long-form parameters (e.g. `--sources`, `--layer`). Short flags reduce typing and improve usability for interactive use.

## What Changes

- Add short flag aliases to all CLI parameters across `build`, `download`, `list`, and `split` commands.
- Mapping: `-S`/`--sources`, `-L`/`--layers`, `-l`/`--layer`, `-e`/`--exporter`, `-b`/`--bbox`, `-x`/`--lng`, `-y`/`--lat`, `-W`/`--width`, `-H`/`--height`, `-z`/`--zoom`, `-o`/`--output-dir`, `-c`/`--cache-dir`, `-f`/`--force`, `-q`/`--quality`. The `--no-download` flag gets no short form.

## Capabilities

### New Capabilities

- `cli-short-params`: Short flag aliases for all CLI parameters.

### Modified Capabilities

_(none — no existing spec-level behavior changes)_

## Impact

- `src/cartoload/cli.py`: Add short flag strings to `@click.option` decorators.
- `tests/test_cli.py`: Update any tests that construct CLI invocations to verify short flags work.
