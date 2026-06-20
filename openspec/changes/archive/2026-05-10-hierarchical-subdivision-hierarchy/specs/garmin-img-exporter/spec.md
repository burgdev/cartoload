## ADDED Requirements

### Requirement: Subdivision generation produces hierarchical tree structure
The `generate_subdivisions()` and `generate_subdivisions_from_metadata()` functions SHALL produce subdivisions organized in a true parent-child tree, where each parent's children are spatially contained within the parent's bounds.

#### Scenario: generate_subdivisions produces hierarchical links
- **WHEN** `generate_subdivisions()` is called with tiles at multiple zoom levels
- **THEN** the returned subdivision list SHALL have each parent's `next_level_index` pointing to its first spatially-contained child
- **AND** no two parents at the same level SHALL share the same first child unless they have overlapping bounds

#### Scenario: generate_subdivisions_from_metadata produces hierarchical links
- **WHEN** `generate_subdivisions_from_metadata()` is called with tile metadata at multiple zoom levels
- **THEN** the returned subdivision list SHALL have the same hierarchical structure as `generate_subdivisions()`
