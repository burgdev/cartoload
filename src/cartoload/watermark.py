"""Forensic watermark for Garmin IMG files.

Embeds an encrypted string into the unused header gap region (0x0400–0x0FFF)
of a Garmin IMG file. The watermark offset within the gap is derived from
HMAC-SHA256(key, map_id), making it unpredictable without the key.

Binary format at the watermark offset:
  [2 bytes] magic "CW" (0x43 0x57)
  [2 bytes] payload_length (uint16 LE) — length of encrypted blob
  [2 bytes] flags (uint16 LE, reserved, 0x0000)
  [N bytes] encrypted blob: nonce(12) + ciphertext + tag(16)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Watermark region boundaries (unused gap between FAT header and FAT entries)
WATERMARK_REGION_START = 0x0400
WATERMARK_REGION_END = 0x1000
WATERMARK_REGION_SIZE = WATERMARK_REGION_END - WATERMARK_REGION_START  # 3,072

# Header format constants
WATERMARK_MAGIC = b"CW"
HEADER_SIZE = 6  # magic(2) + payload_length(2) + flags(2)
NONCE_SIZE = 12
TAG_SIZE = 16
MAX_PLAINTEXT_SIZE = 252

# Maximum possible watermark blob size (used for offset calculation)
# Worst case: header(6) + nonce(12) + max_plaintext(252) + tag(16) = 286
_MAX_BLOB_SIZE = HEADER_SIZE + NONCE_SIZE + MAX_PLAINTEXT_SIZE + TAG_SIZE

# FAT entry constants (for map_id extraction)
FAT_START = 0x1000
FAT_ENTRY_SIZE = 512
FAT_FLAG_ACTIVE = 0x01
MPS_SUBFILE_TYPE = b"MPS"


def _derive_key(raw_key: str | bytes) -> bytes:
    """Derive a 32-byte AES key from any-length input."""
    if isinstance(raw_key, str):
        raw_key = raw_key.encode("utf-8")
    return hashlib.sha256(raw_key).digest()


def _compute_watermark_offset(key: bytes, map_id: int) -> int:
    """Compute the file offset for the watermark.

    Uses a fixed max-blob-size so the offset is deterministic for reading
    without knowing the actual payload size.

    offset = REGION_START + HMAC-SHA256(key, map_id_hex)[:4] % (REGION_SIZE - MAX_BLOB_SIZE)
    Since MAX_BLOB_SIZE <= REGION_SIZE, we use a minimum available of 1.
    """
    map_id_hex = f"{map_id:08X}"
    h = hmac.new(key, map_id_hex.encode("ascii"), hashlib.sha256).digest()
    # Reserve room for the largest possible watermark at the end of the region
    available = WATERMARK_REGION_SIZE - _MAX_BLOB_SIZE  # always > 0
    offset_in_region = int.from_bytes(h[:4], "little") % available
    return WATERMARK_REGION_START + offset_in_region


def _encrypt_payload(plaintext: str, key: bytes) -> bytes:
    """Encrypt a UTF-8 string with AES-256-GCM.

    Returns: nonce(12) + ciphertext + tag(16)
    """
    plaintext_bytes = plaintext.encode("utf-8")
    nonce = os.urandom(NONCE_SIZE)
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
    first_chunk: bytes, map_id: int, payload: str, key: str | bytes
) -> bytes:
    """Inject a watermark into the first 4KB of an IMG file (for streaming).

    Returns a modified copy of first_chunk with the watermark embedded.
    The returned bytes are exactly the same length as the input.
    """
    if len(first_chunk) < WATERMARK_REGION_END:
        raise ValueError(
            f"First chunk must be at least {WATERMARK_REGION_END} bytes, "
            f"got {len(first_chunk)}"
        )
    derived_key = _derive_key(key)
    blob = _build_watermark_blob(payload, derived_key)
    offset = _compute_watermark_offset(derived_key, map_id)

    result = bytearray(first_chunk)
    result[offset : offset + len(blob)] = blob
    return bytes(result)


def write_watermark(img_path: str | Path, payload: str, key: str | bytes) -> None:
    """Write an encrypted watermark into a Garmin IMG file.

    Args:
        img_path: Path to the IMG file.
        payload: UTF-8 string to embed (max 252 bytes).
        key: Encryption key (any length, will be SHA-256 hashed).
    """
    path = Path(img_path)
    derived_key = _derive_key(key)
    blob = _build_watermark_blob(payload, derived_key)

    map_id = _extract_map_id(path)
    offset = _compute_watermark_offset(derived_key, map_id)

    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(blob)


def read_watermark(img_path: str | Path, key: str | bytes) -> str | None:
    """Read and decrypt a watermark from a Garmin IMG file.

    Args:
        img_path: Path to the IMG file.
        key: Encryption key (must match the key used for writing).

    Returns:
        The decrypted watermark string, or None if no watermark found.
    """
    path = Path(img_path)
    derived_key = _derive_key(key)
    map_id = _extract_map_id(path)

    with open(path, "rb") as f:
        f.seek(WATERMARK_REGION_START)
        region = f.read(WATERMARK_REGION_SIZE)

    return _read_watermark_from_region(region, derived_key, map_id)
