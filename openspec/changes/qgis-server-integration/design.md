## Context

cartoload's vector rasterizer handles `SimpleLine` QML symbols but skips `MarkerLine`, `ArrowLine`, and other symbol types. For vector layers with complex symbology (ski route dots, direction arrows, point markers), the rendered output is degraded or invisible. The rasterizer is a supporting feature — the primary output path is Garmin IMG export via `garmin_types` mapping.

QGIS Server is a mature, Docker-deployable rendering engine that handles all QGIS symbology natively. Rather than reimplementing QGIS rendering in cartoload, QGIS Server can serve as an external tile source that feeds into the existing pipeline through the `wmts` source type.

## Goals / Non-Goals

**Goals:**
- Allow users to render vector layers with full QML fidelity via QGIS Server
- Provide a CLI command to generate QGIS project files from cartoload layer configs
- Enable the existing WMTS downloader to fetch tiles from QGIS WMS `GetMap` endpoints
- Document the full workflow with a guide and example Docker setup
- Support composite layers in project export (multiple layers in one QGIS project)

**Non-Goals:**
- No embedded QGIS rendering backend in cartoload
- No automatic QGIS Server lifecycle management (start/stop/restart)
- No QML parsing improvements for MarkerLine/ArrowLine in the built-in rasterizer
- No `.qgz` support (plain `.qgs` XML is sufficient)
- No WMTS GetCapabilities parsing (URL template approach is sufficient)

## Decisions

### 1. QGIS Server as external WMTS source, not a rasterizer backend

**Decision**: QGIS Server runs as a separate service. cartoload generates project files and the user points a `wmts` source at the server. No QGIS code runs inside cartoload.

**Rationale**: Avoids adding a ~800 MB dependency to cartoload. Keeps the pipeline unchanged. Users opt in only when they need full QML fidelity. The existing `wmts` source type already handles tile fetching, caching, and error retry.

**Alternative considered**: Embedding `qgis_headless` as a native extension. Rejected due to C++ compilation complexity and the massive dependency footprint.

### 2. `${bbox}` template variable in WMTS URLs

**Decision**: Add `${bbox}`, `${west}`, `${south}`, `${east}`, `${north}` template variables to `_build_tile_url()` in the WMTS downloader.

**Rationale**: QGIS WMS `GetMap` requires a `BBOX` parameter. The existing WMTS downloader only supports `${x}/${y}/${z}` for XYZ tile coordinates. Adding bbox variables allows QGIS WMS URLs to be expressed as URL templates in the existing `wmts` source config, with no pipeline changes.

**Alternative considered**: A new `wms` source type. Rejected because the WMTS downloader already handles URL templating, parallel fetching, caching, and retry — a WMS source would duplicate all of that.

### 3. `.qgs` XML generation with `xml.etree.ElementTree`

**Decision**: Generate `.qgs` files using Python's stdlib XML library. No third-party dependencies.

**Rationale**: The `.qgs` format is well-defined XML. For cartoload's use case (vector layers with QML styles + raster layers), the XML structure is straightforward. Using stdlib avoids adding dependencies.

**Alternative considered**: Using PyQGIS to generate project files. Rejected because PyQGIS requires a full QGIS installation — defeating the purpose of keeping cartoload lightweight.

### 4. Template-based QGIS project generation

**Decision**: Start with a hand-crafted XML template rather than trying to support the full `.qgs` schema. Only include elements needed for layer rendering (project CRS, layer definitions with data sources and styles).

**Rationale**: A full `.qgs` schema is complex and version-specific. cartoload only needs enough for QGIS Server to render tiles. A minimal but correct project file is more maintainable than a comprehensive generator.

### 5. `export-qgis-project` downloads local source data

**Decision**: The command downloads GPKG and GeoTIFF data before generating the project file. WMTS sources are skipped (they're remote tile services, not local data). Supports `--no-download` flag like the `build` command.

**Rationale**: The `.qgs` project references data files by path. Those files must exist before QGIS Server can render. Reusing the existing download infrastructure is straightforward.

## Risks / Trade-offs

- **[QGIS Server version compatibility]** `.qgs` XML structure varies between QGIS versions. → Generate minimal XML that works across QGIS 3.x versions. Test with QGIS 3.34 LTR.
- **[First-request latency]** QGIS Server caches projects in memory, but the first request for a new project parses the XML and loads data. → Document this behavior. Not a real issue for batch tile rendering.
- **[Path mapping in Docker]** The GPKG/GeoTIFF paths in the `.qgs` file must be accessible from within the QGIS Server container. → The guide documents volume mounting. The `export-qgis-project` command outputs the project in the cache directory alongside the data, making volume mounting straightforward.
- **[URL template complexity]** A QGIS WMS `GetMap` URL template is longer and more complex than a typical XYZ tile URL. → Provide working examples in docs and config. The `${bbox}` variable keeps it manageable.
