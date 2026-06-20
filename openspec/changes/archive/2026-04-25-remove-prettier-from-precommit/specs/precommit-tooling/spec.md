## ADDED Requirements

### Requirement: Pre-commit SHALL NOT use prettier

The pre-commit configuration SHALL NOT include the `mirrors-prettier` hook or any Node.js-based formatter.

#### Scenario: Pre-commit config has no prettier hook
- **WHEN** `.pre-commit-config.yaml` is inspected
- **THEN** no hook referencing `prettier` or `mirrors-prettier` SHALL be present

### Requirement: YAML and JSON validation SHALL remain via pre-commit-hooks

The pre-commit configuration SHALL continue to validate YAML and JSON files using `check-yaml` and `check-json` from the standard pre-commit-hooks.

#### Scenario: YAML files are validated
- **WHEN** a YAML file with invalid syntax is committed
- **THEN** the `check-yaml` hook SHALL fail
