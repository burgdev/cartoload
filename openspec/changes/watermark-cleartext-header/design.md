## Context

The cartoload library embeds forensic watermarks into Garmin IMG files using AES-256-GCM encryption in the unused header gap (0x0400–0x0FFF, 3072 bytes). The entire payload is encrypted. The cartoload-server stores per-download watermark keys (with rotation via simple_history) and tracks which key was used per `DownloadEvent`.

**Problem**: When a leaked file is discovered, the forensic analyst must try every key to find the right one, because the watermark is fully encrypted and there's no way to identify which order/download produced the file without first decrypting it.

**Current binary layout** (at HMAC-derived offset within region):
```
[2B] magic "CW"
[2B] payload_length (uint16 LE)
[2B] flags (uint16 LE, 0x0000)
[NB] encrypted blob: nonce(12) + ciphertext + tag(16)
```

## Goals / Non-Goals

**Goals:**
- Add a cleartext metadata header to the watermark region that can be read without a key
- Store `order=PUBLIC_ID` (and similar key-value pairs) in cleartext for forensic key lookup
- Keep the encrypted payload for sensitive data (`user=...:t=...`)
- Maintain backward compatibility — files without a cleartext header remain readable
- Support streaming injection (`watermark_bytes()`) and file-based I/O

**Non-Goals:**
- Hiding the cleartext header (it's intentionally unencrypted for lookup purposes)
- Changing the existing encryption scheme (AES-256-GCM)
- Supporting multiple cleartext headers or nested headers
- Changing the HMAC-based offset derivation

## Decisions

### Decision 1: Dual-blob layout with separate magic bytes

Place the cleartext header at a **fixed offset** (0x0400) and the encrypted blob at the existing HMAC-derived offset. Use a different magic byte for the cleartext header (`CH` = Cleartext Header) to distinguish from encrypted watermarks (`CW`).

**Rationale**: A fixed offset makes the cleartext header trivially discoverable without knowing the key or map_id. Using a different magic avoids confusion during reading. The two blobs are independent — the cleartext header is at 0x0400, the encrypted payload remains at its HMAC-derived position.

**Alternative considered**: Encoding header data inside the encrypted blob. Rejected — defeats the purpose of key-independent reading.

**Alternative considered**: Using a single blob with cleartext prefix. Rejected — the HMAC-derived offset means the header position would vary per file, requiring key knowledge to locate.

### Decision 2: Cleartext header format

```
[2B] magic "CH" (0x43, 0x48)
[2B] header_length (uint16 LE) — total bytes including header fields
[2B] flags (uint16 LE, 0x0001 = version 1)
[NB] UTF-8 key-value pairs separated by ':', e.g. "order=gGeN33ktcb8B42McBQbpwY"
```

Maximum cleartext header size: 128 bytes (well within the 3072-byte region, leaving ample room for the encrypted blob).

**Rationale**: Reuses the same structural pattern as the existing `CW` blob (magic + length + flags + data). Simple key-value format is human-readable and easy to parse.

### Decision 3: API changes — opt-in with backward compatibility

- `write_watermark()` / `watermark_bytes()`: Add optional `header: str | None = None` parameter
- `read_watermark()`: Returns `WatermarkResult` dataclass with `header: str | None` and `payload: str`
- New `read_watermark_header()`: Returns just the cleartext header string (no key needed)
- New `watermark_header_bytes()`: Streaming equivalent for header reading

**Rationale**: Optional parameter means existing callers are unaffected. New return type is a clean break from `str | None`.

## Risks / Trade-offs

- **[Cleartext header is visible to anyone with a hex editor]** → Acceptable: the header only contains the order ID (a shortuuid), not user identity. The sensitive data (user, timestamp) remains encrypted.
- **[Header at fixed offset could be targeted for corruption]** → The `CH` magic provides basic detection. If the header is corrupted, the encrypted payload is still recoverable with the correct key.
- **[Breaking API change for read_watermark return type]** → Return a `WatermarkResult` namedtuple/dataclass that also supports `str()` conversion for basic backward compatibility, or just return `str | None` unchanged and add separate header-read functions. Leaning toward separate functions to avoid breakage entirely.
- **[Region space (3072 bytes) must fit both blobs]** → Cleartext header is capped at 128 bytes. Encrypted blob max is ~286 bytes. Total ~414 bytes, well within limits.
