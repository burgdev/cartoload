## Context

The current pipeline is single-source per layer: one `LayerConfig` references one `SourceConfig`, tiles are downloaded, reprojected, and written to IMG. The `type: "raster_overlay"` field exists but is unused — overlay layers are simply built as standalone IMG files.

The user wants to combine multiple raster layers (e.g., basemap + ski routes + hiking trails) into a single composite IMG file. This requires downloading tiles from multiple WMTS sources (potentially different tile grids or formats), blending them with per-layer opacity, and feeding the result into the existing streaming IMG writer.

Key constraint: the pipeline must remain compatible with single-layer configs (no `layers` sub-field). Composite layers are opt-in.

Future concern: non-WMTS sources (especially GeoTIFF) will be added later. The compositing design should not assume WMTS-only input.

## Goals / Non-Goals

**Goals:**
- Support compositing 2–5 raster sub-layers into one IMG output
- Allow per-sub-layer opacity (uniform float or per-zoom mapping)
- Support PNG input tiles (common for overlay layers with transparency)
- Allow sub-layers to reference existing top-level layers (DRY config)
- Allow inline sub-layer definitions with their own source/wmts_layer/zoom_levels
- Keep the existing single-layer pipeline completely unchanged
- Feed composited tiles into the existing `StreamingIMGWriter` without modification

**Non-Goals:**
- Vector layer compositing (out of scope — raster only)
- On-device layer toggling (the output is a single baked IMG)
- Per-sub-layer quality control (quality is applied once at final JPEG encoding)
- Non-uniform tile sizes between sub-layers at the same zoom level
- GeoTIFF source support in composite layers (future work)
- Custom importer/plugin system for sources (future work — but this design should not block it)

## Decisions

### D1: Composite layers as a new layer type, not a pipeline mode

**Decision**: Composite layers are defined via a `layers` sub-field on the existing `LayerConfig`. When present, the pipeline enters composite mode. When absent, behavior is identical to today.

**Rationale**: This is the least invasive approach. No new top-level config keys, no new CLI flags. The config is self-describing.

**Alternative**: A separate `composite_layers` top-level key would require changes to the config loader, CLI, and pipeline dispatch. More invasive for no benefit.

### D2: First sub-layer is the base (bottom), subsequent are overlaid in order

**Decision**: The `layers` list is ordered bottom-to-top. The first entry is painted first (base), each subsequent entry is alpha-composited on top.

**Rationale**: This matches the user's mental model ("basemap first, overlay on top") and is the standard painter's algorithm. No z-index complexity.

### D3: Sub-layer resolution: inline or ref

**Decision**: Each sub-layer is either:
- **Inline**: Has `source`, `wmts_layer`, `zoom_levels`, `extension`, `opacity` directly
- **Ref**: Has `ref: <layer_id>` pointing to an existing top-level layer, with optional overrides for `zoom_levels`, `opacity`

**Rationale**: Inline supports ad-hoc layers that only exist in the composite. Ref avoids duplicating config for layers that are also built standalone. Overrides on refs allow tailoring (e.g., wider zoom range) without modifying the original.

**Alternative**: Only inline (no refs) would force config duplication. Only refs (all sub-layers must be top-level) would clutter the config with layers that are never built independently.

### D4: Unified tile grid = union of zoom levels across sub-layers

**Decision**: The composite layer's zoom levels are the explicit `zoom_levels` on the composite layer itself (not the union of sub-layer zoom levels). Each sub-layer contributes tiles at its own zoom levels. If a sub-layer doesn't cover a particular zoom level, it is simply absent at that zoom — the remaining sub-layers are composited without it.

**Rationale**: The composite layer defines the output zoom levels. Sub-layers declare which of those zooms they contribute to. This gives explicit control — the user decides exactly which zooms appear in the output.

### D5: Compositing happens per-tile in the pipeline, before IMG write

**Decision**: Compositing is a new pipeline stage between "download" and "export". For each (x, y, z) tile position, the compositor:
1. Fetches all sub-layer tiles that exist at that (x, y, z) from cache
2. Loads them as PIL Images (RGBA)
3. Applies per-layer opacity
4. Alpha-composites bottom-to-top
5. Encodes the result as JPEG bytes

**Rationale**: This fits naturally into the existing pipeline. The `StreamingIMGWriter` consumes JPEG bytes — composited tiles are indistinguishable from single-source tiles. No changes to the writer.

**Alternative**: Compositing at export time (inside the writer) would entangle compositing with binary format details. Compositing at download time would require knowing all sub-layers upfront and coupling the downloader to compositing logic.

### D6: PNG tiles decoded to RGBA, JPEG tiles decoded to RGB (opaque alpha)

**Decision**: PNG tiles are decoded as RGBA (preserving transparency). JPEG tiles are decoded as RGB and treated as fully opaque. The compositor always works in RGBA internally and converts to RGB for final JPEG encoding.

**Rationale**: PNG overlays need their alpha channel for proper blending. JPEG has no alpha — treating it as opaque is correct. The final JPEG output has no alpha (Garmin IMG doesn't support transparency in raster tiles).

### D7: Opacity as float or per-zoom mapping

**Decision**: `opacity` can be:
- A float (0.0–1.0) applied uniformly at all zoom levels
- A dict `{zoom_level: opacity, ...}` for per-zoom control
- Omitted (defaults to 1.0)

**Rationale**: Per-zoom opacity is useful for overlays that should be subtle at low zoom (overview) but prominent at high zoom (detail). Uniform opacity covers the common case simply.

### D8: Tile fallback — upscale from closest lower zoom on 404

**Decision**: When a sub-layer declares a zoom level in its `zoom_levels` but a specific tile at (x, y, z) is unavailable (not in cache, 404 from server), the system SHALL fall back to the closest lower zoom level in the sub-layer's declared `zoom_levels` list and upscale that tile. Fallback only applies when the zoom level is declared but the tile is missing — if the zoom level is intentionally omitted from the list, no fallback occurs.

**Rationale**: WMTS overlay layers (ski routes, hiking trails) often have sparse coverage. A tile that exists at zoom 10 may not exist at zoom 12 for the same geographic area. Upscaling from the coarser zoom is standard practice — it adds blur but preserves the overlay information. Checking the cache for lower-zoom tiles is fast (already on disk). Only looking downward avoids downloading tiles the user didn't request.

**Alternative**: No fallback (just skip the sub-layer at that position) would produce maps where overlays appear and disappear unpredictably at adjacent tiles. Downscaling from a higher zoom would require having downloaded those tiles first, which the user may not have requested.

## Risks / Trade-offs

- **Performance**: Compositing N sub-layers means N× the downloads and N decode+blend per tile position. For 3 sub-layers this is ~3× slower than single-layer. → Mitigation: parallel downloads across sub-layers (different sources = independent rate limits). Compositing is cheap (PIL alpha blending is fast). The bottleneck remains network I/O.

- **Tile alignment**: Sub-layers from different WMTS sources may use different tile grids at the same zoom level (e.g., different CRS). → Mitigation: For phase 1, assume all sources use Web Mercator (EPSG:3857) tile grids. The tile coordinate math is standard and identical across WMTS servers. If a source uses a non-standard grid, the user must ensure compatibility via the source's `crs` field. Future work: resampling for misaligned grids.

- **Memory**: Compositing requires holding N decoded PIL images per tile. For 256×256 tiles with 5 sub-layers, this is ~1.3 MB per tile position — negligible. → Mitigation: no mitigation needed, memory impact is trivial.

- **Missing sub-layer tiles**: If an overlay source has gaps (no tile at a given position), the system falls back to the closest lower zoom and upscales. → Mitigation: Fallback is automatic and cache-based (fast). Only applies to declared zoom levels — intentionally omitted zooms are simply absent. If no lower-zoom fallback exists, the sub-layer is skipped for that tile position.

- **Config complexity**: The `layers` sub-field adds nesting. Users could create confusing configs with deeply nested refs. → Mitigation: No nesting beyond one level (composite layer → sub-layers). Refs can only point to top-level layers, not other composites.
