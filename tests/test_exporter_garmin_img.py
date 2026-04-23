"""Tests for Garmin IMG exporter: header, FAT, tile encoding, pyramid, attribution, size limits.

Markers:
    gmt  — requires the ``gmt`` (GMapTool) binary on PATH
    gdal — requires GDAL/rasterio system libraries
"""

from __future__ import annotations

import io
import shutil
import struct
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from cartoload.config import LayerConfig
from cartoload.exporters.garmin_img_model import (
    IMGFile,
    IMGHeader,
    SubfileHeader,
    SubfileType,
    TileRecord,
    ZoomLevel,
)
from cartoload.exporters.garmin_img_writer import (
    BLOCK_SIZE,
    FAT_BLOCK_NUMBER,
    FAT_START,
    FAT_FLAG_ACTIVE,
    FAT_FLAG_SPECIAL,
    FAT_UNUSED_BLOCK,
    FATWriter,
    IMGHeaderWriter,
    IMGWriter,
    LayoutComputer,
    MAX_TILE_SIZE,
    SubfileLayout,
    TileEncoder,
    _blocks_needed,
    _deg_to_garmin,
    _fat_blocks_for_data_blocks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_header(**overrides) -> IMGHeader:
    defaults = dict(
        magic="DSKIMG",
        format_version=2,
        creation_date=datetime(2022, 4, 16, 15, 3, 56),
        creator="GARMIN",
        map_name="TestMap",
    )
    defaults.update(overrides)
    return IMGHeader(**defaults)


def _make_img_file(**overrides) -> IMGFile:
    header = overrides.pop("header", _make_header())
    defaults = dict(
        header=header,
        bounds_north=47.5,
        bounds_south=46.5,
        bounds_west=8.0,
        bounds_east=9.0,
        description="Test Map",
        copyright_string="(c) test",
        map_id=0x09C102B0,
        zoom_levels=[],
        tiles=[],
    )
    defaults.update(overrides)
    return IMGFile(**defaults)


def _make_compressed_tiles(
    tile_count: int = 3, tile_size: int = 1024
) -> dict[int, list[bytes]]:
    """Create fake compressed tile data for testing."""
    return {
        12: [b"\xff\xd8\xff\xe0" + b"\x00" * (tile_size - 4)] * tile_count,
    }


# ---------------------------------------------------------------------------
# Task 1.2 – BaseExporter ABC
# ---------------------------------------------------------------------------


class TestBaseExporterABC:
    def test_cannot_instantiate_without_methods(self):
        from cartoload.exporters.base import BaseExporter

        with pytest.raises(TypeError, match="abstract methods"):
            BaseExporter()

    def test_incomplete_subclass_raises(self):
        from cartoload.exporters.base import BaseExporter

        class Partial(BaseExporter):
            @property
            def name(self):
                return "partial"

        with pytest.raises(TypeError, match="export"):
            Partial()


# ---------------------------------------------------------------------------
# IMG Header serialization
# ---------------------------------------------------------------------------


class TestIMGHeaderSerialization:
    def test_magic_bytes(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert data[0x10:0x16] == b"DSKIMG"
        assert data[0x16] == 0x00  # null terminator

    def test_format_version_byte(self):
        header = _make_header(format_version=2)
        data = IMGHeaderWriter.serialize(header)
        assert data[0x17] == 0x02

    def test_creation_date_encoding(self):
        dt = datetime(2022, 4, 16, 15, 3, 56)
        header = _make_header(creation_date=dt)
        data = IMGHeaderWriter.serialize(header)
        # Year LE
        year = struct.unpack_from("<H", data, 0x39)[0]
        assert year == 2022
        assert data[0x3B] == 4  # month
        assert data[0x3C] == 16  # day
        assert data[0x3D] == 15  # hour
        assert data[0x3E] == 3  # minute
        assert data[0x3F] == 56  # second

    def test_fat_block_number_at_0x40(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert data[0x40] == FAT_BLOCK_NUMBER  # 8

    def test_creator_string_at_0x41(self):
        header = _make_header(creator="GARMIN")
        data = IMGHeaderWriter.serialize(header)
        assert data[0x41:0x47] == b"GARMIN"

    def test_map_name_at_0x49(self):
        header = _make_header(map_name="TestMap")
        data = IMGHeaderWriter.serialize(header)
        # Map description is 20 bytes at 0x49-0x5C, space-padded
        desc = data[0x49:0x5D]
        assert desc[:7] == b"TestMap"
        assert desc[7] == ord(" ")  # space-padded

    def test_boot_signature(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55

    def test_header_is_512_bytes(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert len(data) == 512

    def test_xor_byte_at_0x00(self):
        header = _make_header(xor_byte=0x00)
        data = IMGHeaderWriter.serialize(header)
        assert data[0x00] == 0x00

    def test_block_size_exponents(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert data[0x61] == 0x09  # E1
        assert data[0x62] == 0x06  # E2 → 512 * 2^6 = 32768

    def test_checksum_at_0x0F(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        # Sum of bytes 0x00-0x0F should be 0 mod 256
        byte_sum = sum(data[0x00:0x10])
        assert byte_sum % 256 == 0

    def test_partition_table_at_0x1BE(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        # System type should be 0xFF
        assert data[0x1C2] == 0xFF


# ---------------------------------------------------------------------------
# FAT entry serialization
# ---------------------------------------------------------------------------


class TestFATEntrySerialization:
    def test_special_directory_entry(self):
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="09C102B0",
            start_offset=BLOCK_SIZE * 10,
            data_size=12345,
        )
        buf = io.BytesIO()
        FATWriter._write_special_entry(buf, [layout], FAT_START)
        data = buf.getvalue()
        assert len(data) == 512

        # Flag: active
        assert data[0x00] == FAT_FLAG_ACTIVE
        # Name: 8 spaces
        assert data[0x01:0x09] == b"        "
        # Type: 3 spaces
        assert data[0x09:0x0C] == b"   "
        # Flag2: special
        assert data[0x10] == FAT_FLAG_SPECIAL

    def test_subfile_fat_entry(self):
        data_size = 12345
        start_block = 10
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="09C102B0",
            start_offset=BLOCK_SIZE * start_block,
            data_size=data_size,
        )
        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()

        # Flag: active
        assert data[0x00] == FAT_FLAG_ACTIVE
        # Name
        assert data[0x01:0x09] == b"09C102B0"
        # Type
        assert data[0x09:0x0C] == b"GMP"
        # Size (LE uint32 at offset 0x0C)
        size = struct.unpack_from("<I", data, 0x0C)[0]
        assert size == data_size
        # Part number
        assert data[0x11] == 0

    def test_block_sequence_in_fat_entry(self):
        # Create a subfile with 3 data blocks (32KB each)
        # Starting at offset = 10 * 32KB
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="TEST",
            start_offset=BLOCK_SIZE * 10,
            data_size=BLOCK_SIZE * 3,
        )
        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()

        # FAT uses 32KB logical blocks in the block chain
        # start_block = 10, num_blocks = 3, so blocks 10, 11, 12
        block0 = struct.unpack_from("<H", data, 0x20)[0]
        block1 = struct.unpack_from("<H", data, 0x22)[0]
        block2 = struct.unpack_from("<H", data, 0x24)[0]
        assert block0 == 10
        assert block1 == 11
        assert block2 == 12
        # Remaining blocks should be 0xFFFF
        block3 = struct.unpack_from("<H", data, 0x26)[0]
        assert block3 == FAT_UNUSED_BLOCK

    def test_mps_fat_entry(self):
        layout = SubfileLayout(
            subfile_type=SubfileType.MPS,
            name="MAPSOURC",
            start_offset=BLOCK_SIZE * 100,
            data_size=98,
        )
        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()

        assert data[0x01:0x09] == b"MAPSOURC"
        assert data[0x09:0x0C] == b"MPS"
        size = struct.unpack_from("<I", data, 0x0C)[0]
        assert size == 98

    def test_multi_part_fat_entry(self):
        # Create a subfile needing >240 blocks (32KB each)
        # 300 blocks will need 2 FAT entries (240 blocks in first, 60 in second)
        large_size = BLOCK_SIZE * 300
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="BIGFILE",
            start_offset=BLOCK_SIZE * 50,
            data_size=large_size,
        )
        assert layout.num_fat_entries == 2

        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()
        assert len(data) == 2 * 512  # Two FAT entries

        # First entry: part 0, has size
        assert data[0x11] == 0  # part 0
        size = struct.unpack_from("<I", data, 0x0C)[0]
        assert size == large_size

        # Second entry: part 1, size=0
        second_entry = data[512:]
        assert second_entry[0x11] == 1  # part 1
        size2 = struct.unpack_from("<I", second_entry, 0x0C)[0]
        assert size2 == 0

    def test_full_fat_write(self):
        gmp_layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="09C102B0",
            start_offset=BLOCK_SIZE * 10,
            data_size=BLOCK_SIZE * 5,
        )
        mps_layout = SubfileLayout(
            subfile_type=SubfileType.MPS,
            name="MAPSOURC",
            start_offset=BLOCK_SIZE * 20,
            data_size=98,
        )
        layouts = [gmp_layout, mps_layout]
        buf = io.BytesIO()
        FATWriter.write(buf, layouts, FAT_START)
        data = buf.getvalue()

        # Should have: 1 special + 1 GMP + 1 MPS = 3 FAT entries = 1536 bytes
        assert len(data) == 3 * 512


class TestSubfileHeaderModel:
    def test_physical_offset(self):
        sh = SubfileHeader(
            subfile_type=SubfileType.GMP,
            name="test",
            start_block_offset=10,
            length=1000,
        )
        assert sh.get_physical_offset(32768) == 10 * 32768


# ---------------------------------------------------------------------------
# Tile Encoder
# ---------------------------------------------------------------------------


class TestTileEncoder:
    def test_encode_256x256_tile(self):
        tile = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        assert jpeg_data[:2] == b"\xff\xd8"  # JPEG SOI marker
        assert len(jpeg_data) < MAX_TILE_SIZE

    def test_encode_preserves_dimensions_header(self):
        """Verify the tile can be decoded back and dimensions match."""
        from PIL import Image

        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        img = Image.open(io.BytesIO(jpeg_data))
        assert img.size == (256, 256)

    def test_encode_strip_alpha(self):
        """4-channel input should be handled (alpha stripped)."""
        tile = np.full((256, 256, 4), 128, dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        assert jpeg_data[:2] == b"\xff\xd8"

    def test_encode_non_standard_tile(self):
        """Edge tile: non-256x256 dimensions."""
        tile = np.random.randint(0, 255, (128, 200, 3), dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        from PIL import Image

        img = Image.open(io.BytesIO(jpeg_data))
        assert img.size == (200, 128)

    def test_encode_multiple_tiles(self):
        tiles = [np.full((256, 256, 3), i * 50, dtype=np.uint8) for i in range(3)]
        encoded = TileEncoder.encode_tiles(tiles)
        assert len(encoded) == 3
        for data in encoded:
            assert data[:2] == b"\xff\xd8"

    def test_compute_tile_grid(self):
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        cols, rows = TileEncoder.compute_grid(bounds, zoom_level=12, tile_size=256)
        assert cols >= 1
        assert rows >= 1

    def test_compute_tile_grid_higher_zoom(self):
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        cols_low, rows_low = TileEncoder.compute_grid(bounds, zoom_level=10)
        cols_high, rows_high = TileEncoder.compute_grid(bounds, zoom_level=12)
        assert cols_high >= cols_low
        assert rows_high >= rows_low


# ---------------------------------------------------------------------------
# Multi-Resolution Pyramid
# ---------------------------------------------------------------------------


class TestPyramidGeneration:
    def test_pyramid_multiple_zoom_levels(self):
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=84),
            ZoomLevel(level_number=11, zoom_code=83),
            ZoomLevel(level_number=12, zoom_code=2),
        ]
        compressed_tiles = {
            10: [b"\xff\xd8" + b"\x00" * 500] * 2,
            11: [b"\xff\xd8" + b"\x00" * 500] * 5,
            12: [b"\xff\xd8" + b"\x00" * 500] * 12,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()

        gmp_layout = next(lay for lay in layouts if lay.subfile_type == SubfileType.GMP)
        assert gmp_layout.data_size > 0

        # GMP should contain tile data for all zoom levels
        total_tile_data = sum(len(t) * 502 for t in compressed_tiles.values())
        assert gmp_layout.data_size >= total_tile_data

    def test_single_zoom_level(self):
        zoom_levels = [ZoomLevel(level_number=14, zoom_code=0)]
        compressed_tiles = {14: [b"\xff\xd8" + b"\x00" * 100] * 3}
        img_file = _make_img_file(zoom_levels=zoom_levels)
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()

        gmp_layout = next(lay for lay in layouts if lay.subfile_type == SubfileType.GMP)
        assert gmp_layout.data_size > 0

    def test_pyramid_tile_count_increases_with_zoom(self):
        """Higher zoom levels should have more tiles."""
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        c10, r10 = TileEncoder.compute_grid(bounds, 10)
        c12, r12 = TileEncoder.compute_grid(bounds, 12)
        assert c12 * r12 > c10 * r10


# ---------------------------------------------------------------------------
# Attribution Embedding
# ---------------------------------------------------------------------------


class TestAttributionEmbedding:
    def test_attribution_in_header(self):
        header = _make_header(map_name="Swisstopo")
        data = IMGHeaderWriter.serialize(header)
        # Map description is 20 bytes at 0x49-0x5C, space-padded
        desc = data[0x49:0x5D]
        assert desc[:9] == b"Swisstopo"

    def test_truncation_to_20_bytes(self):
        long_name = "A" * 50
        header = _make_header(map_name=long_name)
        data = IMGHeaderWriter.serialize(header)
        desc = data[0x49:0x5D]
        assert len(desc) == 20
        assert all(b == ord("A") for b in desc)  # all 20 bytes filled

    def test_attribution_fallback_empty(self):
        header = _make_header(map_name="")
        data = IMGHeaderWriter.serialize(header)
        desc = data[0x49:0x5D]
        assert desc == b" " * 20  # space-padded when empty

    def test_max_length_attribution(self):
        name_20 = "A" * 20
        header = _make_header(map_name=name_20)
        data = IMGHeaderWriter.serialize(header)
        extracted = data[0x49:0x5D]
        assert extracted == b"A" * 20

    def test_heads_and_sectors_fields(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        # Heads at 0x5D (copy of 0x1A)
        heads = struct.unpack_from("<H", data, 0x5D)[0]
        assert heads == 0x0001
        # Sectors at 0x5F (copy of 0x18)
        sectors = struct.unpack_from("<H", data, 0x5F)[0]
        assert sectors == 0x0020


# ---------------------------------------------------------------------------
# Size Limit Handling
# ---------------------------------------------------------------------------


class TestSizeLimitHandling:
    def test_tile_within_size_limit(self):
        tile = TileRecord(
            row=0,
            col=0,
            lat_north=47.5,
            lat_south=47.0,
            lon_west=8.0,
            lon_east=8.5,
            data_offset=0,
            data_length=2_000_000,
        )
        assert tile.validate_size_limit()

    def test_tile_exceeds_size_limit(self):
        tile = TileRecord(
            row=0,
            col=0,
            lat_north=47.5,
            lat_south=47.0,
            lon_west=8.0,
            lon_east=8.5,
            data_offset=0,
            data_length=4_200_000,
        )
        assert not tile.validate_size_limit()

    def test_pre_write_size_accounting(self):
        """Verify that encoded tile sizes are tracked."""
        tiles = [np.full((256, 256, 3), i * 30, dtype=np.uint8) for i in range(5)]
        encoded = TileEncoder.encode_tiles(tiles)
        for data in encoded:
            assert len(data) <= MAX_TILE_SIZE

    def test_file_size_validation(self):
        """IMGFile.validate_size_constraints checks 4GB limit."""
        img_file = _make_img_file()
        img_file.subfiles = [
            SubfileHeader(
                subfile_type=SubfileType.GMP,
                name="test",
                start_block_offset=10,
                length=3_000_000_000,
            )
        ]
        valid, violations = img_file.validate_size_constraints()
        assert valid

    def test_file_size_exceeds_4gb(self):
        header = SubfileHeader(
            subfile_type=SubfileType.GMP,
            name="test",
            start_block_offset=0,
            length=5_000_000_000,
        )
        img_file = _make_img_file(subfiles=[header])
        valid, violations = img_file.validate_size_constraints()
        assert not valid
        assert any("4 GB" in v for v in violations)

    def test_tile_splitting_scenario(self):
        """Verify that tiles over 3.5MB are flagged."""
        oversized_tile = TileRecord(
            row=0,
            col=0,
            lat_north=47.5,
            lat_south=47.0,
            lon_west=8.0,
            lon_east=8.5,
            data_offset=0,
            data_length=MAX_TILE_SIZE + 1,
            width_pixels=256,
            height_pixels=256,
        )
        img_file = _make_img_file(tiles=[oversized_tile])
        valid, violations = img_file.validate_size_constraints()
        assert not valid
        assert any("3.5 MB" in v for v in violations)


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


class TestCoordinateConversion:
    def test_deg_to_garmin_zero(self):
        assert _deg_to_garmin(0.0) == 0

    def test_deg_to_garmin_positive(self):
        val = _deg_to_garmin(47.5)
        assert val > 0
        # Should be degrees * 2^31 / 180
        expected = int(47.5 * (2**31) / 180)
        assert val == expected

    def test_deg_to_garmin_negative(self):
        val = _deg_to_garmin(-8.5)
        assert val < 0


# ---------------------------------------------------------------------------
# FAT block calculation helpers
# ---------------------------------------------------------------------------


class TestFATBlockCalculation:
    def test_blocks_needed(self):
        assert _blocks_needed(1) == 1
        assert _blocks_needed(BLOCK_SIZE) == 1
        assert _blocks_needed(BLOCK_SIZE + 1) == 2

    def test_fat_blocks_for_data_blocks(self):
        # 1 data block needs 1 FAT entry
        assert _fat_blocks_for_data_blocks(1) == 1
        # 240 data blocks needs 1 FAT entry
        assert _fat_blocks_for_data_blocks(240) == 1
        # 241 data blocks needs 2 FAT entries
        assert _fat_blocks_for_data_blocks(241) == 2
        # 0 data blocks still needs 1 FAT entry
        assert _fat_blocks_for_data_blocks(0) == 1


# ---------------------------------------------------------------------------
# Integration: full IMG file write
# ---------------------------------------------------------------------------


class TestIMGFileWrite:
    def test_write_minimal_img(self, tmp_path):
        output = tmp_path / "test.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=2)]
        compressed_tiles = {
            12: [b"\xff\xd8" + b"\x00" * 100] * 3,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        assert output.exists()
        data = output.read_bytes()
        assert len(data) >= 512
        # Check magic
        assert data[0x10:0x16] == b"DSKIMG"
        # Check boot signature
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55
        # Check FAT block number at 0x40
        assert data[0x40] == FAT_BLOCK_NUMBER

    def test_write_multi_zoom_img(self, tmp_path):
        output = tmp_path / "multi.img"
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=84),
            ZoomLevel(level_number=11, zoom_code=83),
            ZoomLevel(level_number=12, zoom_code=2),
        ]
        compressed_tiles = {
            10: [b"\xff\xd8" + b"\x00" * 200],
            11: [b"\xff\xd8" + b"\x00" * 200] * 3,
            12: [b"\xff\xd8" + b"\x00" * 200] * 8,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        assert data[0x10:0x16] == b"DSKIMG"

    def test_fat_entries_written(self, tmp_path):
        output = tmp_path / "fat_test.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=2)]
        compressed_tiles = {12: [b"\x00" * 100]}
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # FAT should start at FAT_START (0x1000)
        # First FAT entry should be the special directory entry
        fat_start = FAT_START
        assert data[fat_start] == FAT_FLAG_ACTIVE  # active flag
        # Name should be spaces for special entry
        assert data[fat_start + 1 : fat_start + 9] == b"        "
        # Second FAT entry (GMP) should follow
        gmp_entry_offset = fat_start + 512
        assert data[gmp_entry_offset] == FAT_FLAG_ACTIVE
        assert data[gmp_entry_offset + 1 : gmp_entry_offset + 9] == b"09C102B0"

    def test_file_size_includes_all_tiles(self, tmp_path):
        output = tmp_path / "size_test.img"
        # Use larger tile data to verify it's all included
        tile_data = b"\xff\xd8" + b"\xab" * 10000
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=2)]
        compressed_tiles = {12: [tile_data] * 5}
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # File should be large enough to contain all tile data
        total_tile_bytes = len(tile_data) * 5
        assert len(data) >= total_tile_bytes + 4096  # tiles + overhead

    @pytest.mark.skip(reason="Tile index table removed - replaced by LBL28/LBL29")
    def test_tile_index_offsets_point_to_jpeg_data(self, tmp_path):
        """Verify that tile index entries point to valid JPEG SOI markers.

        Regression test: tile index offsets must be relative to GMP subfile start,
        not relative to the tile data region within GMP.

        NOTE: This test is obsolete. Tile index table has been replaced by
        LBL28 (image index) and LBL29 (image storage) sections.
        """
        output = tmp_path / "tile_index_test.img"
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=94),
            ZoomLevel(level_number=12, zoom_code=92),
        ]
        # Create distinguishable tile data for each zoom level
        tile_10a = b"\xff\xd8\xff\xe0" + b"\x0a" * 500
        tile_10b = b"\xff\xd8\xff\xe0" + b"\x0b" * 500
        tile_12a = b"\xff\xd8\xff\xe0" + b"\xc0" * 500
        tile_12b = b"\xff\xd8\xff\xe0" + b"\xc1" * 500
        tile_12c = b"\xff\xd8\xff\xe0" + b"\xc2" * 500

        compressed_tiles = {
            10: [tile_10a, tile_10b],
            12: [tile_12a, tile_12b, tile_12c],
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()

        # Compute GMP layout to find GMP start offset
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()
        gmp_layout = next(lay for lay in layouts if lay.subfile_type == SubfileType.GMP)
        gmp_start = gmp_layout.start_offset

        # Compute the tile index position within the GMP subfile
        # by reproducing the GMP writer's layout calculation
        from cartoload.exporters.garmin_img_writer import (
            GMP_CONTAINER_HEADER_SIZE,
            LBL_HEADER_LENGTH,
            NET_HEADER_LENGTH,
            RGN_HEADER_LENGTH,
            TRE_HEADER_LENGTH,
        )

        copyright_str = img_file.copyright_string or "Copyright GARMIN."
        copyright_bytes = copyright_str.encode("cp1252") + b"\x00" + b"\x00"
        pos = 0
        pos += GMP_CONTAINER_HEADER_SIZE
        pos += len(copyright_bytes)
        pos += TRE_HEADER_LENGTH
        map_info = b"Raster Map\0" + copyright_str.encode("cp1252") + b"\x00"
        pos += len(map_info)
        pos += RGN_HEADER_LENGTH
        pos += LBL_HEADER_LENGTH
        pos += NET_HEADER_LENGTH
        pos += 6  # TRE copyright
        pos += len(zoom_levels) * 8  # subdivisions
        pos += len(zoom_levels) * 4  # map levels
        pos += 1582  # RGN data
        total_tiles = 5
        for i in range(total_tiles):
            pos += len(f"{i}.jpg\0".encode("ascii"))
        tile_index_pos = pos

        # Read each tile index entry and verify it points to a JPEG SOI marker
        for i in range(total_tiles):
            offset_in_gmp = struct.unpack_from(
                "<I", data, gmp_start + tile_index_pos + i * 4
            )[0]
            abs_pos = gmp_start + offset_in_gmp
            assert data[abs_pos : abs_pos + 2] == b"\xff\xd8", (
                f"Tile {i}: offset {offset_in_gmp} (abs {abs_pos}) "
                f"does not point to JPEG SOI, found {data[abs_pos : abs_pos + 4].hex()}"
            )

    @pytest.mark.skip(reason="Tile index table removed - replaced by LBL28/LBL29")
    def test_tile_index_offsets_multi_zoom(self, tmp_path):
        """Verify tile offsets are correct with 3 zoom levels and varying tile counts.

        NOTE: This test is obsolete. Tile index table has been replaced by
        LBL28 (image index) and LBL29 (image storage) sections.
        """
        output = tmp_path / "multi_zoom_index.img"
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=94),
            ZoomLevel(level_number=11, zoom_code=93),
            ZoomLevel(level_number=12, zoom_code=92),
        ]
        compressed_tiles = {
            10: [b"\xff\xd8" + b"\x10" * 200] * 2,
            11: [b"\xff\xd8" + b"\x11" * 200] * 5,
            12: [b"\xff\xd8" + b"\x12" * 200] * 12,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()

        # Count JPEG SOI markers in the file
        jpeg_count = 0
        p = 0
        while True:
            idx = data.find(b"\xff\xd8", p)
            if idx == -1:
                break
            jpeg_count += 1
            p = idx + 1

        # Should find exactly 2 + 5 + 12 = 19 JPEG markers
        assert jpeg_count == 19, f"Expected 19 JPEG markers, found {jpeg_count}"


# ---------------------------------------------------------------------------
# GarminImgExporter integration
# ---------------------------------------------------------------------------


class TestGarminImgExporter:
    def test_exporter_name(self):
        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        assert exporter.name == "garmin-img"

    def test_validate_nonexistent_file(self, tmp_path):
        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        result = exporter.validate(tmp_path / "nonexistent.img")
        assert result is False

    def test_validate_gmt_not_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        # Create a dummy file
        dummy = tmp_path / "dummy.img"
        dummy.write_bytes(b"\x00" * 512)
        result = exporter.validate(dummy)
        assert result is True  # Skips validation when gmt not found


# ---------------------------------------------------------------------------
# Integration test: small but complete .img file
# ---------------------------------------------------------------------------


class TestIntegrationWrite:
    """Integration tests that write a complete .img file and verify structure."""

    def test_write_complete_img_2_zoom_levels(self, tmp_path):
        """Write a small but complete .img file with 2 zoom levels."""
        output = tmp_path / "integration_test.img"
        zoom_levels = [
            ZoomLevel(level_number=12, zoom_code=92),
            ZoomLevel(level_number=13, zoom_code=91),
        ]
        # Small tiles (real JPEG data)
        tile_12 = np.full((256, 256, 3), 100, dtype=np.uint8)
        tile_13a = np.full((256, 256, 3), 150, dtype=np.uint8)
        tile_13b = np.full((256, 256, 3), 200, dtype=np.uint8)

        compressed_tiles = {
            12: [TileEncoder.encode_tile(tile_12)],
            13: [TileEncoder.encode_tile(tile_13a), TileEncoder.encode_tile(tile_13b)],
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        assert output.exists()
        data = output.read_bytes()

        # Verify header structure
        assert data[0x10:0x16] == b"DSKIMG"
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55

        # Verify FAT block number
        assert data[0x40] == FAT_BLOCK_NUMBER

        # Verify block size exponents
        assert data[0x61] == 0x09
        assert data[0x62] == 0x06

        # Verify FAT entries exist
        assert data[FAT_START] == FAT_FLAG_ACTIVE

    @pytest.mark.gmt
    def test_write_validates_with_gmt(self, tmp_path):
        """Write a complete .img and validate with gmt (requires gmt on PATH)."""
        if not shutil.which("gmt"):
            pytest.skip("gmt not available on PATH")

        output = tmp_path / "gmt_validated.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        result = exporter.validate(output)
        assert result is True, "gmt validation should pass"

    def test_export_via_exporter_class(self, tmp_path):
        """Test the full GarminImgExporter.export() pipeline."""
        from cartoload.exporters.garmin_img import GarminImgExporter

        # Create a dummy raster (just needs to exist for the test)
        raster = tmp_path / "input.tif"
        raster.write_bytes(b"\x00" * 512)

        layer = LayerConfig(
            id="test",
            name="IntegrationTest",
            description="Test layer",
            source="test_src",
            zoom_levels=[12],
            exporter="garmin-img",
            output="test_output.img",
            bounds={"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0},
        )

        output = tmp_path / "test_output.img"
        exporter = GarminImgExporter()
        result = exporter.export(raster, layer, output)

        assert len(result) >= 1
        assert result[0].exists()
        data = result[0].read_bytes()
        assert data[0x10:0x16] == b"DSKIMG"


# ---------------------------------------------------------------------------
# LBL28/LBL29/Type E0 Tests
# ---------------------------------------------------------------------------


class TestLBL28LBL29TypeE0:
    """Test LBL28 (Image Index), LBL29 (Image Storage), and RGN Type E0 records."""

    def test_lbl28_section_present_in_subheader(self, tmp_path):
        """Verify LBL sub-header contains LBL28 section descriptor."""
        output = tmp_path / "test_lbl28.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # GMP FAT entry is at 0x1200 (second FAT entry after special directory at 0x1000)
        # Read first block number from GMP FAT entry
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 512

        # LBL sub-header is within GMP - search for "GARMIN LBL" magic
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        assert lbl_magic_offset > 0, "Could not find LBL sub-header"
        # LBL sub-header starts 2 bytes before the magic (header length field)
        lbl_start = lbl_magic_offset - 2

        # LBL28 descriptor at bytes 37-44 relative to LBL start
        lbl28_position = struct.unpack_from("<I", data, lbl_start + 37)[0]
        lbl28_size = struct.unpack_from("<I", data, lbl_start + 41)[0]

        assert lbl28_position > 0, "LBL28 position should be set"
        assert lbl28_size > 0, "LBL28 size should be set"

    def test_lbl28_contains_uint32_offsets(self, tmp_path):
        """Verify LBL28 contains N × uint32 offsets where N = tile count."""
        output = tmp_path / "test_lbl28_offsets.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        # Create 3 tiles
        tiles = [np.full((256, 256, 3), val, dtype=np.uint8) for val in [100, 150, 200]]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 512
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Read LBL28 descriptor
        lbl28_position = struct.unpack_from("<I", data, lbl_start + 37)[0]
        lbl28_size = struct.unpack_from("<I", data, lbl_start + 41)[0]

        # LBL28 should contain 3 × 4 bytes = 12 bytes
        assert lbl28_size == 12, f"Expected 12 bytes for 3 tiles, got {lbl28_size}"

        # Read offsets
        lbl28_offset = lbl_start + lbl28_position
        offsets = [
            struct.unpack_from("<I", data, lbl28_offset + i * 4)[0] for i in range(3)
        ]

        # First offset should be 0
        assert offsets[0] == 0, "First LBL28 offset should be 0"
        # Subsequent offsets should be cumulative JPEG sizes
        assert all(offsets[i] < offsets[i + 1] for i in range(2)), (
            "Offsets should be increasing"
        )

    def test_lbl29_section_present_in_subheader(self, tmp_path):
        """Verify LBL sub-header contains LBL29 section descriptor."""
        output = tmp_path / "test_lbl29.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 512
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # LBL29 descriptor at bytes 45-52
        lbl29_position = struct.unpack_from("<I", data, lbl_start + 45)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 49)[0]

        assert lbl29_position > 0, "LBL29 position should be set"
        assert lbl29_size > 0, "LBL29 size should be set"

    def test_lbl29_contains_jpeg_files(self, tmp_path):
        """Verify LBL29 contains concatenated JPEG files with FFD8FFE0 markers."""
        output = tmp_path / "test_lbl29_jpegs.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        # Create 2 tiles
        tiles = [np.full((256, 256, 3), val, dtype=np.uint8) for val in [100, 200]]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 512
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Read LBL29 descriptor
        lbl29_position = struct.unpack_from("<I", data, lbl_start + 45)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 49)[0]

        # Read LBL29 section
        lbl29_offset = lbl_start + lbl29_position
        lbl29_data = data[lbl29_offset : lbl29_offset + lbl29_size]

        # Should start with JPEG marker FFD8FFE0
        assert lbl29_data[:4] == b"\xff\xd8\xff\xe0", (
            "LBL29 should start with JPEG marker"
        )

        # Count JPEG markers (should be 2)
        jpeg_count = lbl29_data.count(b"\xff\xd8\xff\xe0")
        assert jpeg_count == 2, f"Expected 2 JPEG markers, found {jpeg_count}"

    def test_rgn_data_contains_type_e0_records(self, tmp_path):
        """Verify RGN data section contains Type E0 records starting with 0xE0 marker."""
        output = tmp_path / "test_type_e0.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # RGN sub-header at offset determined by layout (after GMP header)
        # For simplicity, search for Type E0 marker (0xE0) followed by bits_field
        assert b"\xe0\x2b" in data or b"\xe0\x25" in data, (
            "Should contain Type E0 record (0xE0 + bits_field)"
        )

    def test_type_e0_record_count_matches_tile_count(self, tmp_path):
        """Verify Type E0 record count matches tile count."""
        output = tmp_path / "test_type_e0_count.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        # Create 5 tiles
        tiles = [
            np.full((256, 256, 3), val, dtype=np.uint8) for val in range(100, 150, 10)
        ]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Count Type E0 markers (0xE0 followed by bits_field 0x2B or 0x25)
        e0_count = data.count(b"\xe0\x2b") + data.count(b"\xe0\x25")
        assert e0_count == 5, f"Expected 5 Type E0 records, found {e0_count}"

    def test_type_e0_bits_field_under_256_tiles(self, tmp_path):
        """Verify Type E0 bits_field is 0x2B for <256 tiles."""
        output = tmp_path / "test_bits_field_2b.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        # Create 10 tiles (< 256)
        tiles = [np.full((256, 256, 3), 128, dtype=np.uint8) for _ in range(10)]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Should use 0x2B for <256 tiles
        assert b"\xe0\x2b" in data, "Should use bits_field 0x2B for <256 tiles"
        assert b"\xe0\x25" not in data, "Should NOT use bits_field 0x25 for <256 tiles"

    def test_tile_index_table_not_present(self, tmp_path):
        """Verify tile index table is NOT present (replaced by LBL28/LBL29)."""
        output = tmp_path / "test_no_tile_index.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 512
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Verify LBL29 is last section in LBL (no tile index table after it)
        lbl29_position = struct.unpack_from("<I", data, lbl_start + 45)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 49)[0]

        # LBL sub-header total length
        lbl_header_length = struct.unpack_from("<H", data, lbl_start)[0]

        # LBL29 should extend to near end of LBL subfile
        lbl29_end = lbl29_position + lbl29_size
        # Allow some padding, but should be close to header length
        assert lbl29_end <= lbl_header_length + 1024, (
            "LBL29 should be last major section"
        )

    @pytest.mark.gmt
    def test_gmt_output_shows_bitmaps(self, tmp_path):
        """Verify GMT output contains 'Bitmaps' line showing raster detection."""
        if not shutil.which("gmt"):
            pytest.skip("gmt not available on PATH")

        output = tmp_path / "test_gmt_bitmaps.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=92)]
        # Create 3 tiles
        tiles = [np.full((256, 256, 3), val, dtype=np.uint8) for val in [100, 150, 200]]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        # Run GMT validation
        import subprocess

        result = subprocess.run(
            ["gmt", "-i", "-v", str(output)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"GMT validation failed: {result.stderr}"

        # Check for "Bitmaps" line in output
        assert "Bitmaps" in result.stdout, "GMT output should contain 'Bitmaps' line"

        # Verify tile count appears in output
        assert "3" in result.stdout or "size" in result.stdout.lower(), (
            "GMT should show bitmap count/size"
        )


# ---------------------------------------------------------------------------
# Binary comparison test (requires known-good .img)
# ---------------------------------------------------------------------------

KNOWN_GOOD_IMG = Path("tests/data/garmin_samples")


class TestBinaryComparison:
    """Compare writer output against known-good .img files (if available)."""

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_header_magic_matches_reference(self):
        """Compare header magic bytes with reference file."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found in test data")

        ref_data = ref_files[0].read_bytes()[:512]
        assert ref_data[0x10:0x16] == b"DSKIMG"

        # Our writer should produce the same magic
        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)
        assert our_data[0x10:0x16] == ref_data[0x10:0x16]

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_boot_signature_matches_reference(self):
        """Boot signature should match reference."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found")

        ref_data = ref_files[0].read_bytes()[:512]
        ref_sig = struct.unpack_from("<H", ref_data, 0x1FE)[0]

        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)
        our_sig = struct.unpack_from("<H", our_data, 0x1FE)[0]

        assert our_sig == ref_sig == 0xAA55

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_fat_block_number_matches_reference(self):
        """FAT block number at offset 0x40 should match reference."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found")

        ref_data = ref_files[0].read_bytes()[:512]
        ref_fat_block = ref_data[0x40]

        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)

        assert our_data[0x40] == ref_fat_block == 0x08

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_block_size_exponents_match_reference(self):
        """Block size exponents at 0x61-0x62 should match reference."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found")

        ref_data = ref_files[0].read_bytes()[:512]

        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)

        assert our_data[0x61] == ref_data[0x61] == 0x09
        assert our_data[0x62] == ref_data[0x62] == 0x06


# ---------------------------------------------------------------------------
# Test markers for gmt / gdal
# ---------------------------------------------------------------------------


def test_gmt_marker_exists():
    """Verify pytest.mark.gmt is configured."""
    assert hasattr(pytest.mark, "gmt")


def test_gdal_marker_exists():
    """Verify pytest.mark.gdal is available for future GDAL tests."""
    assert hasattr(pytest.mark, "gdal")
