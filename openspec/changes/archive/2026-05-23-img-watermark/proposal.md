## Why

When IMG files are distributed to users, there is no way to trace a leaked file back to a specific download. For fraud detection, we need a forensic watermark embedded in the IMG binary that records provenance information (download date, order UUID) — encrypted so that only the holder of the deployment key can read it.

## What Changes

- Add a watermark module that can write and read an encrypted string into the unused header gap region (0x0400–0x0FFF) of a Garmin IMG file
- The watermark offset within the gap is derived from `HMAC-SHA256(key, map_id)` so it varies per file and is unpredictable without the key
- Payload is encrypted with AES-256-GCM (provides both confidentiality and authentication)
- Add CLI commands `cartoload watermark write <img-file> <string>` and `cartoload watermark read <img-file>` for direct file manipulation
- Add a Python API (`write_watermark` / `read_watermark`) for server-side use during streaming
- The encryption key is provided via the `CARTOLOAD_WATERMARK_KEY` environment variable, a `--key` CLI parameter, or a `--key-file` parameter that reads the key from a file

## Capabilities

### New Capabilities
- `img-watermark`: Embed and retrieve encrypted forensic watermarks in Garmin IMG files using the unused header gap region

### Modified Capabilities

## Impact

- New module `src/cartoload/watermark.py` — watermark read/write logic
- New CLI subcommands under `cartoload watermark` — `write` and `read`
- Dependency: `cryptography` package (for AES-256-GCM and HMAC-SHA256)
- No changes to the IMG writer itself — watermarks are applied post-build by overwriting bytes in the reserved region
- Server-side: Django (or any Python code) can use the Python API to inject watermarks during streaming without running the CLI
