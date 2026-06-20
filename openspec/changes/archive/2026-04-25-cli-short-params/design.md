## Context

The cartoload CLI uses Click with long-form `--option` parameters only. Adding short flags is a straightforward decorator-level change — no architectural or data model changes needed.

## Goals / Non-Goals

**Goals:**

- Add short flag aliases for every CLI parameter (except `--no-download`).
- Keep long forms unchanged so existing scripts and docs continue to work.

**Non-Goals:**

- Changing parameter names, types, or behavior.
- Adding new parameters.

## Decisions

- **Use Click's first positional argument for short flags** — Click natively supports `@click.option("-s", "--sources", ...)`. No custom code needed.
- **Mapping follows conventions** — `-S`/`-L` for plural config lists, `-l` for single layer, `-x`/`-y` for coordinates (GIS convention), standard letters for the rest.

## Risks / Trade-offs

- **Short flag collisions**: Unlikely — the chosen letters don't conflict with Click internals or each other across commands. Verified: `-f` already used for `--force`.
