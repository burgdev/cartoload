## Context

The `--quality` CLI parameter (1-100, default 85) flows correctly through CLI → pipeline → exporter → writer, but has zero effect on output size. Three distinct bugs:

1. **No-processor path (EPSG:4326 sources)**: When `source_crs == "EPSG:4326"`, `tile_processor` is `None`, so `_process_tile_jpeg()` calls `tile.source_path.read_bytes()` — raw JPEG bytes, no re-encoding, quality ignored.

2. **Warp path (EPSG:3857→4326)**: `warp_tile_to_jpeg()` accepts a `quality` parameter but rasterio's `MemoryFile.open(driver="JPEG")` ignores `JPEG_QUALITY` creation options — always uses default quality. Verified: encoding random 256x256 data at Q20, Q50, Q85, Q95 all produce identical 37717 bytes.

3. **Sequential path drops quality**: `_process_tile_jpeg()` receives `jpeg_quality` but calls `tile_processor(path, x, y, zoom, source_crs)` without passing quality. The `tile_processor` callable signature only takes 5 args.

SwissTopo serves tiles at approximately JPEG Q85. Testing shows real compression ratios achievable via PIL:
- Q75: ~30% size reduction, visually indistinguishable
- Q50: ~50% size reduction, slight softening
- Q20: ~70% size reduction, noticeable artifacts

## Goals / Non-Goals

**Goals:**
- Make `--quality` actually control JPEG compression in the output IMG
- Minimize additional processing time (avoid unnecessary decode/re-encode when quality matches source)
- Keep the streaming/batched architecture intact (no loading all tiles into memory)

**Non-Goals:**
- Tile downsampling (reducing pixel dimensions) — could be a future enhancement
- WebP or other codec support — Garmin devices require JPEG
- Changing the default quality value (85 remains default)
- Optimizing the rasterio warp path beyond JPEG encoding fix

## Decisions

### Decision 1: Use PIL for JPEG re-encoding instead of rasterio MemoryFile

**Choice**: After rasterio warping, encode to JPEG via PIL (Pillow) instead of rasterio's MemoryFile JPEG driver.

**Rationale**: Rasterio's MemoryFile ignores `JPEG_QUALITY` creation options (verified empirically). PIL's `Image.save(format='JPEG', quality=N)` reliably controls quality. Since Pillow is already a project dependency (used by rasterio internally), no new dependency needed.

**Implementation**: `warp_tile_to_jpeg()` warps via rasterio into a numpy array, then encodes via PIL `Image.fromarray().save()` into a `BytesIO` buffer.

**Alternative considered**: Using GDAL directly with `gdal.Translate()` and JPEG_QUALITY option — too heavy, requires subprocess or extra GDAL Python bindings complexity.

### Decision 2: Always re-encode when quality differs from source

**Choice**: Introduce a re-encoding step that applies to ALL tiles, not just those needing reprojection.

**Rationale**: Currently, tiles already in EPSG:4326 bypass quality entirely. But the user's intent with `--quality 50` is "make the output 50% smaller" regardless of source CRS. The re-encode step decodes the JPEG to pixels, then re-encodes at the target quality.

**Optimization**: If quality >= 95 (or some high threshold matching typical server quality), skip re-encoding and pass through raw bytes. This avoids quality loss from double-encoding when the user wants maximum quality.

### Decision 3: Unify encoding into a single function

**Choice**: Create a `_reencode_jpeg(bytes, quality) -> bytes` helper that handles quality re-encoding. Call it from `_process_tile_jpeg()` and `_warp_tile_worker()`.

**Rationale**: Both the warp path and the pass-through path need the same re-encoding logic. A single helper avoids duplication and ensures consistent behavior.

**Alternative considered**: Adding quality parameter to the `tile_processor` callable signature — would require changing the callable protocol in multiple places. A simpler post-processing step is cleaner.

## Risks / Trade-offs

- **[Double-encoding quality loss]**: Re-encoding a JPEG that was already JPEG-compressed introduces generation loss. → Mitigation: at default quality 85, the loss is negligible (SwissTopo tiles are already ~Q85, re-encoding at Q85 is essentially a pass-through). At lower qualities, the user explicitly chose smaller size over quality.

- **[Processing time increase]**: Every tile now needs decode + re-encode instead of raw byte passthrough. → Mitigation: PIL JPEG operations on 256x256 tiles are fast (< 1ms per tile). Even 200K tiles would add ~3 minutes. The parallel ProcessPoolExecutor path already handles this.

- **[Quality threshold passthrough]**: If we skip re-encoding at high quality, output sizes won't change for users who don't set `--quality`. → Acceptable: default behavior should remain unchanged. Only users who explicitly lower quality see size reduction.
