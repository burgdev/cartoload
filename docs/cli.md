# CLI Reference

```
Usage: cartoload [OPTIONS] COMMAND [ARGS]

Commands:
  build     Build one or more layers into output files
  download  Download source data only (no build)
  split     Split an oversized .img into region files
  list      List all layers from the provided config files
  analyze   Analyze geodata files
  cache     Manage the local tile cache
```

## build

```bash
cartoload build [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-S`, `--sources PATH` | Source config file(s) (repeatable) |
| `-L`, `--layers PATH` | Layer config file(s) (repeatable) |
| `-l`, `--layer TEXT` | Layer ID to build (repeatable; default: all) |
| `-e`, `--exporter TEXT` | Override exporter: `garmin_img` \| `garmin_img_vec` |
| `--bounds TEXT` | Override bounding box: `"west,east,south,north"` |
| `-y`, `--center-lat FLOAT` | Center latitude for bounds override |
| `-x`, `--center-lon FLOAT` | Center longitude for bounds override |
| `-W`, `--width FLOAT` | Width in km for bounds override |
| `-H`, `--height FLOAT` | Height in km for bounds override |
| `-z`, `--zoom TEXT` | Override zoom levels: `"10,12,14"` |
| `-o`, `--output-dir PATH` | Output directory (default: `./output`) |
| `-c`, `--cache-dir PATH` | Cache directory (default: `./cache`) |
| `--no-download` | Use existing cache only |
| `-f`, `--force` | Overwrite existing output files |
| `--dry-run` | Show build plan without executing |
| `-q`, `--quality INT` | JPEG quality 1–100 (default: 85) |
| `--preview` | Generate preview images after build |
| `--executor TEXT` | Execution mode: `thread` \| `process` |
| `--resume` | Resume a previous interrupted build |

See the [Build a map](guides/build-a-map.md) guide for a full walkthrough.

## analyze img

Inspect and compare Garmin IMG binary files. See [Analyze IMG files](guides/analyze-img.md) for detailed usage and examples.

```bash
cartoload analyze img info <img_file> [OPTIONS]
cartoload analyze img compare <file1> <file2>
```

## split

```bash
cartoload split <img_file> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-o`, `--output-dir PATH` | Output directory |

See [Split large maps](guides/split-maps.md).

## list

```bash
cartoload list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-S`, `--sources PATH` | Source config file(s) (repeatable) |
| `-L`, `--layers PATH` | Layer config file(s) (repeatable) |

## download

```bash
cartoload download [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-S`, `--sources PATH` | Source config file(s) (repeatable) |
| `-L`, `--layers PATH` | Layer config file(s) (repeatable) |
| `-l`, `--layer TEXT` | Layer ID to download (repeatable) |
| `-y`, `--center-lat FLOAT` | Center latitude |
| `-x`, `--center-lon FLOAT` | Center longitude |
| `-W`, `--width FLOAT` | Width in km |
| `-H`, `--height FLOAT` | Height in km |
| `-z`, `--zoom TEXT` | Zoom levels |
| `-c`, `--cache-dir PATH` | Cache directory (default: `./cache`) |

## cache

```bash
cartoload cache [COMMAND]
```

| Command | Description |
|---------|-------------|
| `cache info` | Show cache statistics |
| `cache clean` | Remove cached tiles |
