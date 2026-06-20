## Context

The project uses pre-commit with three hook groups: standard pre-commit-hooks, ruff (Python linting/formatting), and prettier (YAML/Markdown/JSON formatting). Prettier is the only hook that requires a Node.js runtime. When it runs, it consumes excessive resources, freezing the system and crashing the user's editor.

The project is a Python package (`src/cartoload/`). Python formatting is already fully covered by ruff. Prettier only formats non-Python files (YAML, Markdown, JSON).

## Goals / Non-Goals

**Goals:**
- Eliminate the prettier-induced system freeze and editor crashes
- Maintain basic validation of YAML/JSON files via existing pre-commit-hooks
- Keep pre-commit fast and lightweight

**Non-Goals:**
- Adding a new Markdown auto-formatter (mdformat or similar) — not needed now, can be added later if desired
- Changing Python formatting (ruff stays as-is)
- Changing any runtime behavior

## Decisions

### 1. Remove prettier entirely (no replacement formatter)

**Decision**: Remove the `mirrors-prettier` hook without replacing it with another formatter.

**Rationale**:
- `check-yaml` and `check-json` from pre-commit-hooks already validate syntax
- Markdown formatting is low-value in pre-commit for a Python project
- Adding mdformat or similar would introduce a new dependency for marginal benefit
- The core problem (Node.js resource usage) is solved completely by removal

**Alternatives considered**:
- `mdformat` (pre-commit-mdformat): Pure Python, no Node.js. Viable but unnecessary — no one has requested Markdown formatting, and `prettier` wasn't intentionally added for that purpose.
- `djlint` / `biome` / `dprint`: All heavier than needed for this use case.

## Risks / Trade-offs

- **Risk**: YAML/Markdown/JSON files may have inconsistent formatting across contributors → **Mitigation**: Existing `check-yaml`/`check-json` catch syntax errors; formatting consistency is low priority for config/doc files. If needed later, a lightweight formatter can be added.
- **Risk**: Existing files formatted by prettier may look different from new edits → **Mitigation**: Acceptable trade-off. No user-facing impact.
