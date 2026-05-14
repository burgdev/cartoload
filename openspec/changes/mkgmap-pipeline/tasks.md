## 1. Module setup

- [ ] 1.1 Create `src/cartoload/mkgmap/__init__.py` with public API (`run_mkgmap_pipeline`)
- [ ] 1.2 Create `src/cartoload/mkgmap/osm_converter.py`
- [ ] 1.3 Create `src/cartoload/mkgmap/style_generator.py`
- [ ] 1.4 Create `src/cartoload/mkgmap/typ_generator.py`
- [ ] 1.5 Create `src/cartoload/mkgmap/runner.py`

## 2. OSM converter

- [ ] 2.1 Implement `convert_gpkg_to_osm(gpkg_path, output_path, layer_name=None)` — run `ogr2ogr -f OSM` as subprocess, pass GPKG attributes through as OSM tags
- [ ] 2.2 Implement ogr2ogr availability check — verify ogr2ogr is on PATH, raise clear error if not
- [ ] 2.3 Write tests: verify OSM XML output contains expected tags from a test GPKG fixture, verify error when ogr2ogr missing

## 3. mkgmap style generator

- [ ] 3.1 Implement `generate_style(rules: list[StyleRule], output_dir: Path)` — write `version`, `options`, `lines` files to a style directory
- [ ] 3.2 Implement `version` file generation (content: `1`)
- [ ] 3.3 Implement `options` file generation with default level-to-resolution mapping
- [ ] 3.4 Implement `lines` file generation: iterate rules with `garmin` mappings, write `match_expression [type resolution min-max]` per rule
- [ ] 3.5 Handle compound match expressions: pass through `&`, `|`, `!()` syntax directly
- [ ] 3.6 Skip rules without `garmin` block (no Garmin type to assign)
- [ ] 3.7 Write catch-all rule (`* = *`) last if present
- [ ] 3.8 Write tests: verify generated lines file contains expected rules, compound expressions preserved, rules without garmin skipped

## 4. TYP file generator

- [ ] 4.1 Implement `generate_typ(rules: list[StyleRule], output_path: Path)` — generate a Garmin TYP text file
- [ ] 4.2 Implement solid line TYP entry: `LineWidth`, `BorderWidth`, XPM with 1-2 colours
- [ ] 4.3 Implement solid line with border: 2-colour XPM, `BorderWidth` set
- [ ] 4.4 Implement XPM bitmap generator for dashed lines: compute 32-pixel-wide bitmap from dash pattern, generate XPM string rows
- [ ] 4.5 Implement dashed line with border: bitmap height = `width + 2 * border_width`, border pixels on edge rows, dashed fill in middle rows
- [ ] 4.6 Map `LineStyle.color` to XPM colour 1, `LineStyle.border_color` to XPM colour 2 (day mode only)
- [ ] 4.7 Write tests: verify TYP output for solid line, solid+border, dashed, dashed+border; verify XPM bitmap is 32 pixels wide; verify bitmap height matches width+border

## 5. mkgmap runner

- [ ] 5.1 Implement `run_mkgmap(osm_path, style_dir, typ_path, output_dir, map_name)` — subprocess wrapper for mkgmap
- [ ] 5.2 Implement mkgmap availability check: look for `java` and `mkgmap.jar` on PATH or `MKGMAP_JAR` env var
- [ ] 5.3 Build mkgmap command: `java -jar mkgmap.jar --style-dir=... --typ=... --description=... --mapname=... --output-dir=... input.osm`
- [ ] 5.4 Capture and report mkgmap stderr on failure
- [ ] 5.5 Validate output: check `.img` file exists and is non-empty after mkgmap runs
- [ ] 5.6 Write tests: verify command construction, error on missing mkgmap, error on mkgmap failure

## 6. Pipeline integration

- [ ] 6.1 Add `mkgmap` to allowed exporter types in config
- [ ] 6.2 Implement `run_mkgmap_pipeline()` orchestration in `__init__.py`: GPKG → OSM conversion → style generation → TYP generation → mkgmap run → output .img
- [ ] 6.3 Add dispatch branch in `build_gpkg_layer()`: when `exporter == "mkgmap"`, call `run_mkgmap_pipeline()`
- [ ] 6.4 Write integration test: full pipeline with mocked ogr2ogr and mkgmap, verify output .img path
