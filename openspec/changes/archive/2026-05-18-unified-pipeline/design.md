## Context

The current pipeline in `src/cartoload/pipeline.py` has four separate build paths dispatched from `build_layer()`:

1. **Composite** (`build_composite_layer`) — handles multi-layer stacking with per-sub-layer download + compositing
2. **GeoTIFF** (`build_geotiff_layer`) — STAC or local GeoTIFF → pre-warp → VRT → read tiles
3. **GPKG** (`build_gpkg_layer`) — STAC or local GPKG → rasterize vector → PNG cache → read tiles
4. **WMTS** (inline in `build_layer`) — download tile grid → stream JPEGs

Each path duplicates download → metadata → export with subtle differences. The downloaders (`STACDownloader`, `GPKGDownloader`) share most of their logic (both query STAC, both cache, both have metadata sidecars) but are separate classes. Adding a new format requires touching multiple functions.

The config model conflates concerns: `SourceConfig.type` is both "how to fetch" and "what format", and `LayerConfig` is both a reusable definition and a build target.

## Goals / Non-Goals

**Goals:**
- One pipeline: the composite pipeline, where single-layer = 1 provider, no compositing needed
- Clean config: `layers` (reusable definitions, no output) and `targets` (build instructions with output)
- Pluggable Sources (how to fetch) and LayerProviders (how to process) — easy to add GeoJSON, FTP, etc.
- Clean cache lifecycle: source owns metadata sidecar, processor can replace originals
- Fast path for single-provider targets (no RGBA decode/re-encode overhead)
- Updated documentation

**Non-Goals:**
- Vector output pipeline (`to_vector`) — only `to_raster` for now, `to_vector` deferred
- Backwards compatibility — breaking config change is acceptable
- Performance optimization beyond the single-provider fast path
- Changes to the Garmin IMG exporter or tile writer

## Decisions

### Decision 1: Config structure — layers + targets

**Choice**: Split config into `layers` (reusable definitions) and `targets` (what to build). Targets reference layers and can override defaults.

```yaml
layers:
  swiss_25k:
    format: geotiff
    source: { ref: swisstopo_stac, layer: ch.swisstopo.pixelkarte-farbe-pk25.noscale }
    zoom_levels: [15, 16]

targets:
  ch_topo:
    name: "Switzerland Topo"
    output: ch_stac_test.img
    layers:
      - ref: swiss_25k
      - format: geotiff                    # inline layer
        source: { ref: swisstopo_stac, layer: ch.swisstopo.pixelkarte-farbe-pk50.noscale }
        zoom_levels: [13, 14]
```

**Alternative**: Keep current structure, just unify the pipeline internally.
**Rationale**: Clean separation of definition vs. build instruction. Makes layers reusable across targets. Eliminates the "layer is both definition and target" confusion.

### Decision 2: Source type = how to fetch, format = what to process

**Choice**: `source.type` (or auto-detected from URL) is purely the fetch method: `stac`, `wmts`, `path`. A new `format` field on layer definitions specifies the data format: `geotiff`, `gpkg`, `wmts`, `geojson`.

**Alternative**: Keep `type` doing double duty, add separate `processor` field.
**Rationale**: Two independent axes need two independent fields. Auto-detection from URLs works for source method. Format is a property of the data, not the transport.

### Decision 3: Source interface

```python
class Source(ABC):
    @classmethod
    def can_handle(cls, url: str) -> bool: ...

    def download(self, layer_config) -> None:
        """Fetch raw data to cache. Uses layer_config.bounds, .zooms as needed."""
        ...

    def is_cached(self, cache_path: Path) -> bool:
        """Check file + metadata sidecar. Also checks processor markers."""
        ...
```

Three implementations: `StacSource`, `WmtsSource`, `PathSource`. `StacSource` replaces both `STACDownloader` and `GPKGDownloader` — the shared `query_stac_collection` logic is already factored out. Format-specific asset finding is driven by the layer's `format` field.

### Decision 4: LayerProvider interface

```python
class LayerProvider(ABC):
    def __init__(self, source: Source, layer_config, cache_dir: Path): ...

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this provider can handle (e.g. ['.tif', '.tiff', '.zip'])."""
        ...

    def download(self) -> None:
        """Delegate to source.download() with format-aware filtering."""
        ...

    def prepare(self) -> None:
        """Pre-process downloaded data (pre-warp, rasterize, etc)."""
        ...

    def to_raster(self, x: int, y: int, z: int) -> Image.Image | None:
        """Return RGBA tile for compositing, or None if no data at this position."""
        ...
```

Providers: `GeotiffProvider`, `GpkgProvider`, `WmtsProvider`. Future: `GeojsonProvider`.

### Decision 5: Cache lifecycle — source owns metadata, processor owns cleanup

```
Source.download():
  1. Check is_cached() — looks for file OR metadata marker
  2. Download file + write metadata .json sidecar
  3. Return cache paths

Provider.prepare():
  1. Pre-process (warp, rasterize, etc.)
  2. Optionally delete original file
  3. Write marker so source.is_cached() returns True on next run
```

The metadata .json sidecar is the source's "receipt." The processor can delete the original but must keep the sidecar (or write its own marker). This decouples source cache checking from processor artifacts.

### Decision 6: Unified pipeline

```python
async def build_target(target, layers, sources, cache_dir, output_dir, **kwargs):
    providers = []
    for sub in target.layers:
        resolved = resolve_ref(sub, layers)
        source = resolve_source(resolved, sources)
        provider = make_provider(resolved.format, source, resolved, cache_dir)
        providers.append(provider)

    # Stage 1: Download
    for p in providers:
        p.download()

    # Stage 2: Prepare
    for p in providers:
        p.prepare()

    # Stage 3: Metadata
    metadata = compute_metadata(target.bounds, target.zoom_levels, providers)

    # Stage 4: Export
    if len(providers) == 1 and not needs_compositing(providers[0]):
        fast_export(target, metadata, providers[0])
    else:
        composite_export(target, metadata, providers)
```

### Decision 7: Single-provider fast path

When there's exactly one provider with opacity 1.0 at all zooms and no overrides, the pipeline streams raw bytes without RGBA decode/re-encode. This avoids JPEG generation loss and ~0.5ms/tile overhead for the common single-layer case.

### Decision 8: Registry for extensibility

```python
SOURCE_REGISTRY: dict[str, type[Source]] = {}
PROVIDER_REGISTRY: dict[str, type[LayerProvider]] = {}

def register_source(name: str, cls: type[Source]): ...
def register_provider(name: str, cls: type[LayerProvider]): ...

# Built-in registration
register_source("stac", StacSource)
register_source("wmts", WmtsSource)
register_source("path", PathSource)

register_provider("geotiff", GeotiffProvider)
register_provider("gpkg", GpkgProvider)
register_provider("wmts", WmtsProvider)
```

Adding a new type means implementing the Source or Provider ABC and calling `register_*`. No core pipeline changes needed.

## Risks / Trade-offs

- **[Scope]** This is a large refactor touching pipeline, config, downloader, processor, CLI, docs, and all tests → Mitigation: Implement in phases. Phase 1: config + pipeline. Phase 2: source/provider extraction. Phase 3: docs.
- **[Regression]** Single-layer WMTS performance could regress without fast path → Mitigation: Fast path is a core design decision, tested explicitly.
- **[Config migration]** All existing config files break → Mitigation: No backwards compat needed per requirements. Provide migration guide in docs.
- **[Complexity]** Two-level config (layers + targets) adds indirection for simple cases → Mitigation: Inline layers in targets allow single-file configs without separate definitions.
