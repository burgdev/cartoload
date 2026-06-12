## 1. Cleartext Header Binary Format

- [ ] 1.1 Add `HEADER_MAGIC = b"CH"`, `MAX_HEADER_SIZE = 128`, and related constants to `watermark.py`
- [ ] 1.2 Implement `_build_header_blob(header: str) -> bytes` — builds the cleartext header binary (magic + length + flags + data)
- [ ] 1.3 Implement `_read_header_blob(first_chunk: bytes) -> str | None` — reads cleartext header from fixed offset 0x0400 in chunk data

## 2. Write API Changes

- [ ] 2.1 Add optional `header: str | None = None` parameter to `write_watermark()` — writes cleartext header blob at 0x0400 when provided
- [ ] 2.2 Add optional `header: str | None = None` parameter to `watermark_bytes()` — injects cleartext header at 0x0400 when provided
- [ ] 2.3 Add validation: raise `ValueError` if header exceeds 120 bytes UTF-8
- [ ] 2.4 Add validation: raise `ValueError` if header blob + encrypted blob would overlap or exceed region

## 3. Read API Changes

- [ ] 3.1 Add `WatermarkResult` dataclass with `header: str | None` and `payload: str | None` fields
- [ ] 3.2 Update `read_watermark()` to return `WatermarkResult` — reads both cleartext header (if present) and decrypted payload
- [ ] 3.3 Add `read_watermark_header(img_path) -> str | None` — reads only the cleartext header, no key required
- [ ] 3.4 Add `read_watermark_header_bytes(first_chunk: bytes) -> str | None` — streaming version, no key required

## 4. CLI Changes

- [ ] 4.1 Add `read-header` subcommand to `cartoload watermark` group — prints cleartext header without key
- [ ] 4.2 Update `read` subcommand to display both header and payload when present, and show header-only when no key is provided

## 5. Tests

- [ ] 5.1 Test `_build_header_blob` / `_read_header_blob` roundtrip
- [ ] 5.2 Test `write_watermark` with header, verify `read_watermark_header` returns header
- [ ] 5.3 Test `write_watermark` without header (backward compat), verify `read_watermark_header` returns None
- [ ] 5.4 Test `watermark_bytes` with header, verify header readable from result
- [ ] 5.5 Test `read_watermark_header` on legacy file (no header) returns None
- [ ] 5.6 Test `read_watermark` returns `WatermarkResult` with both fields
- [ ] 5.7 Test `ValueError` on oversized header
- [ ] 5.8 Test CLI `read-header` subcommand
- [ ] 5.9 Test CLI `read` subcommand with header + payload display
