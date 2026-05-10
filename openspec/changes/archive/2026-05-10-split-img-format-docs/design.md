## Context

The IMG Format documentation currently lives in `docs/img-format/` with three files:
- `overview.md` (~100 lines) — high-level intro, well-scoped
- `detailed-spec.md` (~1465 lines) — complete binary format reference covering every aspect
- `tools-resources.md` (~100 lines) — external tools and references, well-scoped

The detailed spec is organized into 10 numbered sections plus an appendix, covering file headers, FAT, GMP container, tile storage, TRE sections, vector differences, draw order, size constraints, date format, reference file analysis, and format variant recommendations.

## Goals / Non-Goals

**Goals:**
- Split the monolithic spec into ~5 focused pages, each covering one logical area
- Preserve all existing content — no rewriting, just restructuring
- Maintain a clear navigation hierarchy in the sidebar
- Ensure cross-references between pages work correctly
- Keep the overview page as the entry point with links to all sub-pages

**Non-Goals:**
- Rewriting or improving the technical content
- Adding new content, diagrams, or examples
- Changing code, tests, or build configuration
- Altering the styling or layout of the docs site

## Decisions

### 1. Page structure — 5 new pages from the monolith

| New page | Source sections |
|---|---|
| `header-fat.md` | Sec 1 (Header), Sec 2 (FAT), Sec 9 (Date Format), Sec 3.9 (MPS) |
| `gmp-container.md` | Sec 3.1–3.8 (Subfile org, GMP container, sub-headers) |
| `tile-storage.md` | Sec 4 (Tile storage: JPEG, LBL28/LBL29, RGN2, DeltaStream) |
| `tre-sections.md` | Sec 5 (TRE header, TRE1–TRE8, subdivisions, raster layers) |
| `vector-reference.md` | Sec 6 + Appendix A (vector vs raster, vector format reference) |

**Rationale:** Grouping by subfile/functional area matches how readers approach the format — someone working on tile encoding goes to tile-storage, someone on spatial indexing goes to tre-sections.

**Alternative considered:** One page per section (10+ pages). Rejected because some sections (header + FAT) are too small to stand alone, and the nav would be overly deep.

### 2. Sections 7, 8, 10, 11, 12 distribution

These smaller sections (draw order, size constraints, reference file analysis, implementation files, format variant recommendation) will be distributed to the most relevant pages:
- Sec 7 (Draw Order) → `tre-sections.md` (closely tied to TRE display priority)
- Sec 8 (Size Constraints) → `header-fat.md` (related to file/container structure)
- Sec 10 (Reference File Analysis) → `gmp-container.md` (describes the actual reference files)
- Sec 11 (Implementation Files) → `overview.md` (high-level pointer to code)
- Sec 12 (Format Variant Recommendation) → `gmp-container.md` (comparison of single-map vs multi-map)

### 3. Nav structure in zensical.toml

The IMG Format nav section will list all 7 pages (overview + 5 new + tools-resources) as flat children:

```toml
{ title = "IMG Format", children = [
    { title = "Overview", path = "img-format/overview.md" },
    { title = "Header & FAT", path = "img-format/header-fat.md" },
    { title = "GMP Container", path = "img-format/gmp-container.md" },
    { title = "Tile Storage", path = "img-format/tile-storage.md" },
    { title = "TRE Sections", path = "img-format/tre-sections.md" },
    { title = "Vector Reference", path = "img-format/vector-reference.md" },
    { title = "Tools & Resources", path = "img-format/tools-resources.md" },
]},
```

### 4. Overview page updates

The overview page will gain a "Sections" block with links to each sub-page, and its "Further Reading" section will be updated to link to the new pages instead of the old `detailed-spec.md`.

### 5. Delete `detailed-spec.md` after splitting

The old file is removed once all content has been migrated. No redirect needed since this is not yet a published doc.

## Risks / Trade-offs

- **Cross-reference breakage** → Each new page will include relative links to sibling pages where the original had inline references. Verified by rebuilding docs and checking all links resolve.
- **Content gaps at split boundaries** → Some sections reference fields defined in other sections (e.g., RGN2 references TRE7 offsets). These cross-references will be converted to links with page context (e.g., "see [TRE7 offset table](tre-sections.md#54-tre7--raster-layer-section)").
- **Nav depth** → 7 items under IMG Format is manageable. If it grows further, a nested sub-grouping could be introduced later.
