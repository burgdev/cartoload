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

## Implementation Status (Updated 2026-04-22)

### Completed Fixes

1. **Map ID generation** — `map_id` now generated deterministically from layer config (bounds hash). Was defaulting to 0, causing FAT name "00000000" and MPS map_id=0.

2. **Map ID in TRE header** — Written at TRE offsets 116 and 207 (uint32 LE). GMT uses these to display the map ID. Previously zeros.

3. **MPS subfile format** — Corrected to match reference SwissTopo files: "LE" signature (not "MP"), map_id at offset 7, hex ID string, repeated map name. Previously had wrong format causing "Wrong MPS records size" from GMT.

4. **PDF specification analysis** — Analyzed John Mechalas' `imgformat-1.0.pdf` (2005). Key findings:
   - Vector vs raster use different subdivision formats (obj_types=0x0F for raster vs 0x10/0x20/0x40/0x80 for vector)
   - Map level definition: zoom level in bits 0-3, inherited flag in bit 7
   - LBL supports 6/8/10-bit label encoding (vector only)
   - TRE header variants: 116, 120, 154, 188 (vector) vs 273 (raster)
   - Checksum formula confirmed: `(-sum) & 0xFF` at offset 0x0F

### Known Limitations

1. **Subdivision records** — Currently written as zeros (8 bytes per zoom level). GMT reads `levels [0], zoom [0]` or derives values from subdivision data rather than the map_levels table. The reference SwissTopo files have complex subdivision records (8972 bytes) that encode zoom hierarchy and geographic boundaries. Proper raster subdivision encoding requires further reverse-engineering.

2. **CP/encoding display** — GMT shows `CP 0` instead of `CP 1252`. The LBL sub-header encoding field is set to 6 (CP1252) but GMT may read it from a different location.

3. **Parameters display** — GMT shows `parameters 0 0 0 1` instead of reference `parameters 1 4 36 1`. These come from TRE header fields at offsets 60-70.
