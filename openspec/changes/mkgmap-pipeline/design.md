## Context

mkgmap is a Java tool that converts OSM data into Garmin IMG files. It requires:
1. **OSM XML input** — features with tags
2. **A style** — rules mapping tags to Garmin type codes (e.g., `difficulty=WS [0x16 resolution 20]`)
3. **A TYP file** (optional) — defines visual appearance of Garmin type codes (colors, line widths, dash patterns)

The style engine (from `vector-style-engine` change) already has match expressions and visual properties. This change translates that internal model into mkgmap's native formats, runs mkgmap, and produces a separate `.img` file.

The key translation challenge is converting `LineStyle` (color, width, dash, border) into TYP file XPM bitmap patterns. Solid lines use `LineWidth`/`BorderWidth`, while dashed/complex patterns require 32-pixel-wide XPM bitmaps.

## Goals / Non-Goals

**Goals:**
- Convert GPKG features to OSM XML via ogr2ogr (all attributes as tags)
- Generate mkgmap style files from the style engine's match rules + Garmin type mappings
- Generate TYP files from visual properties (color, width, dash, border → XPM)
- Run mkgmap as a subprocess, produce a separate `.img` file
- Handle missing mkgmap/ogr2ogr gracefully with clear error messages

**Non-Goals:**
- Routing support (NET/NOD data) — routes are display-only
- Point/polygon features (start with lines)
- Bundling mkgmap with cartoload — user installs it separately
- Merging vector IMG with raster IMG (users manage separate files on device)

## Decisions

### 1. ogr2ogr for GPKG → OSM conversion

**Decision:** Use `ogr2ogr` (GDAL command-line tool) to convert GPKG to OSM XML format. All GPKG attributes become OSM tags with their original names.

```bash
ogr2ogr -f OSM output.osm input.gpkg --layers <layer_name>
```

**Rationale:** ogr2ogr is already available via GDAL (cartoload's existing dependency chain). It handles geometry conversion, CRS transformation, and attribute mapping. The OSM driver preserves all attributes as tags.

**Caveat:** ogr2ogr's OSM output driver may mangle some attribute names (e.g., convert to lowercase, replace special characters). Need to test with Swiss topo GPKG to verify attribute names survive. If not, a fallback approach using Fiona to read features + manual OSM XML writing would be needed.

### 2. Style generation: match expression → mkgmap rule

**Decision:** The match expression syntax was designed to be mkgmap-compatible. Generation is a direct textual transformation:

```python
# Style engine rule:
#   match="schwierigkeit=WS"
#   garmin={type: 0x16, resolution: [16, 24]}
#
# Generated mkgmap lines file:
#   schwierigkeit=WS [0x16 resolution 16-24]
```

For compound expressions (`&`, `|`, `!()`) the mapping is direct since the syntax is shared. Regex uses `~` in both systems. Numeric comparisons use `>`, `>=`, `<`, `<=` in both.

**Rule ordering:** Rules are written in the same order as the style engine (first match wins). The catch-all `*` rule goes last.

**Level mapping:** The `options` file maps Garmin resolution values to level indices. A default mapping covers the standard zoom levels:

```
levels = 0:24, 1:22, 2:20, 3:18
overview-levels = 4:17, 5:16, 6:15, 7:14, 8:13
```

### 3. TYP file generation: LineStyle → XPM bitmaps

**Decision:** Generate TYP files programmatically from `LineStyle` properties.

**Solid line with optional border:**
```
; Generated for type 0x16
[_line]
Type=0x16
LineWidth=2
BorderWidth=1
Xpm="0 0 2 0"
"1 c #FF0000"
"2 c #FFFFFF"
```

**Dashed line (and dashed with border):**
Requires a 32-pixel-wide XPM bitmap. The generator computes the bitmap from the dash pattern and border:

```python
def generate_dash_bitmap(dash_pattern, line_width, border_width, color, border_color):
    # Total height = line_width + 2 * border_width
    # Width = 32 pixels (fixed by Garmin format)
    # Dash pattern is tiled across the 32-pixel width
    # Each row is: [border_pixels] [dash_on/off_pixels] [border_pixels]
```

The XPM strings are generated programmatically — no manual bitmap editing.

**Color mapping:** `LineStyle.color` → XPM colour 1 (fill), `LineStyle.border_color` → XPM colour 2 (border). Day-only for simplicity.

### 4. mkgmap runner: subprocess with validation

**Decision:** Run mkgmap as a subprocess with pre-flight checks.

```python
def run_mkgmap(osm_path, style_dir, typ_path, output_path):
    # Check mkgmap is available
    # Build command: java -jar mkgmap.jar --style-dir=... --typ=... --output-dir=... input.osm
    # Run subprocess
    # Validate output .img exists
```

**mkgmap detection:** Check `java` and `mkgmap` on PATH, or `MKGMAP_JAR` environment variable. Fail with a clear message if not found.

**Alternative considered:** Bundle mkgmap as a Python dependency. Rejected — mkgmap is GPL-licensed Java, not appropriate to bundle.

### 5. Module structure

```
src/cartoload/mkgmap/
├── __init__.py          # public API: run_mkgmap_pipeline
├── osm_converter.py     # ogr2ogr wrapper: GPKG → OSM XML
├── style_generator.py   # StyleRule → mkgmap style files
├── typ_generator.py     # LineStyle → TYP file with XPM bitmaps
└── runner.py            # mkgmap subprocess wrapper
```

### 6. Config for vector output

**Decision:** A layer config requests vector output by specifying `exporter: mkgmap` or by having a `garmin` block in its rules:

```yaml
layers:
  skitouren:
    source: {type: gpkg, url: "..."}
    zoom_levels: [10, 11, 12, 13, 14]
    rules:
      - match: "schwierigkeit=L"
        style: {color: "#33A02C", width: 1}
        garmin: {type: 0x16, resolution: [18, 24]}
    exporter: mkgmap
    output: skitouren.img
```

When `exporter: mkgmap` is set, cartoload runs the mkgmap pipeline instead of the raster pipeline.

## Risks / Trade-offs

- **[ogr2ogr OSM driver limitations]** The OSM output driver may have quirks with attribute names or geometry types. → Test early with Swiss topo GPKG. If it fails, implement a fallback using Fiona + manual OSM XML writing (straightforward XML generation).
- **[XPM bitmap quality]** Programmatically generated bitmaps may not look as good as hand-tuned ones. → Acceptable for initial version. Users can provide custom TYP files if needed.
- **[mkgmap GPL license]** mkgmap is GPL. cartoload doesn't bundle it — just calls it as a subprocess. → No license conflict (similar to GCC calling pattern).
- **[Java dependency]** Requires JRE. → Many GIS users already have it. Clear error message if missing.
- **[Separate IMG files]** Users must manage multiple IMG files on their device. → This is actually an advantage — enables/disables overlays independently.
