# Analyze IMG Files

cartoload includes tools for inspecting and comparing Garmin IMG binary files.

## Inspect an IMG file

```bash
cartoload analyze img info <file>
```

### Summary mode

Get a concise overview (bounds, bitmap stats, encoding, map name):

```bash
cartoload analyze img info path/to/map.img -m
```

### List subfiles

Show all subfiles (GMP, MPS) in the IMG container:

```bash
cartoload analyze img info path/to/map.img -l
```

### Section filtering

Show only a specific section (TRE, TRE7, RGN, RGN2, LBL, NET, etc.):

```bash
# TRE7 section only
cartoload analyze img info path/to/map.img --section TRE7

# All TRE2 entries (no truncation)
cartoload analyze img info path/to/map.img --section TRE2 --limit 0
```

### Raster analysis

Annotated RGN2 analysis showing raster tile records per zoom level:

```bash
cartoload analyze img info path/to/map.img -r
```

Segment RGN2 by zoom level using TRE7 offsets:

```bash
cartoload analyze img info path/to/map.img -g
```

### Hex dumps

Raw hex dump of a specific section:

```bash
cartoload analyze img info path/to/map.img -x rgn2
```

Read raw bytes at a specific file offset:

```bash
cartoload analyze img info path/to/map.img --raw-offset 0x100 --raw-size 128
```

### Output control

| Flag | Description |
|------|-------------|
| `-m`, `--summary` | Concise summary only |
| `-l`, `--list` | List subfiles, no parsing |
| `-n`, `--section` | Show one section |
| `--limit` | Max entries per section (default 20, 0 = unlimited) |
| `-r`, `--rgn2` | Annotated RGN2 analysis |
| `-g`, `--segments` | TRE7-based zoom level segmentation |
| `-x`, `--hex` | Hex dump of a section |
| `-q`, `--no-descriptions` | Hide section descriptions |
| `--no-color` | Disable colored output |

## Compare two IMG files

Side-by-side comparison of RGN headers, RGN2 records, and byte-level diffs:

```bash
cartoload analyze img compare reference.img output.img
```

## Examples

```bash
# Quick overview of a map
cartoload analyze img info tests/data/garmin_samples/IOM.img -m

# Full analysis
cartoload analyze img info tests/data/garmin_samples/IOM.img

# Zoom level segmentation
cartoload analyze img info tests/data/garmin_samples/IOM.img -g

# Compare reference vs. output
cartoload analyze img compare reference.img my-output.img
```

Output uses Rich for colored formatting. Colors are automatically disabled when piped.
