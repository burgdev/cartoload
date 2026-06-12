"""Tests for the forensic watermark module."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest
from click.testing import CliRunner

from cartoload.watermark import (
    CLEARTEXT_HEADER_MAGIC,
    CLEARTEXT_HEADER_SIZE,
    MAX_CLEARTEXT_HEADER_BLOB,
    MAX_CLEARTEXT_HEADER_DATA,
    MAX_PLAINTEXT_SIZE,
    NONCE_SIZE,
    WATERMARK_REGION_END,
    WATERMARK_REGION_START,
    WatermarkResult,
    _build_header_blob,
    _build_watermark_blob,
    _compute_watermark_offset,
    _decrypt_payload,
    _derive_key,
    _encrypt_payload,
    _extract_map_id,
    _read_header_blob,
    extract_map_id_from_bytes,
    read_watermark,
    read_watermark_header,
    read_watermark_header_bytes,
    watermark_bytes,
    write_watermark,
)

# ---------------------------------------------------------------------------
# Helpers for building minimal IMG files for testing
# ---------------------------------------------------------------------------

HEADER_SIZE = 512
FAT_HEADER_BLOCK_SIZE = 512
FAT_START = 0x1000
FAT_ENTRY_SIZE = 512
BLOCK_SIZE = 32768  # standard block size


def _build_minimal_img(map_id: int = 0x12345678) -> bytes:
    """Build a minimal valid-ish IMG file with header, gap, FAT, and MPS."""
    # 1. Header (512 bytes, at 0x0000)
    header = bytearray(HEADER_SIZE)
    header[0x10:0x16] = b"DSKIMG"  # magic
    header[0x40] = 8  # FAT block number
    header[0x41:0x49] = b"GARMIN\x00\x00"
    header[0x61] = 0x09  # e1
    header[0x62] = 0x06  # e2 (block size = 32768)
    header[0x1FE:0x200] = struct.pack("<H", 0xAA55)  # boot sig

    # 2. FAT header block at 0x200 (512 bytes of zeros)
    fat_header = bytearray(FAT_HEADER_BLOCK_SIZE)

    # 3. Gap 0x400-0xFFF (zeros — this is where watermarks go)
    gap = bytearray(0x1000 - 0x400)  # 3,072 bytes

    # 4. FAT entries at 0x1000
    # First: FAT special directory entry
    fat_special = bytearray(FAT_ENTRY_SIZE)
    fat_special[0x00] = 0x01  # active
    fat_special[0x10] = 0x03  # special directory
    struct.pack_into("<H", fat_special, 0x20, 0)  # block 0
    struct.pack_into("<H", fat_special, 0x22, 1)  # block 1
    for i in range(2, 240):
        struct.pack_into("<H", fat_special, 0x20 + i * 2, 0xFFFF)

    # MPS entry: points to a data block containing the MPS subfile
    mps_data_block = 2  # block 2 = offset 0x10000 (2 * 32768)
    fat_mps = bytearray(FAT_ENTRY_SIZE)
    fat_mps[0x00] = 0x01  # active
    fat_mps[0x01:0x09] = b"MAPSOURC"  # name
    fat_mps[0x09:0x0C] = b"MPS"  # type
    struct.pack_into("<I", fat_mps, 0x0C, 98)  # size
    fat_mps[0x10] = 0x00  # normal
    fat_mps[0x11] = 0x00  # part 0
    struct.pack_into("<H", fat_mps, 0x20, mps_data_block)
    for i in range(1, 240):
        struct.pack_into("<H", fat_mps, 0x20 + i * 2, 0xFFFF)

    # 5. MPS subfile data at block 2 (offset 0x10000)
    mps_data = bytearray(98)
    mps_data[0x00:0x02] = b"LE"  # signature
    struct.pack_into("<I", mps_data, 0x07, map_id)  # map_id at MPS+0x07
    mps_data[0x0B:0x21] = b"Test Map\x00" + b"\x00" * 12  # name
    mps_data[0x21:0x29] = f"{map_id:08X}".encode("ascii")  # hex id
    mps_data[0x29] = 0x00

    # Assemble: header + fat_header + gap + FAT entries + padding + MPS data
    pre_data = (
        bytes(header)
        + bytes(fat_header)
        + bytes(gap)
        + bytes(fat_special)
        + bytes(fat_mps)
    )
    data_start = mps_data_block * BLOCK_SIZE  # 0x10000
    padding_needed = data_start - len(pre_data)
    padding = bytearray(max(0, padding_needed))

    # MPS data padded to block size
    mps_padded = bytes(mps_data) + bytearray(BLOCK_SIZE - len(mps_data))

    return pre_data + bytes(padding) + mps_padded


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def img_file(tmp_path: Path) -> Path:
    """Create a temporary IMG file for testing."""
    p = tmp_path / "test.img"
    p.write_bytes(_build_minimal_img())
    return p


@pytest.fixture
def test_key() -> bytes:
    return b"test-secret-key-for-watermarking"


@pytest.fixture
def test_key_derived(test_key: bytes) -> bytes:
    return _derive_key(test_key)


SAMPLE_IMG = Path("tests/data/garmin_samples/IOM.img")

skip_if_no_sample = pytest.mark.skipif(
    not SAMPLE_IMG.exists(),
    reason="Sample IMG file not available",
)


# ---------------------------------------------------------------------------
# 4.1 Test _compute_watermark_offset
# ---------------------------------------------------------------------------


class TestComputeWatermarkOffset:
    def test_same_inputs_same_offset(self, test_key_derived: bytes):
        offset1 = _compute_watermark_offset(test_key_derived, 0x12345678)
        offset2 = _compute_watermark_offset(test_key_derived, 0x12345678)
        assert offset1 == offset2

    def test_different_map_ids_different_offsets(self, test_key_derived: bytes):
        offset1 = _compute_watermark_offset(test_key_derived, 0x12345678)
        offset2 = _compute_watermark_offset(test_key_derived, 0x87654321)
        assert offset1 != offset2

    def test_offset_within_region(self, test_key_derived: bytes):
        offset = _compute_watermark_offset(test_key_derived, 0x12345678)
        # Offset must be after the cleartext header area and before region end
        assert (
            WATERMARK_REGION_START + MAX_CLEARTEXT_HEADER_BLOB
            <= offset
            < WATERMARK_REGION_END
        )

    def test_different_keys_different_offsets(self):
        key1 = _derive_key(b"key-1")
        key2 = _derive_key(b"key-2")
        offset1 = _compute_watermark_offset(key1, 0x12345678)
        offset2 = _compute_watermark_offset(key2, 0x12345678)
        assert offset1 != offset2


# ---------------------------------------------------------------------------
# 4.2 Test _encrypt_payload / _decrypt_payload
# ---------------------------------------------------------------------------


class TestEncryptDecrypt:
    def test_round_trip(self, test_key_derived: bytes):
        plaintext = "2026-05-21|order-abc123"
        encrypted = _encrypt_payload(plaintext, test_key_derived)
        assert encrypted[:NONCE_SIZE] != b"\x00" * NONCE_SIZE  # nonce is nonzero
        decrypted = _decrypt_payload(encrypted, test_key_derived)
        assert decrypted == plaintext

    def test_tamper_detection(self, test_key_derived: bytes):
        from cryptography.exceptions import InvalidTag

        plaintext = "test-payload"
        encrypted = bytearray(_encrypt_payload(plaintext, test_key_derived))
        # Flip a bit in the ciphertext
        encrypted[NONCE_SIZE + 1] ^= 0xFF
        with pytest.raises(InvalidTag):
            _decrypt_payload(bytes(encrypted), test_key_derived)

    def test_wrong_key_fails(self, test_key_derived: bytes):
        from cryptography.exceptions import InvalidTag

        encrypted = _encrypt_payload("secret", test_key_derived)
        wrong_key = _derive_key(b"wrong-key")
        with pytest.raises(InvalidTag):
            _decrypt_payload(encrypted, wrong_key)

    def test_unicode_payload(self, test_key_derived: bytes):
        plaintext = "order-üñíçödé-测试"
        encrypted = _encrypt_payload(plaintext, test_key_derived)
        decrypted = _decrypt_payload(encrypted, test_key_derived)
        assert decrypted == plaintext

    def test_deterministic_encryption(self, test_key_derived: bytes):
        """Same key + plaintext always produces same encrypted output."""
        encrypted1 = _encrypt_payload("deterministic-test", test_key_derived)
        encrypted2 = _encrypt_payload("deterministic-test", test_key_derived)
        assert encrypted1 == encrypted2

    def test_different_plaintexts_differ(self, test_key_derived: bytes):
        encrypted1 = _encrypt_payload("payload-a", test_key_derived)
        encrypted2 = _encrypt_payload("payload-b", test_key_derived)
        assert encrypted1 != encrypted2


# ---------------------------------------------------------------------------
# 4.3 Test write_watermark / read_watermark
# ---------------------------------------------------------------------------


class TestWriteReadWatermark:
    def test_round_trip(self, img_file: Path, test_key: bytes):
        payload = "2026-05-21|order-abc123"
        write_watermark(img_file, payload, test_key)
        result = read_watermark(img_file, test_key)
        assert isinstance(result, WatermarkResult)
        assert result.payload == payload
        assert result.header is None

    def test_file_unchanged_outside_watermark(self, img_file: Path, test_key: bytes):
        original = img_file.read_bytes()
        original_before = original[:WATERMARK_REGION_START]
        original_after = original[WATERMARK_REGION_END:]

        write_watermark(img_file, "test-payload", test_key)

        modified = img_file.read_bytes()
        assert modified[:WATERMARK_REGION_START] == original_before
        assert modified[WATERMARK_REGION_END:] == original_after

    def test_overwrite_watermark(self, img_file: Path, test_key: bytes):
        write_watermark(img_file, "first-watermark", test_key)
        write_watermark(img_file, "second-watermark", test_key)
        result = read_watermark(img_file, test_key)
        assert result.payload == "second-watermark"

    def test_wrong_key_returns_none_payload(self, img_file: Path, test_key: bytes):
        write_watermark(img_file, "secret-payload", test_key)
        result = read_watermark(img_file, b"wrong-key")
        assert result.payload is None

    def test_key_as_string(self, img_file: Path):
        write_watermark(img_file, "payload", "my-string-key")
        result = read_watermark(img_file, "my-string-key")
        assert result.payload == "payload"

    @skip_if_no_sample
    def test_round_trip_on_real_img(self, tmp_path: Path):
        """Test watermark round-trip on a real IMG file."""
        import shutil

        img_copy = tmp_path / "test.img"
        shutil.copy2(SAMPLE_IMG, img_copy)
        key = b"real-img-test-key"
        payload = "2026-05-21|order-xyz789"
        write_watermark(img_copy, payload, key)
        result = read_watermark(img_copy, key)
        assert result.payload == payload


# ---------------------------------------------------------------------------
# 4.4 Test watermark_bytes (streaming)
# ---------------------------------------------------------------------------


class TestWatermarkBytes:
    def test_inject_into_chunk(self, test_key: bytes):
        img_data = _build_minimal_img()
        first_chunk = img_data[:WATERMARK_REGION_END]
        map_id = 0x12345678

        modified = watermark_bytes(first_chunk, map_id, "streaming-test", test_key)

        assert len(modified) == len(first_chunk)
        # Only the watermark region should differ
        assert modified[:WATERMARK_REGION_START] == first_chunk[:WATERMARK_REGION_START]

    def test_streamed_chunk_read_back(self, img_file: Path, test_key: bytes):
        """Write via watermark_bytes, reassemble, read back with read_watermark."""
        img_data = img_file.read_bytes()
        map_id = _extract_map_id(img_file)
        first_chunk = img_data[:WATERMARK_REGION_END]
        rest = img_data[WATERMARK_REGION_END:]

        modified_chunk = watermark_bytes(
            first_chunk, map_id, "streamed-payload", test_key
        )

        # Reassemble
        reassembled = modified_chunk + rest
        img_file.write_bytes(reassembled)

        result = read_watermark(img_file, test_key)
        assert result.payload == "streamed-payload"

    def test_chunk_too_small_raises(self, test_key: bytes):
        with pytest.raises(ValueError, match="at least"):
            watermark_bytes(b"\x00" * 100, 0x12345678, "test", test_key)


# ---------------------------------------------------------------------------
# 4.5 Test edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_payload_too_large(self, test_key_derived: bytes):
        huge_payload = "x" * (MAX_PLAINTEXT_SIZE + 1)
        with pytest.raises(ValueError, match="too large"):
            _build_watermark_blob(huge_payload, test_key_derived)

    def test_no_watermark_returns_none_payload(self, img_file: Path, test_key: bytes):
        result = read_watermark(img_file, test_key)
        assert isinstance(result, WatermarkResult)
        assert result.payload is None
        assert result.header is None

    def test_max_size_payload(self, img_file: Path, test_key: bytes):
        # Max payload that fits
        max_payload = "x" * MAX_PLAINTEXT_SIZE
        write_watermark(img_file, max_payload, test_key)
        result = read_watermark(img_file, test_key)
        assert result.payload == max_payload

    def test_empty_payload(self, img_file: Path, test_key: bytes):
        write_watermark(img_file, "", test_key)
        result = read_watermark(img_file, test_key)
        assert result.payload == ""


# ---------------------------------------------------------------------------
# 5. Cleartext header tests
# ---------------------------------------------------------------------------


class TestCleartextHeaderBlob:
    def test_build_header_blob_format(self):
        """Verify binary layout: magic + total_length + flags + data."""
        blob = _build_header_blob("order=abc123")
        assert blob[:2] == CLEARTEXT_HEADER_MAGIC
        total_length = struct.unpack("<H", blob[2:4])[0]
        assert total_length == CLEARTEXT_HEADER_SIZE + len(b"order=abc123")
        flags = struct.unpack("<H", blob[4:6])[0]
        assert flags == 0x0001
        assert blob[6:] == b"order=abc123"

    def test_roundtrip(self):
        """Build then read a cleartext header blob."""
        header = "order=gGeN33ktcb8B42McBQbpwY"
        blob = _build_header_blob(header)
        result = _read_header_blob(blob)
        assert result == header

    def test_empty_header(self):
        blob = _build_header_blob("")
        assert blob[:2] == CLEARTEXT_HEADER_MAGIC
        result = _read_header_blob(blob)
        assert result == ""

    def test_max_size_header(self):
        header = "x" * MAX_CLEARTEXT_HEADER_DATA
        blob = _build_header_blob(header)
        result = _read_header_blob(blob)
        assert result == header

    def test_oversized_header_raises(self):
        with pytest.raises(ValueError, match="Cleartext header too large"):
            _build_header_blob("x" * (MAX_CLEARTEXT_HEADER_DATA + 1))

    def test_read_no_magic_returns_none(self):
        assert _read_header_blob(b"\x00\x00" + b"\x00" * 20) is None

    def test_read_truncated_data_returns_none(self):
        # Blob claims length 20 but only 8 bytes available
        blob = CLEARTEXT_HEADER_MAGIC + struct.pack("<H", 20) + b"\x00\x00" + b"ab"
        assert _read_header_blob(blob) is None


class TestCleartextHeaderWriteRead:
    def test_write_with_header(self, img_file: Path, test_key: bytes):
        write_watermark(img_file, "secret", test_key, header="order=abc123")
        # Read header without key
        header = read_watermark_header(img_file)
        assert header == "order=abc123"
        # Read everything with key
        result = read_watermark(img_file, test_key)
        assert result.header == "order=abc123"
        assert result.payload == "secret"

    def test_write_without_header_backward_compat(
        self, img_file: Path, test_key: bytes
    ):
        write_watermark(img_file, "legacy-payload", test_key)
        header = read_watermark_header(img_file)
        assert header is None
        result = read_watermark(img_file, test_key)
        assert result.payload == "legacy-payload"
        assert result.header is None

    def test_read_header_legacy_file(self, img_file: Path, test_key: bytes):
        """Legacy watermarked file (no header) returns None for header."""
        write_watermark(img_file, "old-format", test_key)
        assert read_watermark_header(img_file) is None

    def test_watermark_bytes_with_header(self, test_key: bytes):
        img_data = _build_minimal_img()
        map_id = 0x12345678
        first_chunk = img_data[:WATERMARK_REGION_END]
        rest = img_data[WATERMARK_REGION_END:]

        modified = watermark_bytes(
            first_chunk, map_id, "streaming", test_key, header="order=stream123"
        )
        assert len(modified) == len(first_chunk)

        # Verify header readable from bytes
        header = read_watermark_header_bytes(modified)
        assert header == "order=stream123"

        # Verify full roundtrip via reassembled file
        tmp = Path("/tmp/test_header_streaming.img")
        tmp.write_bytes(modified + rest)
        try:
            result = read_watermark(tmp, test_key)
            assert result.header == "order=stream123"
            assert result.payload == "streaming"
        finally:
            tmp.unlink(missing_ok=True)

    def test_watermark_header_bytes_chunk_too_small(self):
        assert read_watermark_header_bytes(b"\x00" * 100) is None

    def test_watermark_result_dataclass(self, img_file: Path, test_key: bytes):
        write_watermark(img_file, "payload", test_key, header="order=DC")
        result = read_watermark(img_file, test_key)
        assert isinstance(result, WatermarkResult)
        assert result.header == "order=DC"
        assert result.payload == "payload"

    def test_oversized_header_raises(self, img_file: Path, test_key: bytes):
        with pytest.raises(ValueError, match="Cleartext header too large"):
            write_watermark(
                img_file,
                "payload",
                test_key,
                header="x" * (MAX_CLEARTEXT_HEADER_DATA + 1),
            )


# ---------------------------------------------------------------------------
# 4.6 Test CLI commands
# ---------------------------------------------------------------------------


class TestCLI:
    def test_write_and_read(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()
        key = "cli-test-key"
        payload = "2026-05-21|order-cli-test"

        result = runner.invoke(
            main, ["watermark", "write", str(img_file), payload, "--key", key]
        )
        assert result.exit_code == 0, result.output
        assert "Watermark written" in result.output

        result = runner.invoke(main, ["watermark", "read", str(img_file), "--key", key])
        assert result.exit_code == 0, result.output
        assert payload in result.output

    def test_write_no_key_fails(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["watermark", "write", str(img_file), "payload"],
            env={k: v for k, v in os.environ.items() if k != "CARTOLOAD_WATERMARK_KEY"},
        )
        assert result.exit_code != 0
        assert "No key provided" in result.output

    def test_read_no_watermark(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main, ["watermark", "read", str(img_file), "--key", "some-key"]
        )
        assert result.exit_code == 0
        assert "No watermark found" in result.output

    def test_write_with_key_file(self, img_file: Path, tmp_path: Path):
        from cartoload.cli import main

        key_file = tmp_path / "key.txt"
        key_file.write_text("file-based-key")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "watermark",
                "write",
                str(img_file),
                "keyfile-test",
                "--key-file",
                str(key_file),
            ],
        )
        assert result.exit_code == 0, result.output

        result = runner.invoke(
            main,
            ["watermark", "read", str(img_file), "--key-file", str(key_file)],
        )
        assert result.exit_code == 0, result.output
        assert "keyfile-test" in result.output

    def test_write_with_env_var(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()
        env = {**os.environ, "CARTOLOAD_WATERMARK_KEY": "env-key-123"}

        result = runner.invoke(
            main, ["watermark", "write", str(img_file), "env-test"], env=env
        )
        assert result.exit_code == 0, result.output

        result = runner.invoke(main, ["watermark", "read", str(img_file)], env=env)
        assert result.exit_code == 0, result.output
        assert "env-test" in result.output

    def test_key_priority(self, img_file: Path, tmp_path: Path):
        """--key takes priority over --key-file and env var."""
        from cartoload.cli import main

        key_file = tmp_path / "key.txt"
        key_file.write_text("file-key")

        runner = CliRunner()
        env = {**os.environ, "CARTOLOAD_WATERMARK_KEY": "env-key"}

        # Write with --key (should take priority)
        result = runner.invoke(
            main,
            ["watermark", "write", str(img_file), "priority-test", "--key", "cli-key"],
            env=env,
        )
        assert result.exit_code == 0

        # Read with same --key
        result = runner.invoke(
            main,
            ["watermark", "read", str(img_file), "--key", "cli-key"],
            env=env,
        )
        assert result.exit_code == 0
        assert "priority-test" in result.output

    def test_write_and_read_with_header(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()
        key = "cli-header-key"

        result = runner.invoke(
            main,
            [
                "watermark",
                "write",
                str(img_file),
                "secret-payload",
                "--key",
                key,
                "--header",
                "order=abc123",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Watermark written" in result.output

        result = runner.invoke(main, ["watermark", "read", str(img_file), "--key", key])
        assert result.exit_code == 0, result.output
        assert "Header:  order=abc123" in result.output
        assert "Payload: secret-payload" in result.output

    def test_read_header_subcommand(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()
        key = "read-header-key"

        # No header yet
        result = runner.invoke(main, ["watermark", "read-header", str(img_file)])
        assert result.exit_code == 0, result.output
        assert "No cleartext header found" in result.output

        # Write with header
        runner.invoke(
            main,
            [
                "watermark",
                "write",
                str(img_file),
                "payload",
                "--key",
                key,
                "--header",
                "order=XYZ789",
            ],
        )

        # Read header without key
        result = runner.invoke(main, ["watermark", "read-header", str(img_file)])
        assert result.exit_code == 0, result.output
        assert "order=XYZ789" in result.output

    def test_read_without_key_shows_header_only(self, img_file: Path):
        from cartoload.cli import main

        runner = CliRunner()

        # Write with header
        runner.invoke(
            main,
            [
                "watermark",
                "write",
                str(img_file),
                "encrypted-data",
                "--key",
                "test-key",
                "--header",
                "order=HEAD123",
            ],
        )

        # Read without key
        result = runner.invoke(
            main,
            ["watermark", "read", str(img_file)],
            env={k: v for k, v in os.environ.items() if k != "CARTOLOAD_WATERMARK_KEY"},
        )
        assert result.exit_code == 0, result.output
        assert "Header:  order=HEAD123" in result.output
        assert "key required to decrypt" in result.output


# ---------------------------------------------------------------------------
# Test extract_map_id_from_bytes
# ---------------------------------------------------------------------------


class TestExtractMapId:
    def test_extracts_from_minimal_img(self):
        map_id = 0xAABBCCDD
        img_data = _build_minimal_img(map_id)
        result = extract_map_id_from_bytes(img_data)
        assert result == map_id

    def test_raises_on_invalid_data(self):
        with pytest.raises(ValueError, match="Could not find MPS"):
            extract_map_id_from_bytes(b"\x00" * 4096)

    @skip_if_no_sample
    def test_extracts_from_real_img(self):
        img_data = SAMPLE_IMG.read_bytes()
        map_id = extract_map_id_from_bytes(img_data)
        assert 0 < map_id < 0xFFFFFFFF
