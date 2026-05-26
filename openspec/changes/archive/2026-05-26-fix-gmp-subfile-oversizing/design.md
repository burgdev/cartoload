## Context

The Garmin IMG exporter splits large maps into multiple GMP subfiles within a single IMG container. The split logic in `_split_into_gmp_groups` (garmin_img.py) and the split decision in `GarminIMGExporter.export()` use `TileMetadata.jpeg_size` — the **original** source JPEG file size — to estimate per-group data sizes.

At low JPEG quality settings (e.g., quality 25), actual re-encoded tiles are ~3-4x smaller than originals. The split logic doesn't account for this, creating too few GMP groups. The result is oversized GMP subfiles (up to 2.47 GB) that Garmin GPS devices cannot load.

A known-working file (8 GMPs, max 577 MB each) and a broken file (2 GMPs, max 2.47 GB) share the same total tile count (~585K tiles). The only difference is the per-GMP size distribution.

The quality ratio estimation function (`_estimate_quality_ratio`) already exists in `garmin_img_writer.py` but is only called during the writer's layout computation, not during the split decision.

## Goals / Non-Goals

**Goals:**
- Ensure GMP subfiles stay within GPS device limits regardless of quality setting
- Make split decisions based on actual output sizes (quality-adjusted), not source sizes
- Lower per-GMP target to match proven working limits (~512 MB)

**Non-Goals:**
- No changes to JPEG encoding, mirror padding, or tile processing
- No changes to the FAT structure or block allocation algorithm
- No changes to the MPS section or map ID generation
- No performance optimization of the split algorithm

## Decisions

### D1: Lower MAX_GMP_SIZE to 600 MB

**Choice**: Reduce `MAX_GMP_SIZE` from 3,500 MB to 600 MB.

**Rationale**: The known-working file had a max GMP size of 577 MB. The IOM reference file (50 GMPs from Garmin) has even smaller GMPs. 600 MB provides a safe margin. This is the simplest fix — it directly caps each GMP at a proven-safe size regardless of quality estimation accuracy.

**Alternatives considered**:
- 512 MB: More conservative, would create even more GMPs. May increase FAT overhead.
- 1 GB: Would still risk device compatibility.
- Keep 3.5 GB and only fix quality estimation: Risky — we don't know the exact device limit.

### D2: Apply quality ratio to split estimates

**Choice**: Compute the quality ratio (via `_estimate_quality_ratio`) before the split decision and apply it to `TileMetadata.jpeg_size` values used in `_split_into_gmp_groups`.

**Rationale**: Even with the lower `MAX_GMP_SIZE`, using original sizes at quality 25 would grossly over-estimate, creating far more GMPs than needed. Quality-adjusted estimates keep the GMP count reasonable. The ratio estimation samples a few tiles and computes a median ratio, which is sufficient for split sizing.

**Implementation**: Extract `_estimate_quality_ratio` to accept `tile_metadata` directly (it currently takes `subdivisions`), or compute the ratio in the exporter and pass it to `_split_into_gmp_groups`.

### D3: Move quality ratio computation before split decision

**Choice**: In `GarminIMGExporter.export()`, compute the quality ratio before calling `_split_into_gmp_groups` and pass it as a parameter.

**Rationale**: The quality ratio needs tile data and quality settings that are available at the exporter level. Rather than restructuring `_estimate_quality_ratio`, we compute the ratio once and pass it through. This keeps the change minimal.

## Risks / Trade-offs

- **More GMP subfiles** → At quality 25 with 600 MB limit, a 3.5 GB map would create ~6 GMPs instead of 2. More FAT entries but each stays small. The IOM file has 50 GMPs and works fine. → Acceptable.
- **Quality ratio estimation inaccuracy** → The ratio is based on 5 sample tiles. If those samples aren't representative, the split might still be slightly off. → Mitigated by D1's lower absolute cap: even if the ratio is wrong, each GMP is limited to 600 MB.
- **Regression on large maps** → Maps that previously had 2 GMPs will now have 6+. Block size may change (smaller per-GMP = smaller blocks). → Verify with existing test maps.
- **Not confirmed as the sole fix** → This addresses the most likely cause (oversized GMPs) but there may be other factors in GPS compatibility. → The lower GMP size is inherently safer regardless.
