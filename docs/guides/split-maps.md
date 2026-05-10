# Split Large Maps

Garmin devices may have difficulty with very large `.img` files. The `split` command divides a single file into multiple region files.

## Usage

```bash
cartoload split <img_file> [OPTIONS]
```

### Options

| Flag | Description |
|------|-------------|
| `-o`, `--output-dir` | Output directory (default: current directory) |

### Example

```bash
cartoload split large_map.img -o ./split-output
```

This produces multiple smaller `.img` files in the output directory, each covering a geographic region of the original map.
