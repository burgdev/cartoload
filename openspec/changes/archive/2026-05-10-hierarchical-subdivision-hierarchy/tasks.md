## 1. Refactor subdivision generation to produce hierarchical tree

- [x] 1.1 Add `_generate_child_subdivisions()` helper that takes a parent subdivision's bounds and the tiles at the next zoom level, and returns a list of child subdivisions contained within those bounds (using grid-based subdivision and intersection-based tile assignment)
- [x] 1.2 Add `_generate_child_subdivisions_from_metadata()` variant that works with TileMetadata instead of (bytes, bounds) tuples
- [x] 1.3 Refactor `generate_subdivisions()` to iterate zoom levels top-down: level 0 gets single full-bounds subdivision (or grid if tiles exist), then for each parent at level N, call `_generate_child_subdivisions()` to create its children at level N+1
- [x] 1.4 Refactor `generate_subdivisions_from_metadata()` with the same top-down hierarchical approach using the metadata variant

## 2. Replace flat chain linking with hierarchical linking

- [x] 2.1 Replace `_set_subdivision_links()` with hierarchical linking: since children are now generated per-parent and appended contiguously, set each parent's `next_level_index` to the index of its first child in the flat list
- [x] 2.2 Remove the old flat-chain linking code that sets all parents' `next_level_index` to `by_level[next_z][0]`

## 3. Handle edge cases

- [x] 3.1 Ensure empty overview levels (no tiles) create a single full-bounds subdivision whose children at the next level are still correctly linked
- [x] 3.2 Handle the case where a parent has no tiles in its bounds at the next zoom level (create an empty child subdivision)
- [x] 3.3 Ensure grid sizing for children is reasonable: subdivide proportionally to the number of tiles within the parent's bounds, not the total tiles at that zoom level

## 4. Verification

- [ ] 4.1 Generate an IMG file with the hierarchical subdivision structure and verify it opens correctly in GPXSee
- [ ] 4.2 Run `cartoload analyze img info` on the generated file and verify that parent subdivisions have different `next_level_index` values (not all pointing to the same first child)
- [ ] 4.3 Test on GPSMAP 66i device and verify rendering speed improvement
