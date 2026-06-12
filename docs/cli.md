# CLI Reference

cartoload — convert geodata into GPS device maps.

**Usage:** `cartoload COMMAND [ARGS]`

**Subcommands:**

`analyze`
:   Analyze geodata files.

`build`
:   Build one or more layers into output files.

`download`
:   Download source data only (no build).

`split`
:   Split an oversized .img into region files.

`list`
:   List all layers from the provided config files.

`cache`
:   Inspect and manage the tile cache.

`watermark`
:   Read and write forensic watermarks in Garmin IMG files.

---

### `cartoload analyze`

Analyze geodata files.

**Usage:** `cartoload analyze COMMAND [ARGS]`

**Subcommands:**

`img`
:   Analyze Garmin IMG binary files.

### `cartoload analyze img`

Analyze Garmin IMG binary files.

**Usage:** `cartoload analyze img COMMAND [ARGS]`

**Subcommands:**

`info`
:   Analyze a Garmin IMG file.

`compare`
:   Compare two IMG files: structure, headers, and RGN2 raster tiles.

`export`
:   Export IMG raster tiles to GeoTIFF format.

### `cartoload analyze img info`

Analyze a Garmin IMG file.

**Usage:** `cartoload analyze img info [OPTIONS] IMG_FILE`

**Arguments:**

`IMG_FILE`
:   Path


**Options:**

`-s, --subfile TEXT`
:   Subfile name (e.g. '00355951')

`-n, --section TEXT`
:   Show only one section (TRE, TRE7, RGN, RGN2, LBL, NET, etc.)

`--limit INTEGER`
:   Max entries per section (default: 20, 0 = unlimited)

`-x, --hex TEXT`
:   Dump hex of section

`-d, --dump TEXT`
:   Full hex dump of section with ASCII

`-l, --list`
:   List subfiles only

`-a, --all`
:   Dump all sections

`--raw-offset INTEGER`
:   Read raw bytes at offset

`--raw-size INTEGER`
:   Size for raw read (default: 64)

`-r, --rgn2`
:   Show annotated RGN2 analysis. RGN2 contains raster tile records (E0) and polyline/polygon preambles that describe bitmap placement per zoom level.

`-g, --segments`
:   Segment RGN2 by zoom level using TRE7 offsets. Shows how raster tiles are grouped into zoom levels within the RGN2 data section.

`-m, --summary`
:   Show concise summary (bounds, bitmaps, encoding, map name)

`-q, --no-descriptions`
:   Hide section descriptions

`--tile-details`
:   Validate coordinate encoding and show per-tile decoded coordinates

`--no-color`
:   Disable colored output

### `cartoload analyze img compare`

Compare two IMG files: structure, headers, and RGN2 raster tiles.

**Usage:** `cartoload analyze img compare [OPTIONS] FILE1 FILE2`

**Arguments:**

`FILE1`
:   Path

`FILE2`
:   Path


**Options:**

`--no-color`
:   Disable colored output

`--headers-only`
:   Only compare headers, skip RGN2 samples

`--sample-size INTEGER`
:   Number of RGN2 records to compare (default: 10)

`--full`
:   Full raw dump mode (legacy verbose output)

### `cartoload analyze img export`

Export IMG raster tiles to GeoTIFF format.

**Usage:** `cartoload analyze img export [OPTIONS] IMG_FILE`

**Arguments:**

`IMG_FILE`
:   Path


**Options:**

`-o, --output PATH`
:   Output GeoTIFF file path

`--bbox TEXT`
:   Bounding box filter: west,south,east,north (e.g., '7.0,46.0,8.0,47.0')

`--zoom TEXT`
:   Zoom level filter: single level or range (e.g., '14' or '12-16')

`--max-tiles INTEGER`
:   Maximum tiles to export (0 = all, useful for testing)

---

### `cartoload build`

Build one or more layers into output files.

**Usage:** `cartoload build [OPTIONS]`

**Options:**

`-c, --config PATH ...`
:   Config file(s) (repeatable)

`-l, --layer TEXT`
:   Layer ID to build (required)

`-b, --bbox FLOAT`
:   Override bounding box: W S E N

`-x, --lng FLOAT`
:   Center longitude for extent (use with --lat/--width/--height)

`-y, --lat FLOAT`
:   Center latitude for extent (use with --lng/--width/--height)

`-W, --width FLOAT`
:   Extent width in km (use with --lng/--lat/--height)

`-H, --height FLOAT`
:   Extent height in km (use with --lng/--lat/--width)

`-z, --zoom TEXT`
:   Override zoom levels: 10,12,14

`-o, --output-dir TEXT`
:   Default: ./output

`-C, --cache-dir TEXT`
:   Default: ./cache

`--no-download`
:   Use existing cache only

`--offline`
:   Skip freshness checks, use cached files as-is

`--update`
:   Check cache freshness via HTTP HEAD

`--ago INTEGER`
:   Only update if cached file is older than N days

`-f, --force`
:   Overwrite existing output files

`--dry-run`
:   Show build plan without executing

`--cache-warmup`
:   Download and cache tiles only, skip IMG build

`--preview`
:   Generate preview images after build

`-P, --preview-tiles INTEGER`
:   Max tiles per preview mosaic (default: 9)

`--preview-center FLOAT`
:   Override preview center: LNG LAT

`-q, --quality INTEGER RANGE`
:   JPEG quality 1-100 (default: passthrough, no re-encoding)

`--qtables {raster,default}`
:   Custom quantization tables: 'raster' (map-optimized) or 'default' (standard)

`--executor {process,thread}`
:   Parallel executor mode: 'process' (default, fastest) or 'thread' (less memory)

`--fast`
:   Fast build: skip mirror-padding and cjpeg trellis optimization (larger output)

`-v, --verbose`
:   Show detailed tracebacks on errors

---

### `cartoload download`

Download source data only (no build).

**Usage:** `cartoload download [OPTIONS]`

**Options:**

`-c, --config PATH ...`
:   Config file(s) (repeatable)

`-l, --layer TEXT`
:   Layer ID to download (required)

`-b, --bbox FLOAT`
:   Override bounding box: W S E N

`-x, --lng FLOAT`
:   Center longitude for extent (use with --lat/--width/--height)

`-y, --lat FLOAT`
:   Center latitude for extent (use with --lng/--width/--height)

`-W, --width FLOAT`
:   Extent width in km (use with --lng/--lat/--height)

`-H, --height FLOAT`
:   Extent height in km (use with --lng/--lat/--width)

`-z, --zoom TEXT`
:   Override zoom levels: 10,12,14

`-C, --cache-dir TEXT`
:   Default: ./cache

---

### `cartoload split`

Split an oversized .img into region files.

**Usage:** `cartoload split [OPTIONS] IMG_FILE`

**Arguments:**

`IMG_FILE`
:   Path


**Options:**

`-o, --output-dir TEXT`
:   Output directory (default: same as input)

---

### `cartoload list`

List all layers from the provided config files.

**Usage:** `cartoload list [OPTIONS]`

**Options:**

`-c, --config PATH ...`
:   Config file(s) (repeatable)

---

### `cartoload cache`

Inspect and manage the tile cache.

**Usage:** `cartoload cache [OPTIONS] COMMAND [ARGS]`

**Options:**

`-C, --cache-dir TEXT`
:   Default: ./cache


**Subcommands:**

`status`
:   Report cache size and tile counts per source.

`clean`
:   Remove cached tiles.

### `cartoload cache status`

Report cache size and tile counts per source.

**Usage:** `cartoload cache status`
### `cartoload cache clean`

Remove cached tiles.

**Usage:** `cartoload cache clean [OPTIONS]`

**Options:**

`--source TEXT`
:   Clean only a specific source's cache

`-f, --force`
:   Skip confirmation prompt

---

### `cartoload watermark`

Read and write forensic watermarks in Garmin IMG files.

**Usage:** `cartoload watermark COMMAND [ARGS]`

**Subcommands:**

`write`
:   Write a watermark string into a Garmin IMG file.

`read`
:   Read and print the watermark from a Garmin IMG file.

`read-header`
:   Read the cleartext header from a Garmin IMG file (no key required).

### `cartoload watermark write`

Write a watermark string into a Garmin IMG file.

**Usage:** `cartoload watermark write [OPTIONS] IMG_FILE PAYLOAD`

**Arguments:**

`IMG_FILE`
:   Path

`PAYLOAD`
:   Text


**Options:**

`--key TEXT`
:   Encryption key

`--key-file PATH`
:   Read key from file

`--header TEXT`
:   Cleartext header string (e.g. order=ID)

### `cartoload watermark read`

Read and print the watermark from a Garmin IMG file.

**Usage:** `cartoload watermark read [OPTIONS] IMG_FILE`

**Arguments:**

`IMG_FILE`
:   Path


**Options:**

`--key TEXT`
:   Encryption key

`--key-file PATH`
:   Read key from file

### `cartoload watermark read-header`

Read the cleartext header from a Garmin IMG file (no key required).

**Usage:** `cartoload watermark read-header IMG_FILE`

**Arguments:**

`IMG_FILE`
:   Path
