## 1. Create new page files

- [x] 1.1 Create `docs/img-format/header-fat.md` — migrate Sec 1 (Header), Sec 2 (FAT), Sec 3.9 (MPS), Sec 8 (Size Constraints), Sec 9 (Date Format) from detailed-spec.md
- [x] 1.2 Create `docs/img-format/gmp-container.md` — migrate Sec 3.1–3.8 (Subfile org, GMP container, sub-headers), Sec 10 (Reference File Analysis), Sec 12 (Format Variant Recommendation) from detailed-spec.md
- [x] 1.3 Create `docs/img-format/tile-storage.md` — migrate Sec 4 (Tile Storage: JPEG, LBL28/LBL29, RGN2 compound records, DeltaStream bitstream, segment boundaries, complete data layout) from detailed-spec.md
- [x] 1.4 Create `docs/img-format/tre-sections.md` — migrate Sec 5 (TRE header layout, TRE1–TRE8, map levels, subdivisions, raster layers), Sec 7 (Draw Order and Attribution) from detailed-spec.md
- [x] 1.5 Create `docs/img-format/vector-reference.md` — migrate Sec 6 (Vector vs Raster differences) and Appendix A (Vector IMG format reference) from detailed-spec.md

## 2. Update cross-references

- [x] 2.1 Update `docs/img-format/overview.md` — add section links to all new pages, update "Further Reading" to replace `detailed-spec.md` link with individual page links
- [x] 2.2 Add inter-page links within new files where sections reference content in other pages (e.g., tile-storage referencing TRE7 → link to tre-sections)
- [x] 2.3 Update `docs/img-format/tools-resources.md` if it links to `detailed-spec.md`

## 3. Update navigation and cleanup

- [x] 3.1 Update `docs/zensical.toml` nav to list all 7 IMG Format pages (overview + 5 new + tools-resources)
- [x] 3.2 Delete `docs/img-format/detailed-spec.md`

## 4. Verify

- [x] 4.1 Rebuild docs with `zensical build -f docs/zensical.toml` and verify all pages render
- [x] 4.2 Verify all nav links and cross-page links resolve (curl check each page)
