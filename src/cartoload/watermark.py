"""Forensic watermark for Garmin IMG files.

Embeds an encrypted string into the unused header gap region (0x0400–0x0FFF)
of a Garmin IMG file. The watermark offset within the gap is derived from
HMAC-SHA256(key, map_id), making it unpredictable without the key.

Optionally embeds a cleartext header at fixed offset 0x0400 for key-independent
forensic identification (e.g. order ID lookup).

Binary format — cleartext header at fixed offset 0x0400:
  [2 bytes] magic "CH" (0x43 0x48)
  [2 bytes] header_length (uint16 LE) — total blob size including header fields
  [2 bytes] flags (uint16 LE, 0x0001 = version 1)
  [N bytes] UTF-8 key-value metadata, e.g. "order=gGeN33kt"

Binary format — encrypted payload at HMAC-derived offset:
  [2 bytes] magic "CW" (0x43 0x57)
  [2 bytes] payload_length (uint16 LE) — length of encrypted blob
  [2 bytes] flags (uint16 LE, reserved, 0x0000)
  [N bytes] encrypted blob: nonce(12) + ciphertext + tag(16)
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Watermark region boundaries (unused gap between FAT header and FAT entries)
WATERMARK_REGION_START = 0x0400
WATERMARK_REGION_END = 0x1000
WATERMARK_REGION_SIZE = WATERMARK_REGION_END - WATERMARK_REGION_START  # 3,072

# Encrypted payload format constants
WATERMARK_MAGIC = b"CW"
HEADER_SIZE = 6  # magic(2) + payload_length(2) + flags(2)
NONCE_SIZE = 12
TAG_SIZE = 16
MAX_PLAINTEXT_SIZE = 252

# Cleartext header format constants
CLEARTEXT_HEADER_MAGIC = b"CH"
CLEARTEXT_HEADER_SIZE = 6  # magic(2) + header_length(2) + flags(2)
MAX_CLEARTEXT_HEADER_DATA = 120  # max UTF-8 bytes for the header string
MAX_CLEARTEXT_HEADER_BLOB = 128  # CLEARTEXT_HEADER_SIZE + MAX_CLEARTEXT_HEADER_DATA

# Maximum possible watermark blob size (used for offset calculation)
# Worst case: header(6) + nonce(12) + max_plaintext(252) + tag(16) = 286
_MAX_BLOB_SIZE = HEADER_SIZE + NONCE_SIZE + MAX_PLAINTEXT_SIZE + TAG_SIZE

# FAT entry constants (for map_id extraction)
FAT_START = 0x1000
FAT_ENTRY_SIZE = 512
FAT_FLAG_ACTIVE = 0x01
MPS_SUBFILE_TYPE = b"MPS"


@dataclass
class WatermarkResult:
    """Result of reading a watermark from an IMG file."""

    header: str | None
    payload: str | None


def _derive_key(raw_key: str | bytes) -> bytes:
    """Derive a 32-byte AES key from any-length input."""
    if isinstance(raw_key, str):
        raw_key = raw_key.encode("utf-8")
    return hashlib.sha256(raw_key).digest()


def _compute_watermark_offset(key: bytes, map_id: int) -> int:
    """Compute the file offset for the encrypted watermark blob.

    The offset is placed after the cleartext header area (first 128 bytes
    of the region) and before the region end minus the max blob size.

    offset = REGION_START + HEADER_RESERVED + HMAC[:4] % available
    where available = REGION_SIZE - HEADER_RESERVED - MAX_BLOB_SIZE
    """
    map_id_hex = f"{map_id:08X}"
    h = hmac.new(key, map_id_hex.encode("ascii"), hashlib.sha256).digest()
    # Reserve cleartext header area at start, max blob at end
    available = WATERMARK_REGION_SIZE - MAX_CLEARTEXT_HEADER_BLOB - _MAX_BLOB_SIZE
    offset_in_region = (
        MAX_CLEARTEXT_HEADER_BLOB + int.from_bytes(h[:4], "little") % available
    )
    return WATERMARK_REGION_START + offset_in_region


def _derive_nonce(key: bytes, plaintext_bytes: bytes) -> bytes:
    """Derive a deterministic 12-byte nonce from key and plaintext.

    Uses HMAC-SHA256 truncated to 12 bytes. Safe as long as the same
    (key, nonce) pair is never reused for *different* plaintexts — which
    is guaranteed here since the nonce is derived from the plaintext itself.
    """
    return hmac.new(key, plaintext_bytes, hashlib.sha256).digest()[:NONCE_SIZE]


def _encrypt_payload(plaintext: str, key: bytes) -> bytes:
    """Encrypt a UTF-8 string with AES-256-GCM.

    Returns: nonce(12) + ciphertext + tag(16)

    The nonce is deterministic (derived from key + plaintext) so that
    identical inputs always produce identical encrypted output. This
    enables resumable downloads via HTTP Range requests — the watermark
    bytes are the same regardless of how many requests assemble the file.
    """
    plaintext_bytes = plaintext.encode("utf-8")
    nonce = _derive_nonce(key, plaintext_bytes)
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext_bytes, None)
    return nonce + ciphertext_with_tag


def _decrypt_payload(encrypted: bytes, key: bytes) -> str:
    """Decrypt an AES-256-GCM encrypted payload.

    Input: nonce(12) + ciphertext + tag(16)
    Returns: UTF-8 string.
    Raises InvalidTag if data is corrupted or wrong key.
    """
    nonce = encrypted[:NONCE_SIZE]
    ciphertext_with_tag = encrypted[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    return plaintext_bytes.decode("utf-8")


def _build_header_blob(header: str) -> bytes:
    """Build the cleartext header blob.

    Format: magic "CH" (2B) + header_length (2B, uint16 LE) + flags (2B) + UTF-8 data.
    header_length is the total blob size (CLEARTEXT_HEADER_SIZE + len(data)).
    """
    data = header.encode("utf-8")
    if len(data) > MAX_CLEARTEXT_HEADER_DATA:
        raise ValueError(
            f"Cleartext header too large: {len(data)} bytes "
            f"(max {MAX_CLEARTEXT_HEADER_DATA})"
        )
    total_length = CLEARTEXT_HEADER_SIZE + len(data)
    return (
        CLEARTEXT_HEADER_MAGIC
        + struct.pack("<H", total_length)
        + struct.pack("<H", 0x0001)
        + data
    )


def _read_header_blob(data: bytes) -> str | None:
    """Read a cleartext header blob from raw bytes at offset 0x0400.

    Returns the header string, or None if no valid header is present.
    """
    if len(data) < CLEARTEXT_HEADER_SIZE:
        return None
    magic = data[:2]
    if magic != CLEARTEXT_HEADER_MAGIC:
        return None
    total_length = struct.unpack("<H", data[2:4])[0]
    if total_length < CLEARTEXT_HEADER_SIZE or total_length > len(data):
        return None
    # flags = struct.unpack("<H", data[4:6])[0]  # not used yet
    header_data = data[CLEARTEXT_HEADER_SIZE:total_length]
    try:
        return header_data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _build_watermark_blob(plaintext: str, key: bytes) -> bytes:
    """Build the complete watermark blob: header + encrypted payload."""
    if len(plaintext.encode("utf-8")) > MAX_PLAINTEXT_SIZE:
        raise ValueError(
            f"Payload too large: {len(plaintext.encode('utf-8'))} bytes "
            f"(max {MAX_PLAINTEXT_SIZE})"
        )
    encrypted = _encrypt_payload(plaintext, key)
    header = WATERMARK_MAGIC + struct.pack("<H", len(encrypted)) + b"\x00\x00"
    return header + encrypted


def _read_watermark_from_region(region: bytes, key: bytes, map_id: int) -> str | None:
    """Read watermark from the region bytes at the computed offset."""
    offset_in_region = _compute_watermark_offset(key, map_id) - WATERMARK_REGION_START

    if offset_in_region + HEADER_SIZE > len(region):
        return None

    magic = region[offset_in_region : offset_in_region + 2]
    if magic != WATERMARK_MAGIC:
        return None

    payload_length = struct.unpack(
        "<H", region[offset_in_region + 2 : offset_in_region + 4]
    )[0]
    if offset_in_region + HEADER_SIZE + payload_length > len(region):
        return None

    encrypted = region[
        offset_in_region + HEADER_SIZE : offset_in_region + HEADER_SIZE + payload_length
    ]
    try:
        return _decrypt_payload(encrypted, key)
    except Exception:
        return None


def extract_map_id_from_bytes(data: bytes) -> int:
    """Extract map_id from raw IMG file bytes.

    Scans FAT entries starting at FAT_START (0x1000) to find the MPS subfile,
    then reads the map_id at MPS+0x07 (uint32 LE).

    Falls back to reading map_id from the first GMP FAT entry name (hex string).

    The data must contain at least FAT_START + enough FAT entries.
    For streaming use, read at least the first 1MB of the file.
    """
    offset = FAT_START
    first_gmp_name: str | None = None
    while offset + FAT_ENTRY_SIZE <= len(data):
        entry = data[offset : offset + FAT_ENTRY_SIZE]
        flag = entry[0]
        if flag != FAT_FLAG_ACTIVE:
            break
        subfile_type = entry[0x09:0x0C]
        if subfile_type == MPS_SUBFILE_TYPE:
            # Found MPS — read map_id from the first data block
            # entry[0x20:] contains block numbers (uint16 LE)
            if len(entry) < 0x22:
                break
            block_number = struct.unpack("<H", entry[0x20:0x22])[0]
            # Block size from header: 2^e1 * 2^e2
            e1 = data[0x61]
            e2 = data[0x62]
            block_size = (1 << e1) * (1 << e2)
            mps_offset = block_number * block_size
            if mps_offset + 0x0B <= len(data):
                map_id = struct.unpack(
                    "<I", data[mps_offset + 0x07 : mps_offset + 0x0B]
                )[0]
                return map_id
            break
        if subfile_type == b"GMP" and first_gmp_name is None:
            first_gmp_name = entry[0x01:0x09].decode("ascii", errors="ignore").strip()
        offset += FAT_ENTRY_SIZE

    # Fallback: read map_id from the first GMP FAT entry name (hex string)
    if first_gmp_name:
        try:
            return int(first_gmp_name, 16)
        except ValueError:
            pass

    raise ValueError("Could not find MPS subfile or extract map_id from provided data")


def _extract_map_id(img_path: str | Path) -> int:
    """Extract map_id from a Garmin IMG file on disk."""
    path = Path(img_path)
    with open(path, "rb") as f:
        data = f.read(1024 * 1024)  # 1MB is plenty for FAT + MPS
    return extract_map_id_from_bytes(data)


def watermark_bytes(
    first_chunk: bytes,
    map_id: int,
    payload: str,
    key: str | bytes,
    header: str | None = None,
) -> bytes:
    """Inject a watermark into the first 4KB of an IMG file (for streaming).

    Returns a modified copy of first_chunk with the watermark (and optional
    cleartext header) embedded. The returned bytes are exactly the same
    length as the input.
    """
    if len(first_chunk) < WATERMARK_REGION_END:
        raise ValueError(
            f"First chunk must be at least {WATERMARK_REGION_END} bytes, "
            f"got {len(first_chunk)}"
        )
    derived_key = _derive_key(key)

    header_blob = b""
    if header is not None:
        header_blob = _build_header_blob(header)

    blob = _build_watermark_blob(payload, derived_key)
    offset = _compute_watermark_offset(derived_key, map_id)

    result = bytearray(first_chunk)
    if header_blob:
        result[WATERMARK_REGION_START : WATERMARK_REGION_START + len(header_blob)] = (
            header_blob
        )
    result[offset : offset + len(blob)] = blob
    return bytes(result)


def write_watermark(
    img_path: str | Path,
    payload: str,
    key: str | bytes,
    header: str | None = None,
) -> None:
    """Write an encrypted watermark (and optional cleartext header) into a Garmin IMG file.

    Args:
        img_path: Path to the IMG file.
        payload: UTF-8 string to embed (max 252 bytes).
        key: Encryption key (any length, will be SHA-256 hashed).
        header: Optional cleartext header string (max 120 bytes UTF-8).
    """
    path = Path(img_path)
    derived_key = _derive_key(key)
    blob = _build_watermark_blob(payload, derived_key)

    map_id = _extract_map_id(path)
    offset = _compute_watermark_offset(derived_key, map_id)

    header_blob = b""
    if header is not None:
        header_blob = _build_header_blob(header)

    with open(path, "r+b") as f:
        if header_blob:
            f.seek(WATERMARK_REGION_START)
            f.write(header_blob)
        f.seek(offset)
        f.write(blob)


def read_watermark(img_path: str | Path, key: str | bytes) -> WatermarkResult:
    """Read and decrypt a watermark from a Garmin IMG file.

    Args:
        img_path: Path to the IMG file.
        key: Encryption key (must match the key used for writing).

    Returns:
        A WatermarkResult with the cleartext header (if present) and the
        decrypted payload (if present).
    """
    path = Path(img_path)
    derived_key = _derive_key(key)
    map_id = _extract_map_id(path)

    with open(path, "rb") as f:
        f.seek(WATERMARK_REGION_START)
        region = f.read(WATERMARK_REGION_SIZE)

    header = _read_header_blob(region)
    payload = _read_watermark_from_region(region, derived_key, map_id)
    return WatermarkResult(header=header, payload=payload)


def read_watermark_header(img_path: str | Path) -> str | None:
    """Read only the cleartext header from a Garmin IMG file (no key required).

    Args:
        img_path: Path to the IMG file.

    Returns:
        The cleartext header string, or None if no header is present.
    """
    path = Path(img_path)
    with open(path, "rb") as f:
        f.seek(WATERMARK_REGION_START)
        region = f.read(MAX_CLEARTEXT_HEADER_BLOB)
    return _read_header_blob(region)


def read_watermark_header_bytes(first_chunk: bytes) -> str | None:
    """Read the cleartext header from the first chunk of an IMG file (no key required).

    Args:
        first_chunk: At least WATERMARK_REGION_START + MAX_CLEARTEXT_HEADER_BLOB bytes.

    Returns:
        The cleartext header string, or None if no header is present.
    """
    needed = WATERMARK_REGION_START + MAX_CLEARTEXT_HEADER_BLOB
    if len(first_chunk) < needed:
        return None
    region = first_chunk[
        WATERMARK_REGION_START : WATERMARK_REGION_START + MAX_CLEARTEXT_HEADER_BLOB
    ]
    return _read_header_blob(region)
