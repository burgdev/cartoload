## ADDED Requirements

### Requirement: Documentation navigation structure
The documentation SHALL use the following navigation structure:

```
Home
Getting started
Guides
  Build a map
  Analyze IMG files
  Split large maps
Configuration
  Sources
  Layers
IMG Format
  Overview
  Detailed specification
  Tools & resources
CLI Reference
API Reference
```

#### Scenario: User navigates documentation
- **WHEN** a user views the documentation site
- **THEN** the sidebar navigation shows the structure above with all items clickable

### Requirement: Landing page content
The home page SHALL describe cartoload as a CLI tool and Python library for converting geodata into GPS device maps. It SHALL list key features without referencing specific sample files from unclear provenance.

#### Scenario: User reads the landing page
- **WHEN** a user visits the documentation home page
- **THEN** they see a description of cartoload, its key features, and installation instructions
- **AND** no references to swisstopo IMG sample files appear

### Requirement: Getting started guide
The getting started page SHALL provide a concrete walkthrough using example config files. Swisstopo as a source example config is acceptable.

#### Scenario: New user follows getting started
- **WHEN** a new user follows the getting started guide
- **THEN** they can install cartoload, configure a source and layer, and build their first map

### Requirement: Build a map guide
The Guides section SHALL include a "Build a map" page documenting the `cartoload build` workflow with common options and examples.

#### Scenario: User learns how to build a map
- **WHEN** a user reads the "Build a map" guide
- **THEN** they understand source config, layer config, and the build command with its key options

### Requirement: Analyze IMG files guide
The Guides section SHALL include an "Analyze IMG files" page documenting the `cartoload analyze img` commands (info, compare) with practical examples. This content SHALL be moved from the IMG format spec into this guide.

#### Scenario: User inspects an IMG file
- **WHEN** a user reads the "Analyze IMG files" guide
- **THEN** they understand how to use `cartoload analyze img info` and `compare` with common flags

### Requirement: IMG format overview page
The IMG Format section SHALL include an "Overview" page that explains the Garmin IMG format at a high level: what it is, raster vs vector, the file structure (header, FAT, GMP subfiles), and device compatibility. This page SHALL link to the detailed specification for readers who need binary-level detail.

#### Scenario: User wants to understand IMG format basics
- **WHEN** a user reads the IMG format overview
- **THEN** they understand what an IMG file is, the difference between raster and vector, and which devices support raster IMG
- **AND** they can follow a link to the detailed specification if needed

### Requirement: IMG format detailed specification
The IMG Format section SHALL include a "Detailed specification" page containing the binary format reference for the Garmin raster IMG format. This SHALL be the current `garmin-img.md` content with swisstopo IMG references replaced by IOM references.

#### Scenario: Developer needs binary format details
- **WHEN** a developer reads the detailed specification
- **THEN** they have complete information to implement a raster IMG writer, including byte offsets, field formats, and encoding details

### Requirement: IMG tools and resources page
The IMG Format section SHALL include a "Tools & resources" page with curated descriptions of Garmin IMG tools, format documentation, and reference implementations. The page SHALL NOT contain implementation planning sections, project status markers, or approach recommendations specific to cartoload.

#### Scenario: User finds IMG ecosystem tools
- **WHEN** a user reads the Tools & resources page
- **THEN** they find descriptions of relevant tools (mkgmap, GPXSee, GMapTool, etc.), format documentation links, and device compatibility information

### Requirement: CLI reference page
The documentation SHALL include a CLI Reference page documenting all `cartoload` commands with their options, arguments, and examples.

#### Scenario: User looks up a CLI option
- **WHEN** a user visits the CLI Reference page
- **THEN** they find the command and option they need with a description and example

### Requirement: API reference page
The documentation SHALL include an API Reference page as a placeholder for future Python API documentation.

#### Scenario: User visits API reference
- **WHEN** a user visits the API Reference page
- **THEN** they see a brief note that the Python API documentation is coming soon

### Requirement: No placeholder pages in navigation
The navigation SHALL NOT include pages that only say "Not yet implemented." Such pages SHALL be excluded from the nav but MAY remain as files for future use.

#### Scenario: User views navigation
- **WHEN** a user views the documentation sidebar
- **THEN** no navigation item leads to a page containing only "Not yet implemented"

### Requirement: No swisstopo IMG references
Documentation pages SHALL NOT reference swisstopo IMG sample files (e.g., SwissTopo_West.img, SwissTopo_Est.img) as their provenance is unclear. Swisstopo as a source config name in examples is acceptable. IOM.img references are acceptable.

#### Scenario: Documentation references sample files
- **WHEN** documentation references a sample IMG file
- **THEN** it uses IOM.img or a generic name, not a swisstopo IMG file
