## 1. WMTS BBOX Template Variables

- [ ] 1.1 Add `${bbox}`, `${west}`, `${south}`, `${east}`, `${north}` template variable support to `_build_tile_url()` in `src/cartoload/downloader/wmts.py`
- [ ] 1.2 Compute the Web Mercator bounding box from tile coordinates (x, y, zoom) in the WMTS downloader
- [ ] 1.3 Add tests for BBOX variable substitution in `tests/test_wmts_bbox.py`

## 2. QGIS Project Generator Module

- [ ] 2.1 Create `src/cartoload/qgis_project.py` with a function to generate `.qgs` XML using `xml.etree.ElementTree`
- [ ] 2.2 Implement EPSG:3857 project CRS element generation
- [ ] 2.3 Implement vector layer (GPKG/ogr) element generation with QML style reference
- [ ] 2.4 Implement raster layer (GeoTIFF/gdal) element generation
- [ ] 2.5 Implement relative path computation for data sources relative to the project file location
- [ ] 2.6 Support multiple layers (composite) — ordered bottom-to-top in the layer tree
- [ ] 2.7 Add tests for `.qgs` XML generation in `tests/test_qgis_project.py`

## 3. CLI Command: export-qgis-project

- [ ] 3.1 Add `export-qgis-project` command to `src/cartoload/cli.py` with options: `-c`, `-l`, `-o`, `--no-download`, `-C/--cache-dir`
- [ ] 3.2 Implement data download step: iterate layer sources, download GPKG/GeoTIFF (skip WMTS), reuse existing download infrastructure
- [ ] 3.3 Wire the project generator: pass resolved layer configs + local file paths to `qgis_project.py`
- [ ] 3.4 Add `--no-download` flag support — skip download, use existing cache
- [ ] 3.5 Add integration test for the CLI command in `tests/test_cli.py`

## 4. Docker Compose Example

- [ ] 4.1 Create `docker-compose.qgis.yml` with QGIS Server service using `qgis/qgis:ltr` image, volume mounts for cache and project files, and port 8080

## 5. Documentation

- [ ] 5.1 Create `docs/guides/qgis-integration.md` — guide covering: the workflow, export command usage, Docker setup, WMTS source config for QGIS Server, and tips for path mapping
