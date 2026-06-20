## Why

The documentation is a mix of user guides, internal planning docs, and binary format specs. Several pages read like engineering research notes rather than user-facing documentation. The zensical site build lacks proper branding (no logo, favicon, or design-system colors). The nav includes placeholder pages that say "Not yet implemented."

## What Changes

- Restructure documentation into clear sections: Home, Getting started, Guides, Configuration, IMG Format, CLI Reference, API Reference
- Rewrite the Garmin IMG exporter page as a two-level document: a high-level overview for users, with a link to the detailed binary format specification
- Clean up the IMG resources page: remove implementation planning sections, keep curated tool/link reference
- Move `cartoload analyze` docs from the format spec into a Guides page
- Remove swisstopo IMG file references (unclear provenance); swisstopo as a source example is fine
- Remove placeholder pages ("Not yet implemented") from nav
- Fix zensical.toml: add logo, favicon, custom color palette (Alpine green design system), dark mode
- Copy logo/favicon assets into docs/ for zensical to use
- Exclude `external_ignored/` directory from the zensical build

## Capabilities

### New Capabilities
- `docs-structure`: New documentation navigation structure and page organization
- `docs-zen-branding`: Zensical site branding with design-system colors, logo, and favicon

### Modified Capabilities
<!-- No spec-level behavior changes — this is documentation and build config only -->

## Impact

- All files in `docs/` (markdown content, zensical.toml)
- Static assets copied into `docs/assets/`
- No code changes, no API changes
