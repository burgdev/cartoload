# CLI Reference

```
Usage: cartoload [OPTIONS] COMMAND [ARGS]

Commands:
  build     Build one or more layers into output files
  download  Download source data only (no build)
  split     Split an oversized .img into region files
  list      List all layers from the provided config files
  analyze   Analyze geodata files
```

## build

```
cartoload build [OPTIONS]
  --sources PATH    Source config file(s) (repeatable)
  --layers PATH     Layer config file(s) (repeatable)
  --layer TEXT      Layer ID to build (repeatable; default: all)
  --exporter TEXT   Override exporter: garmin_img | garmin_img_vec
  --bounds TEXT     Override bounding box: "west,east,south,north"
  --zoom TEXT       Override zoom levels: "10,12,14"
  --output-dir PATH Default: ./output
  --cache-dir PATH  Default: ./cache
  --no-download     Use existing cache only
  --quality INT     JPEG quality 1-100 (default: 85)
```

## analyze img

Inspect and compare Garmin IMG binary files.

```
cartoload analyze img <command> [OPTIONS]
```

Commands:
- `info` — inspect an IMG file
- `compare` — compare two IMG files side by side

### analyze img info

```
cartoload analyze img info <img_file> [OPTIONS]
  -s, --subfile TEXT     Subfile name (e.g. '00355951')
  -x, --hex TEXT         Dump hex of a section (gmp-header, tre-header, tre-levels, tre-subdivs, tre7, tre8, rgn-header, rgn-data, rgn2, rgn5, lbl-header, lbl-data)
  -d, --dump TEXT        Full hex dump of section with ASCII
  -l, --list             List subfiles only (no parsing)
  -a, --all              Dump all sections
  --raw-offset INT       Read raw bytes at file offset
  --raw-size INT         Size for raw read (default: 64)
  -r, --rgn2             Show annotated RGN2 analysis (raster tile records and polyline/polygon preambles per zoom level)
  -g, --segments         Segment RGN2 by zoom level using TRE7 offsets
  -m, --summary          Show concise summary (bounds, bitmaps, encoding, map name)
```

Examples:

```bash
# Concise summary
cartoload analyze img info tests/data/garmin_samples/IOM.img -m

# List all subfiles in an IMG
cartoload analyze img info tests/data/garmin_samples/IOM.img -l

# Full analysis (TRE, RGN, LBL sections with bitmap stats)
cartoload analyze img info tests/data/garmin_samples/IOM.img

# Annotated RGN2 analysis
cartoload analyze img info tests/data/garmin_samples/IOM.img -r

# Segment RGN2 by zoom level
cartoload analyze img info tests/data/garmin_samples/IOM.img -g

# Hex dump of a specific section
cartoload analyze img info tests/data/garmin_samples/IOM.img -x rgn2

# Raw bytes at a specific offset
cartoload analyze img info tests/data/garmin_samples/IOM.img --raw-offset 0x100 --raw-size 128
```

### analyze img compare

```
cartoload analyze img compare <file1> <file2>
```

Side-by-side comparison of two IMG files. Shows RGN headers, RGN2 record-by-record parsing, and a diff of RGN header bytes 0x15–0x7C.

Example:

```bash
cartoload analyze img compare reference.img output.img
```
