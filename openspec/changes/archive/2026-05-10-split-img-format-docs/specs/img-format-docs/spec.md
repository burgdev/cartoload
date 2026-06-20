## ADDED Requirements

### Requirement: IMG Format documentation split into focused pages
The IMG Format documentation SHALL be organized into separate pages under `docs/img-format/`, each covering one logical area of the Garmin raster IMG binary format.

#### Scenario: Reader navigates to a specific topic
- **WHEN** a reader opens the IMG Format section in the sidebar
- **THEN** they see individual pages for: Overview, Header & FAT, GMP Container, Tile Storage, TRE Sections, Vector Reference, Tools & Resources

#### Scenario: Cross-references between pages resolve correctly
- **WHEN** a page references another IMG Format page (e.g., tile-storage links to tre-sections)
- **THEN** the link resolves to the correct page and anchor

### Requirement: Overview page links to all sub-pages
The `overview.md` page SHALL contain a section listing all sub-pages with brief descriptions, replacing the previous "Further Reading" links to `detailed-spec.md`.

#### Scenario: Reader finds sub-page from overview
- **WHEN** a reader opens the IMG Format overview page
- **THEN** they see links to Header & FAT, GMP Container, Tile Storage, TRE Sections, and Vector Reference pages

### Requirement: All content from detailed-spec.md is preserved
No technical content from the original `detailed-spec.md` SHALL be lost during the split. All sections, tables, field references, and examples must appear in one of the new pages.

#### Scenario: Verify content completeness
- **WHEN** the old `detailed-spec.md` is compared against the union of all new pages
- **THEN** every section, table, and paragraph from the original is present in exactly one new page

### Requirement: Nav configuration lists all IMG Format pages
The `zensical.toml` nav configuration SHALL list all 7 IMG Format pages as children of the "IMG Format" nav group.

#### Scenario: Docs build succeeds with new nav
- **WHEN** `zensical build` runs with the updated nav configuration
- **THEN** the build succeeds and all nav links resolve to valid pages
