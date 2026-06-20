## Context

The Garmin IMG writer in `garmin_img.py` uses a static dictionary `_GARMIN_ZOOM_CODES` to map Web Mercator zoom levels to Garmin TRE1 zoom codes. This mapping is incorrect — it assigns codes based on absolute zoom numbers rather than relative position within the file.

Binary analysis of reference files revealed the actual pattern:

- **IOM.img** (8 levels [17-24]): codes `0x87, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00`
- **SwissTopo_West.img** (5 levels [20-24]): codes `0x84, 0x83, 0x02, 0x01, 0x00`

The pattern: for N levels, the first level gets code `0x80 + (N-1)`, and remaining levels count down from `N-2` to `0`.

Our current mapping produces codes like `0x94, 0x93, 0x92` for zooms 10-12, which don't match any known reference file pattern. Zoom 8 is entirely missing and defaults to `0x00`.

## Goals / Non-Goals

**Goals:**

- Replace static zoom code mapping with a dynamic function
- Support any combination of zoom levels (including 8, 9, etc.)
- Match the zoom code pattern used by real Garmin devices
- Ensure GMT shows the `levels [...]` line correctly

**Non-Goals:**

- No changes to block size (32KB vs 2KB) — both work on Garmin devices
- No changes to format version field
- No changes to other TRE/RGN/LBL sections
- No hybrid raster+vector support

## Decisions

### 1. Dynamic zoom code computation

**Decision:** Replace `_GARMIN_ZOOM_CODES` with a function `_compute_zoom_codes(level_numbers: list[int]) -> list[tuple[int, int]]` that returns (level_number, zoom_code) pairs.

**Rationale:** Zoom codes depend on position within the file, not absolute zoom number. A static mapping cannot handle arbitrary zoom level combinations.

**Pattern:**

```python
def _compute_zoom_codes(sorted_level_numbers):
    n = len(sorted_level_numbers)
    codes = []
    for i, level_num in enumerate(sorted_level_numbers):
        if i == 0:
            code = 0x80 + (n - 1)
        else:
            code = n - 1 - i
        codes.append((level_num, code))
    return codes
```

Examples:

- 3 levels [8, 10, 12] → codes [0x82, 0x01, 0x00]
- 5 levels [20, 21, 22, 23, 24] → codes [0x84, 0x03, 0x02, 0x01, 0x00]
- 8 levels [17-24] → codes [0x87, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00]

### 2. Keep the code in `garmin_img.py`

**Decision:** Keep the zoom code computation in `garmin_img.py` (the exporter), not in the writer.

**Rationale:** The exporter builds the `IMGFile` data structure including zoom levels with their codes. The writer just serializes what it's given. This maintains the existing separation of concerns.

## Risks / Trade-offs

**[Risk] Pattern may not be fully correct for all level counts** → The pattern matches both IOM (8 levels) and SwissTopo (5 levels) exactly. Single-level files would get code 0x80, which is untested but follows the pattern.

**[Risk] Zoom codes alone may not fix Garmin device display** → There may be other issues (block size, version, TRE structure) preventing device rendering. This change addresses the most clearly incorrect aspect. Further fixes can follow.
