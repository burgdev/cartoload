## MODIFIED Requirements

### Requirement: Unified config file format
A config file SHALL be a YAML document that may contain any combination of the following top-level keys: `includes`, `sources`, `layers`, `bounds`, `targets`, `products`, `settings`. All sections are optional. A file containing only `sources:` is valid.

#### Scenario: Config file with all sections
- **WHEN** a config file contains `includes`, `sources`, `layers`, `targets`, `bounds`, `products`, and `settings` keys
- **THEN** the loader SHALL parse all sections and return them as a unified result

#### Scenario: Config file with only sources
- **WHEN** a config file contains only a `sources` key (no `layers`, `bounds`, `targets`, or `products`)
- **THEN** the loader SHALL return the sources with empty other sections

#### Scenario: Empty config file
- **WHEN** a config file contains no recognized top-level keys
- **THEN** the loader SHALL return empty sources, empty layers, empty targets, empty products, no bounds, and default settings
