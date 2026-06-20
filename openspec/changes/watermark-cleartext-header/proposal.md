## Why

Watermark payloads are fully encrypted, creating a chicken-and-egg problem for forensic recovery: you need the key to decrypt the watermark, but you need to know which order/download produced the file to look up the correct key. After key rotation or with many downloads, finding the right key requires trying every key — which is impractical.

## What Changes

- Split the watermark region into two parts: a **cleartext header** and the existing **encrypted payload**
- The cleartext header stores key-value metadata (e.g. `order=PUBLIC_ID`) in UTF-8 at a fixed, well-known offset within the watermark region
- The encrypted payload continues to hold the sensitive data (`user=PUBLIC_ID:t=TIMESTAMP`) using the existing AES-256-GCM scheme
- New `read_watermark_header()` function reads the cleartext header without needing a key
- New `cartoload watermark read-header` CLI command prints the cleartext metadata
- Existing `read_watermark()` and CLI `read` are updated to return both header and decrypted payload
- `watermark_bytes()` and `write_watermark()` accept an optional cleartext header parameter

## Capabilities

### New Capabilities
- `watermark-cleartext-header`: Cleartext metadata header embedded alongside the encrypted watermark payload, readable without a key for forensic key lookup

### Modified Capabilities
- `img-watermark`: Extended binary format to include cleartext header; updated write/read/streaming APIs to accept and return header data

## Impact

- **Binary format**: Watermark blob gains a cleartext section before the encrypted section. **BREAKING** for existing watermarked files — old format has no header and will still be readable (graceful fallback)
- **API**: `watermark_bytes()`, `write_watermark()`, `read_watermark()` get new optional `header` parameter / return tuple
- **CLI**: New `read-header` subcommand; existing `read` command output changes to show both header and payload
- **cartoload-server**: `server/apps/orders/downloads/watermark.py` updated to pass `order_public_id` as cleartext header
- **Backward compatibility**: Files watermarked without a header continue to be readable — header is treated as optional
