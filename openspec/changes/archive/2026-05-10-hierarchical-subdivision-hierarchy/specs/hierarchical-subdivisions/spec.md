## ADDED Requirements

### Requirement: Subdivision hierarchy uses true parent-child relationships
The system SHALL generate TRE subdivisions where each parent's `nextLevel` field points to the first of its own spatially-contained children at the next zoom level, not to a shared global first-child index.

#### Scenario: Parent links to its own children only
- **WHEN** a parent subdivision P at zoom level N has geographic bounds (N, S, E, W)
- **AND** child subdivisions are generated at zoom level N+1
- **THEN** P's `next_level_index` SHALL point to the first child subdivision whose geographic bounds intersect P's bounds
- **AND** child subdivisions whose bounds do NOT intersect P's bounds SHALL NOT be linked from P

#### Scenario: All children of a parent are contiguous in the subdivision list
- **WHEN** parent P has K children at the next zoom level
- **THEN** the K children SHALL occupy consecutive indices in the flat subdivision list
- **AND** the last child SHALL have the "end of chain" marker (bit15 in TRE2 width field) set

#### Scenario: Empty overview levels maintain single-subdivision structure
- **WHEN** a zoom level has no tiles (overview level)
- **THEN** the system SHALL create a single subdivision spanning the full map bounds
- **AND** its parent's `next_level_index` SHALL point to this single subdivision

### Requirement: Tiles are assigned to parent-bounded subdivisions
The system SHALL assign tiles to subdivisions based on geographic intersection with parent bounds, ensuring that child subdivisions at level N+1 only contain tiles that fall within their parent's geographic area at level N.

#### Scenario: Tile assigned to correct parent's child
- **WHEN** tile T at zoom level N+1 has bounds that intersect parent subdivision P at level N
- **THEN** T SHALL be assigned to one of P's child subdivisions
- **AND** T SHALL NOT be assigned to a child of a different parent

#### Scenario: Tile spanning parent boundary
- **WHEN** tile T's bounds intersect two adjacent parent subdivisions P1 and P2
- **THEN** T SHALL be assigned to the child subdivision of whichever parent's center is nearest
- **OR** T MAY be duplicated in both parents' children (acceptable for raster maps)
