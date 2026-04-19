## Context

The cartoload project aims to produce Garmin `.img` map files from downloaded geodata. While vector `.img` creation is handled by mkgmap, **raster** `.img` files have no open-source writer. The Garmin raster `.img` format is a proprietary container that stores tiled raster map data alongside metadata like draw order, zoom levels, and attribution. Community efforts (GMapTool, SendMap,QLandkarte) have partially reverse-engineered the format, but no comprehensive documentation exists for building a writer from scratch.

The only reliable way to understand the format is to inspect existing raster `.img` files (e.g., swisstopo `.img` files already used as test data) using `gmt -i -v` (GMapTool's verbose info mode), which dumps header fields, subfile tables, tile records, and block structures.

This change is purely research and documentation — no `.img` writing code is produced. The outputs are a format specification document and Python data model classes that serve as the foundation for a future `garmin-img-exporter` change.

## Goals / Non-Goals

**Goals:**
- Fully document the Garmin raster `.img` container format by inspecting real files with `gmt -i -v`
- Document the IMG header structure, subfile organization, tile grid layout, zoom level encoding, draw order, attribution fields, and size constraints
- Create Python dataclass models in `src/cartoload/exporters/garmin_img_model.py` representing all discovered structures
- Validate the data model by parsing `gmt -i -v` output and confirming all fields are captured
- Produce the authoritative format reference at `docs/exporters/garmin-img.md`

**Non-Goals:**
- Writing any `.img` exporter code — that belongs to the `garmin-img-exporter` change
- Creating a standalone `.img` parser library — only the data model is needed
- Supporting vector `.img` format — mkgmap handles that
- Reverse-engineering encryption or DRM protection schemes
- Testing on actual Garmin hardware — validation is done via `gmt` output comparison only

## Decisions

### 1. Use `gmt -i -v` for format inspection

**Choice**: GMapTool's verbose info mode as the primary inspection tool.

**Rationale**: `gmt -i -v` is the most widely used tool for inspecting Garmin `.img` file internals. It dumps raw header bytes, subfile tables, FAT entries, and tile records in a human-readable format. The swisstopo `.img` files already available as test data provide real-world samples covering multiple zoom levels and tile grids.

**Alternative considered**: Raw hex editing / manual byte inspection — too slow and error-prone for the full format. Using `gmt` output as the primary source, supplemented by hex inspection for ambiguous fields, is more efficient.

### 2. Documentation location: `docs/exporters/garmin-img.md`

**Choice**: A single comprehensive document at `docs/exporters/garmin-img.md`.

**Rationale**: This mirrors the existing documentation structure established in the project-scaffolding change. The document becomes the authoritative reference for anyone working on the Garmin IMG exporter. It replaces the placeholder created during scaffolding.

### 3. Data model: Python dataclasses in `src/cartoload/exporters/garmin_img_model.py`

**Choice**: Plain `@dataclass` classes matching the project convention (no pydantic).

**Rationale**: The project config.yaml and existing `config.py` use plain dataclasses. The model file defines structures like `IMGHeader`, `SubfileHeader`, `TileRecord`, `DrawOrderEntry`, and `ZoomLevel` — all as dataclasses with typed fields and docstrings. These become the direct input types for the future writer.

**Alternative considered**: TypedDict or raw dicts — dataclasses provide better type safety, default values, and IDE support.

### 4. Multi-sample validation approach

**Choice**: Inspect multiple `.img` files (different zoom levels, different regions) and cross-reference findings.

**Rationale**: A single `.img` file may not exercise all format features. By inspecting multiple swisstopo files (e.g., ch_basemap_25k and ch_basemap_10k), we can identify which fields are constant vs. variable, and detect edge cases like maximum tile counts or boundary conditions.

## Risks / Trade-offs

- **Undocumented edge cases** → The format may contain fields or structures that only appear under specific conditions (e.g., very large maps, cross-boundary tiles). Mitigated by inspecting multiple samples and noting any unexplained bytes as "unknown/reserved" in the documentation.
- **Device generation differences** → Different Garmin device generations (e.g., Oregon vs. GPSMAP vs. Montana) may expect different internal structures. Initial research focuses on the format as understood by `gmt`, with device compatibility noted where known.
- **Format version skew** → Garmin may have updated the format over time without public documentation. The research documents the version(s) found in the sample files and notes any version-specific fields.
- **`gmt` tool accuracy** → GMapTool itself is reverse-engineered and may misinterpret some fields. Mitigated by cross-referencing with hex dumps for critical structures (header, FAT, tile records).
- **No open-source reference implementation** → Unlike vector `.img` (mkgmap), there is no open-source raster `.img` writer to validate findings against. The data model can only be validated by confirming it captures all fields from `gmt -i -v` output.
