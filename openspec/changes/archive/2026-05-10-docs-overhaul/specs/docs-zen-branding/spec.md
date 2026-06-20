## ADDED Requirements

### Requirement: Zensical site branding with logo
The zensical configuration SHALL set a project logo in the site header using the cartoload logo from `assets/logo/`.

#### Scenario: User views documentation site header
- **WHEN** a user visits any documentation page
- **THEN** the cartoload logo appears in the site header

### Requirement: Zensical site favicon
The zensical configuration SHALL set a favicon using `assets/logo/favicon.svg`.

#### Scenario: Browser displays favicon
- **WHEN** a user opens the documentation site in a browser
- **THEN** the cartoload favicon appears in the browser tab

### Requirement: Zensical color palette matches design system
The zensical configuration SHALL use colors from the cartoload Alpine green design system:
- Primary/accent: `#6A9E7A` (Fern) / `#4E7A5F` (Forest)
- Light mode background: `#F5F2EC` (Parchment)
- Dark mode background: `#131512` (Dark BG)

#### Scenario: Light mode colors
- **WHEN** the documentation site is viewed in light mode
- **THEN** the header, links, and accent elements use Alpine green tones from the design system

#### Scenario: Dark mode colors
- **WHEN** the documentation site is viewed in dark mode
- **THEN** the background uses dark mode colors from the design system and accents remain Alpine green

### Requirement: Light/dark mode toggle
The zensical configuration SHALL enable a light/dark mode toggle so users can switch between color schemes.

#### Scenario: User switches color mode
- **WHEN** a user clicks the color mode toggle
- **THEN** the site switches between light and dark color schemes

### Requirement: Logo and favicon assets in docs directory
The logo and favicon files SHALL be copied into `docs/assets/` so zensical can reference them relative to the docs directory.

#### Scenario: Zensical build finds assets
- **WHEN** zensical builds the documentation
- **THEN** it successfully resolves the logo and favicon paths without errors

### Requirement: External ignored directory excluded from build
The `external_ignored/` directory in `docs/` SHALL NOT appear in the generated site output.

#### Scenario: Build output does not contain external references
- **WHEN** zensical builds the documentation
- **THEN** no page is generated for content in `external_ignored/`
