## Why

The IMG Format detailed specification (`docs/img-format/detailed-spec.md`) is a single ~1465-line monolithic page covering the entire Garmin raster IMG binary format. It is unwieldy to navigate, impossible to link to specific topics from code or other docs, and overwhelms readers who only need one area (e.g., tile storage or TRE sections). The overview and tools-resources pages are well-scoped; only the detailed spec needs splitting.

## What Changes

- Split `detailed-spec.md` into 5 focused pages under `docs/img-format/`:
  - `header-fat.md` — File header structure, FAT layout, date encoding, MPS subfile
  - `gmp-container.md` — GMP container format, subfile organization, sub-headers (TRE, RGN, LBL, NET)
  - `tile-storage.md` — JPEG tile data, LBL28/LBL29 index/storage, RGN2 compound records, DeltaStream bitstream
  - `tre-sections.md` — TRE header layout, TRE1–TRE8 sections, map levels, subdivisions, raster layers
  - `vector-reference.md` — Vector vs raster differences, vector format appendix (kept for completeness)
- Update nav in `docs/zensical.toml` to list all new pages under the IMG Format section
- Update cross-references between pages (links from overview, between sub-pages)
- Remove the old `detailed-spec.md`

## Capabilities

### New Capabilities

_None — this is a documentation restructuring, no new software capability._

### Modified Capabilities

_None — no spec-level behavior changes, only documentation reorganization._

## Impact

- **Documentation only**: `docs/img-format/` directory restructured, `docs/zensical.toml` nav updated
- **No code changes**: no source files, tests, or build configuration affected
- **External references**: any bookmarks or links to `detailed-spec.md` will break (this is a new page, not yet published, so impact is minimal)
