## 1. Remove prettier from pre-commit config

- [x] 1.1 Remove the `mirrors-prettier` repo block from `.pre-commit-config.yaml`
- [x] 1.2 Verify `check-json` hook is present in `.pre-commit-config.yaml` (add if missing)
- [x] 1.3 Run `pre-commit run --all-files` to confirm no hooks reference prettier and all remaining hooks pass

## 2. Verify

- [x] 2.1 Run `just check` and confirm the full check suite passes without prettier
