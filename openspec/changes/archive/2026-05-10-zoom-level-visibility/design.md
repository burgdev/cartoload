## Context

The Garmin IMG TRE1 section contains one 4-byte record per zoom level:
- Byte 0: `zoom_code` — contains a level indicator OR'd with the 0x80 inherited flag
- Byte 1: `level_number` — coordinate precision/bits
- Bytes 2-3: subdivision count at this level

GPXSee's rendering pipeline (`trefile.cpp`) uses the 0x80 flag to determine which levels to render:
```
_firstLevel = first index where !(level & 0x80)
zooms() returns range from _firstLevel to end
```

The current `_compute_zoom_codes()` in `garmin_img.py`:
```python
for i, level_num in enumerate(sorted_level_numbers):
    if i == 0:
        code = 0x80 + (n - 1)  # Always inherited on first
    else:
        code = n - 1 - i
```

This unconditionally marks the first zoom level as inherited. If that level has tiles (e.g., zoom 8), those tiles are invisible on devices. With a config like `zoom_levels: [8, 9, 11, 12, 13, 14, 15, 16]`, levels 8 and 9 may be genuinely empty (overview levels with no downloaded tiles), in which case the inherited flag is correct. But if zoom 8 or 9 has tiles, the flag makes them invisible.

**How mkgmap handles this**: mkgmap sets inherited=true only on the root/top-level subdivision (via `Map.topLevelSubdivision()` → `zoom.setInherited(true)`). This is always the single most-zoomed-out level, which typically contains only the map boundary and no features. All lower levels with actual map data are non-inherited.

## Goals / Non-Goals

**Goals:**
- Set the 0x80 inherited flag only on levels that are genuinely empty (no tiles)
- Ensure the most-zoomed-out level with actual tile data is non-inherited, so its tiles render on devices
- Keep the zoom code numbering scheme (descending from N-1) intact

**Non-Goals:**
- Changing the number of zoom levels (that's a user config choice)
- Changing the level_number remapping logic
- Changing the TRE2 or RGN binary format

## Decisions

### Decision 1: Inherited flag based on tile presence, not level position

**Approach**: Change `_compute_zoom_codes()` to accept information about which levels have tiles. Only levels that are empty AND at the top of the hierarchy get the inherited flag. The first level with tiles gets a non-inherited code.

**Why**: This matches the mkgmap pattern where inherited=true is set on the topmost level only because that level is the map boundary with no features. In cartoload's raster context, "no tiles" is the equivalent of "no features."

**Alternative considered**: Always set inherited=false on all levels. This would work but loses the semantic meaning that empty overview levels are "inherited" from the parent map structure. Some Garmin software may use the inherited flag for other purposes.

### Decision 2: Inherited flag on a prefix of empty levels only

**Approach**: Scan from the most-zoomed-out level inward. All consecutive empty levels at the top get the inherited flag. The first level with tiles (and all subsequent levels) are non-inherited.

**Why**: If levels 8 and 9 are empty and level 11 has tiles, levels 8 and 9 both get 0x80. Level 11 (the first with tiles) gets a non-inherited code. If level 8 has tiles, only it would get 0x80... but wait, that's wrong — if level 8 has tiles, it should NOT be inherited. Let me reconsider.

Actually, re-examining: the inherited flag means "this level has no independent data, inherit from parent." So it should only go on levels that are empty. The first non-empty level must NOT have it.

**Pattern**: `inherited[i] = True` for `i < first_non_empty_level_index`, `inherited[i] = False` otherwise. If the very first level has tiles, no level gets inherited.

### Decision 3: Zoom code numbering stays descending

**Approach**: The numeric part of the zoom code continues to descend from N-1 to 0. Only the 0x80 flag changes. Non-inherited levels get `code = N-1-i`, inherited levels get `code = 0x80 | (N-1-i)`.

**Why**: Preserves backward compatibility with the existing numbering scheme. The only change is which levels have the 0x80 bit set.

## Risks / Trade-offs

- **[Risk: Changing inherited flag may affect other Garmin software]** Some Garmin tools may interpret the inherited flag differently. → **Mitigation**: The mkgmap reference implementation uses the same pattern (inherited only on empty root). This is the standard behavior.

- **[Risk: All levels non-inherited when all have tiles]** If every zoom level has tiles, no level gets the inherited flag. → **Mitigation**: This is correct behavior — all levels have renderable data.

- **[Risk: Backward compatibility with existing configs]** Users with configs that rely on the old behavior (first level always inherited) may see their most-zoomed-out tiles appear. → **Mitigation**: This is the desired behavior — users WANT to see those tiles.
