## Why

JPEG tile data makes up 96% of Garmin IMG file size. Two simple, low-risk optimizations can reduce file size by 4-7% (~150-250 MB on a 3.5 GB file) with no visual quality change: progressive JPEG encoding and mozjpeg lossless post-processing.

## What Changes

- **Progressive JPEG encoding**: Add `progressive=True` to all Pillow `save()` calls in the Garmin IMG writer's JPEG encoding path. Progressive JPEG uses multi-scan encoding with more efficient Huffman coding, typically 2-3% smaller than baseline at the same quality.
- **mozjpeg lossless post-processing**: After Pillow encodes each tile, run the JPEG bytes through `mozjpeg-lossless-optimization` (pure Python package, pre-built wheels). This applies additional Huffman optimization and progressive scan reordering — strictly lossless, no visual change.
- **Dependencies**: Add `mozjpeg-lossless-optimization` to project dependencies.

## Capabilities

### New Capabilities

_None_

### Modified Capabilities

- `jpeg-border-padding`: The `_reencode_jpeg` function will use `progressive=True` and optionally apply mozjpeg post-processing after encoding.

## Impact

- `src/cartoload/exporters/garmin_img_writer.py` — `_reencode_jpeg` function, all `img.save()` calls
- `pyproject.toml` or `requirements.txt` — add `mozjpeg-lossless-optimization` dependency
- Encoding time per tile increases slightly (~5-10%) due to progressive encoding and post-processing pass
- Output files are 4-7% smaller with identical visual quality
- Garmin device compatibility: progressive JPEG is part of the JPEG standard (ITU-T T.81), all compliant decoders support it
