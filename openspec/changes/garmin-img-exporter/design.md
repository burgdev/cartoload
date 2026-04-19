## Context

The format-research change provides the reverse-engineered specification of the Garmin raster `.img` container format and the Python data models in `garmin_img_model.py`. This change implements the binary writer that produces valid `.img` files from processed GeoTIFF raster data. No open-source tool can currently write raster Garmin `.img` files — this is the core differentiator of cartoload.

The writer must accept a processed raster dataset (GeoTIFF) with associated layer configuration, encode tiles into the IMG container format at the specified zoom levels, respect the 3.5 MB per-tile-cell and 4 GB per-file limits, embed attribution in the map name header, and produce a file verifiable with `gmt -i -v`.

The existing codebase provides stubs: `exporters/base.py` defines a `BaseExporter` abstract class, and `exporters/garmin_img.py` is an empty stub. The data models from the format-research change (`garmin_img_model.py`) define `IMGHeader`, `SubfileHeader`, `TileRecord`, `DrawOrderEntry`, and related structures.

## Goals / Non-Goals

**Goals:**
- Write valid Garmin raster `.img` files from processed GeoTIFF data that pass `gmt -i -v` validation
- Support multi-resolution tile pyramids (multiple zoom levels in a single `.img` file)
- Embed attribution strings in the map name header so they appear on Garmin devices
- Respect the 3.5 MB per-tile-cell limit by splitting oversized tile data across multiple subfiles
- Respect the 4 GB per-file limit by splitting output into multiple `.img` files when necessary
- Finalize the `BaseExporter` interface based on actual exporter requirements
- Use numpy for binary packing — no new dependencies beyond what is already in `pyproject.toml`

**Non-Goals:**
- Vector `.img` writing — that is a Phase 2 feature covered by a separate change
- Format research — already completed in the format-research change
- Parsing or reading existing `.img` files — the writer only produces new files
- Optimizing tile encoding for file size (e.g., custom compression) — use the standard encoding discovered during format research
- GUI or interactive preview of output files

## Decisions

### 1. Pure Python with numpy for binary packing

**Choice**: Implement the writer in pure Python, using `numpy` for structured binary packing. No C extensions or Cython.

**Rationale**: The format-research change established that the Garmin `.img` format uses little-endian fixed-width fields, which map directly to numpy structured arrays. Pure Python keeps the project build-simple and portable. Performance is acceptable because the bottleneck is tile encoding, not raw binary packing — numpy handles the bulk data efficiently.

**Alternative considered**: `struct` module — more verbose for repeated fixed-width records, no vectorised operations. ctypes — more complex, no real benefit for sequential writes.

### 2. Chunk-based writing for large files

**Choice**: Write the `.img` file in chunks: compute offsets in a first pass, then stream subfile data sequentially. Do not hold the entire file in memory.

**Rationale**: Garmin `.img` files can reach 4 GB. Holding the entire binary blob in memory is not feasible. The two-pass approach (compute layout, then stream writes) allows accurate offset calculation while keeping memory usage proportional to a single tile row.

**Trade-off**: Requires two passes over the data — once for size calculation and offset assignment, once for actual binary output. The overhead is minimal since the first pass only counts sizes, it does not encode pixel data.

### 3. Use data models from garmin_img_model.py

**Choice**: Use the dataclass models from `garmin_img_model.py` (`IMGHeader`, `SubfileHeader`, `TileRecord`, `DrawOrderEntry`) as the intermediate representation. The writer converts these to binary.

**Rationale**: The format-research change already defined these models to match the reverse-engineered format. Reusing them ensures consistency between the spec, the data model, and the writer. Any format corrections in the model automatically propagate.

**Alternative considered**: Ad-hoc dict/tuple passing — loses type safety, harder to validate.

### 4. Tile splitting strategy for 3.5 MB limit

**Choice**: When a single tile cell exceeds 3.5 MB, split it into multiple subfile entries sharing the same geographic bounds but covering different portions of the tile data. The draw order table ties them together.

**Rationale**: The Garmin format has a hard 3.5 MB limit per tile cell in the subfile structure. High-resolution zoom levels with large tile dimensions can exceed this. Splitting across subfiles is the approach used by existing commercial tools (as observed during format research).

**Trade-off**: Increases subfile count and complexity. Alternative of reducing tile dimensions at high zoom levels would require re-tiling the raster, which is the processor's job.

### 5. File splitting for 4 GB limit

**Choice**: When the total output would exceed 4 GB, split into multiple `.img` files with independent headers. Each file covers a contiguous geographic region (spatial split along tile row boundaries).

**Rationale**: The Garmin `.img` format uses 32-bit offsets internally, creating a hard 4 GB file limit. Devices load multiple `.img` files from the same directory. Spatial splitting ensures each file is self-contained and independently loadable.

**Alternative considered**: Single file with truncated data — would lose map coverage. Not acceptable.

### 6. Finalize BaseExporter interface

**Choice**: Finalize the `BaseExporter` abstract class with methods: `export(raster_dataset, layer_config, output_path)` as the main entry point, plus `validate(output_path)` for post-write verification.

**Rationale**: The stub `BaseExporter` in `exporters/base.py` was created during project scaffolding as a placeholder. Actual implementation reveals what parameters are needed. The interface should be finalized here because this is the first concrete exporter, and it establishes the contract that future exporters (vector `.img`, other formats) will follow.

### 7. Validation via gmt

**Choice**: After writing, run `gmt -i -v <file>` as a validation step. The writer raises an error if validation fails.

**Rationale**: `gmt` (GMapTool) is the community-standard tool for inspecting Garmin `.img` files. Passing `gmt -i -v` is the strongest available signal that the file is structurally valid. It is already a system dependency in the Docker setup.

**Trade-off**: Requires `gmt` to be installed at validation time. In CI environments without `gmt`, validation can be skipped via a flag, but the Docker build always includes it.

## Risks / Trade-offs

- **Format is reverse-engineered** — The Garmin `.img` format is not officially documented. Output may be structurally valid (pass `gmt -i -v`) but not render correctly on all devices. Mitigation: test on multiple Garmin device families (Fenix watches, Oregon/GPSMAP handhelds) before release.
- **Real device testing required** — Unit tests and `gmt` validation cannot guarantee device compatibility. A dedicated device-testing phase is needed after implementation. Mitigation: partner with community members who own various Garmin devices.
- **3.5 MB tile cell limit requires careful chunking** — Incorrect splitting produces files that crash Garmin firmware. Mitigation: strict size accounting during the offset-calculation pass, with assertions before each write.
- **No reference implementation** — Unlike WMTS or GeoTIFF where libraries exist, there is no open-source raster `.img` writer to compare against. Bugs must be caught through binary comparison with known-good files and device testing.
- **Large file performance** — 4 GB files require careful memory management. Mitigation: chunk-based streaming writes, avoid loading full tile pyramids into memory simultaneously.
