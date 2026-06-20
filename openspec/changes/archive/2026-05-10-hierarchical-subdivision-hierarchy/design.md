## Context

The Garmin IMG format uses a subdivision hierarchy stored in TRE2 records to spatially index map data. Each subdivision at zoom level N has a `nextLevel` field pointing to its first child subdivision at level N+1. The device traverses this tree to find tiles relevant to the current viewport, pruning branches whose geographic bounds don't intersect the visible area.

**Current state (cartoload)**: All subdivisions at level N share the same `nextLevel` — pointing to the first subdivision at level N+1. This creates a "flat chain" where every parent links to every child, defeating spatial pruning. The device must scan all subdivisions at each level.

```
CURRENT: Flat Chain
═══════════════════════════════════════════════════════

Level 0 (1 subdiv)          ┌──────────────────────────┐
                            │         ROOT              │
                            │    nextLevel ──────────────────┐
                            └──────────────────────────┘    │
                                                            ▼
Level 1 (3 subdivs)    ┌──────────┬──────────┬──────────┐
                       │  Sub A   │  Sub B   │  Sub C   │
                       │  nextLvl─┼──nextLvl─┼──nextLvl─┼───► ALL point to
                       └──────────┴──────────┴──────────┘    first at L2
                                                            │
                                                            ▼
Level 2 (81 subdivs)  ┌────┬────┬────┬────┬────┬────┬────┐
                       │ S0 │ S1 │ S2 │ S3 │ .. │ .. │ S80│
                       └────┴────┴────┴────┴────┴────┴────┘

Problem: Sub A (north) and Sub C (south) BOTH point to ALL 81 children.
Device must scan ALL 81 even if only viewing the north area.
```

**Reference (mkgmap)**: Each parent's `nextLevel` points to its own children only. The `MapBuilder.makeMapAreas()` method iterates zoom levels top-down, splitting each parent independently. `Subdivision.getNextLevel()` returns `divisions.get(0).getNumber()` — the first child of THIS parent.

```
TARGET: True Hierarchy
═══════════════════════════════════════════════════════

Level 0 (1 subdiv)          ┌──────────────────────────┐
                            │         ROOT              │
                            │    nextLevel ──────────────────┐
                            └──────────────────────────┘    │
                                                            ▼
Level 1 (3 subdivs)    ┌──────────┬──────────┬──────────┐
                       │  Sub A   │  Sub B   │  Sub C   │
                       │  nextLvl─┤  nextLvl─┤  nextLvl─┤
                       └────┬─────┴────┬─────┴────┬─────┘
                            │          │          │
                            ▼          ▼          ▼
Level 2 (81 subdivs)  ┌─────────┬─────────┬─────────┐
                       │ S0..S26 │S27..S53 │S54..S80 │
                       │(north)  │(center) │(south)  │
                       └─────────┴─────────┴─────────┘

Device viewing north area follows ROOT → Sub A → S0..S26
Only 27 subdivisions scanned instead of 81.
```

Key files:
- `garmin_img.py:_set_subdivision_links()` — sets flat chain links
- `garmin_img.py:generate_subdivisions()` — creates uniform grid per zoom level
- `garmin_img.py:_assign_tiles_to_grid()` — assigns tiles to grid cells
- `garmin_img_model.py:Subdivision` — data model with `next_level_index`
- `garmin_img_writer.py` — writes TRE2 records using `sub.next_level_index`

## Goals / Non-Goals

**Goals:**
- Build a true parent-child subdivision tree where each parent's `nextLevel` points to its own spatially-contained children
- Maintain valid Garmin IMG binary output that renders correctly in GPXSee and on Garmin devices
- Preserve the existing grid-based subdivision layout at each zoom level
- Keep both `generate_subdivisions()` and `generate_subdivisions_from_metadata()` code paths working

**Non-Goals:**
- Adaptive splitting based on tile density (mkgmap's MapSplitter approach) — this is a future optimization
- Changing the zoom code computation or TRE1 records
- Changing the number of zoom levels or grid dimensions
- Optimizing RGN data layout or JPEG storage

## Decisions

### Decision 1: Generate subdivisions top-down with parent-bounded children

**Approach**: Iterate zoom levels from most-zoomed-out to most-zoomed-in. At each level, for each parent subdivision, generate child subdivisions that cover only the tiles within that parent's geographic bounds.

**Why**: This is the same approach mkgmap uses and naturally produces the correct parent-child relationships. The parent's bounds constrain which tiles can become its children, and the `nextLevel` field simply points to the first child in the flat list.

**Alternative considered**: Post-process the existing flat chain by spatially reassigning children. This is more complex and error-prone because the grid subdivisions at each level span the full map extent, making spatial containment ambiguous.

### Decision 2: Use bounding-box intersection for tile-to-parent assignment

**Approach**: When generating children for a parent, select tiles whose geographic bounds intersect the parent's bounds. Use intersection (not strict containment) to handle tiles that span grid cell boundaries.

**Why**: Tiles at lower zoom levels are larger and may overlap multiple parent subdivisions. Strict containment would lose tiles at boundaries. The device handles duplicates gracefully since tiles are raster images.

**Alternative considered**: Assign each tile to exactly one parent (nearest center). This risks missing tiles that genuinely overlap boundaries, potentially creating visual gaps.

### Decision 3: Flat list representation with index-based parent-child links

**Approach**: Keep subdivisions in a flat list (same as current), ordered by zoom level then by parent group. Each parent's `next_level_index` stores the list index of its first child. No tree data structure needed.

**Why**: This matches the binary TRE2 format exactly (subdivisions are written sequentially, `nextLevel` is an index). The writer code needs minimal changes — it already reads `sub.next_level_index`.

**Alternative considered**: Build an explicit tree then flatten. Adds an intermediate data structure for no benefit since the binary format is already flat.

### Decision 4: Empty overview levels get single full-bounds subdivision

**Approach**: Keep the current behavior where empty zoom levels (no tiles) get a single subdivision spanning the full map bounds, with the parent pointing to it.

**Why**: This matches Garmin IMG conventions. The inherited flag (0x80) on the topmost level already signals to devices that overview levels contain no renderable data.

## Risks / Trade-offs

- **[Risk: Tile duplication across parent boundaries]** Using intersection-based assignment means a tile near a parent boundary may appear in multiple parents' children. → **Mitigation**: Acceptable for raster maps — the device renders the same tile content twice but produces correct output. For vector maps this would be problematic, but cartoload only produces raster overlays.

- **[Risk: Uneven subdivision distribution]** A parent in a sparse area may get very few children while a parent in a dense area gets many. → **Mitigation**: Acceptable — the device still benefits from spatial pruning in the dense area. Future optimization: adaptive grid sizing per parent.

- **[Risk: TRE2 binary format correctness]** The `nextLevel` field encoding (15-bit index with bit15 as "end of chain" marker) must be set correctly. → **Mitigation**: The writer already handles this encoding; only the index values change. Verify with GPXSee and device testing.

- **[Risk: Grid sizing may not subdivide evenly]** If a parent's tiles don't divide evenly into the grid, some child subdivisions may be empty. → **Mitigation**: Empty subdivisions are valid in Garmin IMG (they just have no RGN data). The device skips them efficiently.
