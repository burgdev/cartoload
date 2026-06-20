## Context

Garmin IMG files produced by cartoload have an unused region at file offsets 0x0400–0x0FFF (3,072 bytes) between the FAT header block and the FAT subfile entries. Garmin devices never read this region — they jump from the FAT header (0x0200) to FAT entries (0x1000).

The current IMG writer writes zeros to this gap. No existing code reads from it.

The map_id is derived deterministically from the layer config (`MD5(layer_id:bounds)[:4] & 0x7FFFFFFF`) and stored in the TRE header and MPS subfile. It is available in the file and can be used to compute a file-specific watermark offset.

## Goals / Non-Goals

**Goals:**
- Embed an encrypted string (up to 252 bytes) into any Garmin IMG file
- The watermark location varies per file and is unpredictable without the encryption key
- Provide a Python API (`write_watermark` / `read_watermark`) for server-side integration
- Provide CLI commands (`cartoload watermark write`, `cartoload watermark read`) for manual use
- Work with streaming — the watermark region is in the first 4KB of the file, so it can be injected into the first chunk before sending

**Non-Goals:**
- Modifying the IMG writer to embed watermarks during build (watermarks are applied post-build)
- Protecting against a determined attacker who rebuilds the IMG from source
- Watermarking any file format other than Garmin IMG
- Key management or rotation (the key is a deployment secret)

## Decisions

### 1. Storage location: header gap 0x0400–0x0FFF

**Decision**: Use the 3,072-byte gap between FAT header (0x0200) and FAT entries (0x1000).

**Alternatives considered**:
- Post-EOI bytes in JPEG tiles (corrupts map on deletion, but complex, and cartoload is open-source anyway)
- TRE+0x9A hash area (only 16 bytes, inside GMP so offset varies)
- FAT reserved bytes (only 14 bytes per entry)

**Rationale**: Fixed absolute offset, large enough, never parsed by devices, streaming-friendly (first 4KB chunk). The open-source nature of cartoload means a determined attacker can always rebuild — the HMAC-offset approach raises the bar enough for practical fraud detection.

### 2. Encryption: AES-256-GCM

**Decision**: Use AES-256-GCM with a random 12-byte nonce per write.

**Rationale**: Provides both confidentiality and authentication. GCM's 16-byte auth tag detects tampering. The `cryptography` library is well-maintained and standard.

### 3. Offset derivation: HMAC-SHA256(key, map_id)

**Decision**: `offset = 0x0400 + (HMAC-SHA256(key, f"{map_id:08X}")[:4] % (3072 - payload_size))`

**Rationale**: Same key + same map_id = same offset (deterministic for reading). Without the key, the offset is unpredictable. The map_id is extracted from the file at read time (TRE+0x74 or MPS+0x07).

### 4. Binary format

**Decision**: Fixed header preceding the encrypted payload:

```
[2 bytes] magic "CW" (0x43 0x57)
[2 bytes] payload_length (uint16 LE) — length of encrypted blob
[2 bytes] flags (uint16 LE, reserved, 0x0000)
[N bytes] encrypted blob: nonce(12) + ciphertext + tag(16)
```

Total overhead: 6 bytes header + 12 bytes nonce + 16 bytes tag = 34 bytes minimum. For a 24-byte plaintext (date + UUID), the total watermark is 6 + 12 + 24 + 16 = 58 bytes.

Maximum payload: 252 bytes of plaintext → 252 + 28 = 280 bytes encrypted → 286 bytes total. Fits comfortably in the 3,072-byte gap.

### 5. Map ID extraction

**Decision**: Read map_id from the MPS subfile at offset MPS+0x07 (uint32 LE). The MPS subfile position is found by scanning FAT entries for type "MPS". Fallback: read from TRE+0x74 (requires locating GMP subfile first).

**Rationale**: MPS is a fixed 98-byte subfile with a known layout. Finding it via FAT is simpler than navigating into the GMP container.

### 6. Key input

**Decision**: Key provided via three mechanisms (in priority order):
1. `--key` CLI parameter (string value)
2. `--key-file` CLI parameter (reads key from file, e.g., a mounted secret)
3. `CARTOLOAD_WATERMARK_KEY` environment variable

The raw key input (from any source) is SHA-256 hashed to derive the actual 32-byte AES key, so any length input is accepted.

### 7. Streaming support via Python API

**Decision**: Add a `watermark_bytes(first_chunk: bytes, map_id: int, payload: str, key: bytes) -> bytes` function that takes the first 4KB of the file as bytes, injects the watermark, and returns the modified chunk. This avoids needing a file path.

**Rationale**: For Django streaming, the server doesn't want to write the watermark to disk — it reads the IMG in chunks and yields them. The first 4KB chunk (bytes 0x0000–0x0FFF) contains the entire watermark region. The server can call `watermark_bytes()` to inject the watermark into that first chunk before yielding it.

```python
# Server-side streaming usage
from cartoload.watermark import watermark_bytes

def stream_img(img_path, payload, key):
    with open(img_path, "rb") as f:
        first_chunk = f.read(4096)  # 0x0000-0x0FFF
        map_id = extract_map_id_from_bytes(first_chunk)  # or pass known map_id
        modified = watermark_bytes(first_chunk, map_id, payload, key)
        yield modified
        while chunk := f.read(32768):
            yield chunk
```

## Risks / Trade-offs

- **[Discoverable by source readers]** → The gap location is documented in code and docs. Acceptable: the goal is fraud detection, not DRM. The HMAC-derived offset within the gap still requires the key to locate.
- **[Deletion by zeroing the gap]** → An attacker could zero 0x0400–0x0FFF. This is detectable (the region should contain the watermark) but not preventable. Acceptable trade-off.
- **[Map ID collision across layers]** → Different layers with same bounds and same name produce the same map_id. This means they'd get the same watermark offset — acceptable since the watermark content differs.
- **[Files not produced by cartoload]** → The gap may not exist or may contain data. The magic bytes "CW" serve as a validity check — reading will fail gracefully if no watermark is present.
