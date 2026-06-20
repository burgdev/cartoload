## Why

Running pre-commit with prettier causes the full PC to freeze, making the editor (nvim) unresponsive and sometimes crashing it. Prettier is used only for YAML, Markdown, and JSON formatting — a job that lighter, faster alternatives can handle without pulling in the Node.js runtime that causes the resource issues.

## What Changes

- Remove the `mirrors-prettier` hook from `.pre-commit-config.yaml`
- Replace prettier's YAML/JSON formatting with `check-yaml` and `check-json` (already present or available via pre-commit-hooks) for syntax validation only
- Replace prettier's Markdown formatting with `mdformat` (via pre-commit, pure Python, no Node.js) or remove Markdown formatting from pre-commit entirely (ruff already handles Python, and Markdown formatting is low-value in a pre-commit hook)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — this is a tooling/CI change, no spec-level behavior is affected)_

## Impact

- `.pre-commit-config.yaml` — remove prettier hook, optionally add mdformat
- Developer experience — faster pre-commit runs, no PC freezes, no nvim crashes
- No impact on runtime behavior, API, or exported artifacts
