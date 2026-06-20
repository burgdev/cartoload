## Why

Standard JPEG quantization tables are tuned for natural photographs. Map tiles have very different visual characteristics (uniform color regions, sharp boundaries, thin lines, text). Custom quantization tables optimized for map imagery can yield 5-15% file size reduction at comparable visual quality.

The Garmin IOM reference file uses custom quantization tables (extracted below) that are specifically shaped for map tiles — very low luminance values (high quality) with aggressively clamped chrominance values. These tables can serve as a starting point for tuning.

## What Changes

- **Research phase**: Extract and analyze quantization tables from the IOM reference, compare with Pillow's default tables at various quality levels, understand the shape differences
- **Tuning phase**: Generate candidate quantization table sets by scaling the IOM tables to different quality levels, test with real map tiles, evaluate file size vs visual quality
- **Implementation phase**: Add a `qtables` parameter to the JPEG encoding path, allow configuration via the layer config or CLI
- **Validation phase**: A/B testing with real Swiss topographic tiles at different quality levels

## Capabilities

### New Capabilities

- `custom-jpeg-qtables`: Configurable JPEG quantization tables for map tile encoding, with presets derived from Garmin reference files

### Modified Capabilities

- `jpeg-border-padding`: The `_reencode_jpeg` function accepts optional quantization tables

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — `_reencode_jpeg` function, adds `qtables` parameter
- `examples/configs/layers/switzerland.yaml` — optional `jpeg_qtables` config field
- CLI — optional `--qtables` parameter
- Significant visual QA needed — custom tables change which details are preserved vs lost
