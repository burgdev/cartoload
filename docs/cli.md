# CLI Reference

```
Usage: cartoload [OPTIONS] COMMAND [ARGS]

Commands:
  build     Build one or more layers into output files
  download  Download source data only (no build)
  split     Split an oversized .img into region files
  list      List all layers from the provided config files
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
