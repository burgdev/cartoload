## 1. Dependencies

- [x] 1.1 Add `cryptography` package to project dependencies (`uv add cryptography`)

## 2. Core Watermark Module

- [x] 2.1 Create `src/cartoload/watermark.py` with constants: `WATERMARK_REGION_START = 0x0400`, `WATERMARK_REGION_END = 0x1000`, `WATERMARK_MAGIC = b"CW"`, `MAX_PLAINTEXT_SIZE = 252`
- [x] 2.2 Implement `_extract_map_id(img_path: Path) -> int` — scan FAT entries for MPS subfile type, read uint32 LE at MPS+0x07
- [x] 2.3 Implement `_compute_watermark_offset(key: bytes, map_id: int, payload_size: int) -> int` — HMAC-SHA256(key, f"{map_id:08X}")[:4] % (3072 - payload_size) + 0x0400
- [x] 2.4 Implement `_encrypt_payload(plaintext: str, key: bytes) -> bytes` — AES-256-GCM, random 12-byte nonce, prepend nonce to ciphertext+tag
- [x] 2.5 Implement `_decrypt_payload(encrypted: bytes, key: bytes) -> str` — extract nonce, decrypt, verify tag, return UTF-8 string
- [x] 2.6 Implement `write_watermark(img_path: str | Path, payload: str, key: str | bytes)` — validate size, encrypt, compute offset, seek+write into file
- [x] 2.7 Implement `read_watermark(img_path: str | Path, key: str | bytes) -> str | None` — extract map_id, compute offset, read header, decrypt, return string or None
- [x] 2.8 Implement `watermark_bytes(first_chunk: bytes, map_id: int, payload: str, key: bytes) -> bytes` — inject watermark into a 4KB bytes object without file I/O (for streaming)
- [x] 2.9 Implement `extract_map_id_from_bytes(data: bytes) -> int` — parse FAT entries from raw bytes to find MPS subfile offset, then read map_id from MPS+0x07 (for streaming use where map_id isn't known)

## 3. CLI Commands

- [x] 3.1 Add `watermark` command group to the cartoload CLI (in the CLI entry point module)
- [x] 3.2 Implement `cartoload watermark write <img-file> <string>` subcommand — read key from `--key` param, `--key-file` param, or `CARTOLOAD_WATERMARK_KEY` env var, call `write_watermark`
- [x] 3.3 Implement `cartoload watermark read <img-file>` subcommand — read key from `--key` param, `--key-file` param, or `CARTOLOAD_WATERMARK_KEY` env var, call `read_watermark`, print result

## 4. Tests

- [x] 4.1 Test `_compute_watermark_offset` — same inputs produce same offset, different map_ids produce different offsets
- [x] 4.2 Test `_encrypt_payload` / `_decrypt_payload` — round-trip encryption, tamper detection (corrupted ciphertext raises exception)
- [x] 4.3 Test `write_watermark` / `read_watermark` — write then read on a real IMG file, verify round-trip, verify rest of file unchanged
- [x] 4.4 Test `watermark_bytes` — inject into 4KB chunk, verify only watermark region changed, verify round-trip with `read_watermark` on reassembled file
- [x] 4.5 Test edge cases — payload too large raises ValueError, no watermark returns None, missing key raises error
- [x] 4.6 Test CLI commands — `cartoload watermark write` and `cartoload watermark read` via subprocess or click test runner, test `--key-file` and `CARTOLOAD_WATERMARK_KEY` env var

## 5. Verification

- [x] 5.1 Run `just check` and `just check types` to verify formatting, linting, and type correctness
- [x] 5.2 Run `just test` to verify all tests pass
