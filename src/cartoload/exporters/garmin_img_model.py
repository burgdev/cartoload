"""
Garmin IMG File Format Data Model

This module defines dataclasses representing the structure of Garmin raster .img files.
These classes model the file format documented in docs/exporters/garmin-img.md and are
used for both parsing existing IMG files and constructing new ones.

The Garmin IMG format is a disk image format containing:
- A 512-byte header with file metadata and FAT information
- A File Allocation Table (FAT) for block chain management
- A subfile directory table listing embedded subfiles (GMP, MPS, etc.)
- Subfile data blocks containing the actual map data (tiles, indices, metadata)

For raster maps, the primary subfile is GMP (Garmin Map), which contains:
- Tile index mapping coordinates to data offsets
- Zoom level table defining resolution pyramid
- Compressed bitmap tiles (JPEG/PNG)
- Map metadata (bounds, name, copyright, etc.)

See docs/exporters/garmin-img.md for complete format specification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SubfileType(Enum):
    """Garmin IMG subfile type codes."""

    GMP = "GMP"  # Garmin Map - primary raster/vector data container
    MPS = "MPS"  # MAPSOURC - map source metadata
    TRE = "TRE"  # Tree - spatial index (vector maps)
    RGN = "RGN"  # Region - vector geometry data
    LBL = "LBL"  # Label - text labels and POI names
    TYP = "TYP"  # Type - custom style definitions
    MDR = "MDR"  # Metadata - multi-map registry


class TileCompressionType(Enum):
    """Tile compression format types."""

    JPEG = 4  # JPEG compression (most common for raster)
    PNG = 5  # PNG compression (lossless, larger)
    NONE = 0  # Uncompressed (rarely used)


@dataclass
class IMGHeader:
    """
    Main IMG file header (512 bytes at file offset 0x00).

    Contains file-level metadata, creation date, FAT location, and map identification.
    All multi-byte integers are little-endian unless otherwise noted.
    """

    # Magic signature and version (offset 0x10-0x17)
    magic: str = "DSKIMG"  # 6 bytes, must be "DSKIMG"
    format_version: int = 2  # 2 bytes, typically 0x0002

    # Encryption (offset 0x1A)
    xor_byte: int = 0x00  # 1 byte, XOR encryption key (0x00 = no encryption)

    # Creation timestamp (offset 0x39-0x3E, 6 bytes total)
    creation_date: datetime = field(default_factory=datetime.now)
    # Stored as: [year:2 bytes LE][month:1][day:1][hour:1][minute:1][second:1]

    # Creator and map identification (offset 0x41-0x68)
    creator: str = "GARMIN"  # 8 bytes, null-padded vendor string
    map_name: str = ""  # 32 bytes max, null-terminated map title

    # FAT configuration
    fat_start_offset: int = 0x1000  # FAT begins at offset 0x1000 (4096)
    fat_directory_offset: int = 0x1200  # Subfile directory at 0x1200 (4608)
    fat_size: int = 0x20000  # FAT extent in bytes
    block_size: int = 32768  # Allocation unit size (typically 32KB)

    # File metadata
    checksum_or_id: int = (
        0x0000  # 2 bytes at offset 0x0E, file-specific ID (0x0000 from SwissTopo_West)
    )
    unknown_size_field: int = 0x047A0000  # 4 bytes at offset 0x0A, purpose unclear

    # Boot sector signature (offset 0x1FE-0x1FF)
    boot_signature: int = 0xAA55  # Standard x86 boot sector marker

    def encode_creation_date(self) -> bytes:
        """
        Encode creation_date as 6-byte Garmin timestamp.

        Format: [year:2 bytes LE][month:1][day:1][hour:1][minute:1][second:1]
        Example: 2022-04-16 15:03:56 -> e6 07 04 10 0f 03 38

        Returns:
            6 bytes representing the timestamp
        """
        year_bytes = self.creation_date.year.to_bytes(2, byteorder="little")
        month_byte = bytes([self.creation_date.month])
        day_byte = bytes([self.creation_date.day])
        hour_byte = bytes([self.creation_date.hour])
        minute_byte = bytes([self.creation_date.minute])
        second_byte = bytes([self.creation_date.second])

        return (
            year_bytes + month_byte + day_byte + hour_byte + minute_byte + second_byte
        )

    @staticmethod
    def encode_creation_date_static(dt: datetime) -> bytes:
        """Encode a datetime as 6-byte Garmin timestamp (static version)."""
        year_bytes = dt.year.to_bytes(2, byteorder="little")
        return year_bytes + bytes([dt.month, dt.day, dt.hour, dt.minute, dt.second])

    @staticmethod
    def decode_creation_date(date_bytes: bytes) -> datetime:
        """
        Decode 6-byte Garmin timestamp to datetime.

        Args:
            date_bytes: 6 bytes in Garmin format

        Returns:
            Parsed datetime object
        """
        year = int.from_bytes(date_bytes[0:2], byteorder="little")
        month = date_bytes[2]
        day = date_bytes[3]
        hour = date_bytes[4]
        minute = date_bytes[5]
        second = date_bytes[6] if len(date_bytes) > 6 else 0

        return datetime(year, month, day, hour, minute, second)


@dataclass
class SubfileHeader:
    """
    Subfile directory entry describing an embedded subfile.

    Located at offset 0x1200 (fat_directory_offset) in the main IMG file.
    Each entry identifies a subfile's type, location, and size.
    """

    subfile_type: SubfileType  # 3-character type code (GMP, MPS, TRE, etc.)
    name: str  # 8-character identifier (e.g., "09C102B0", "MAPSOURC")
    start_block_offset: (
        int  # Starting block offset (multiply by block_size for byte offset)
    )
    length: int  # Total size in bytes

    # FAT chain information (computed during parsing or construction)
    block_chain: list[int] = field(
        default_factory=list
    )  # List of block numbers in chain

    def get_physical_offset(self, block_size: int = 32768) -> int:
        """
        Calculate physical byte offset of subfile start.

        Args:
            block_size: Block allocation size (default 32KB)

        Returns:
            Byte offset from start of file
        """
        return self.start_block_offset * block_size


@dataclass
class TileRecord:
    """
    Individual tile record within the GMP subfile tile index.

    Maps a tile's grid coordinates and geographic bounds to its data location.
    Each tile contains a compressed bitmap covering a specific lat/lon rectangle.
    """

    # Grid coordinates (zero-indexed row and column within zoom level)
    row: int
    col: int

    # Geographic bounds (WGS84 decimal degrees)
    lat_north: float
    lat_south: float
    lon_west: float
    lon_east: float

    # Data location within GMP subfile
    data_offset: int  # Byte offset from start of GMP subfile
    data_length: int  # Compressed tile size in bytes

    # Tile properties
    compression_type: TileCompressionType = TileCompressionType.JPEG
    width_pixels: int = 256  # Pixel width (typically 256)
    height_pixels: int = 256  # Pixel height (typically 256)

    def get_center_lat_lon(self) -> tuple[float, float]:
        """
        Calculate tile center coordinates.

        Returns:
            (latitude, longitude) tuple of tile center
        """
        center_lat = (self.lat_north + self.lat_south) / 2
        center_lon = (self.lon_west + self.lon_east) / 2
        return (center_lat, center_lon)

    def validate_size_limit(self) -> bool:
        """
        Check if tile data is within Garmin's 3.5 MB per-tile limit.

        Returns:
            True if tile is within limit, False otherwise
        """
        MAX_TILE_SIZE = 3_670_016  # 3.5 MB limit
        return self.data_length <= MAX_TILE_SIZE


@dataclass
class ZoomLevel:
    """
    Zoom level definition within the GMP subfile.

    Each zoom level represents one layer of the multi-resolution pyramid,
    referencing a subset of tiles at a specific resolution.
    """

    level_number: int  # Garmin bits/precision (remapped to 24-N+1..24)
    zoom_code: int  # Garmin internal zoom code (e.g., 84, 83, 2, 1, 0)
    source_zoom: int | None = (
        None  # Original WMTS zoom level (key into compressed_tiles)
    )

    # Resolution metadata
    resolution_meters_per_pixel: Optional[float] = (
        None  # Ground resolution at this level
    )

    # Tile subset for this zoom level
    tile_offset: int = 0  # Starting index in tile array
    tile_count: int = 0  # Number of tiles at this zoom level

    # Geographic bounds (should match or be subset of map bounds)
    lat_north: Optional[float] = None
    lat_south: Optional[float] = None
    lon_west: Optional[float] = None
    lon_east: Optional[float] = None

    def get_tile_range(self) -> tuple[int, int]:
        """
        Get tile index range for this zoom level.

        Returns:
            (start_index, end_index) tuple (end is exclusive)
        """
        return (self.tile_offset, self.tile_offset + self.tile_count)


@dataclass
class DrawOrderEntry:
    """
    Draw order and rendering priority configuration.

    Determines how the map layer is rendered when multiple maps overlap.
    """

    priority: int = 24  # Draw order priority (0-100, higher = drawn on top)
    layer_type: str = "Raster Map"  # Layer type description

    # Unknown parameters field from GMT output: "parameters 1 4 36 1"
    param1: int = 1
    param2: int = 4
    param3: int = 36
    param4: int = 1


@dataclass
class TypeE0Record:
    """
    RGN Type E0 record for raster tile metadata.

    Each Type E0 record describes one raster tile's geographic bounds,
    size, and reference to the image data in LBL29 via LBL28 index.

    Binary format:
    - marker (1 byte): 0xE0
    - bits_field (1 byte): 0x2B for <256 tiles, 0x25 for ≥256 tiles
    - lat_min, lon_min, lat_max, lon_max (4× uint32 LE): bounds in Garmin map units
    - block_size (uint32 LE): JPEG file size in bytes
    - image_index (uint8 or uint16 LE): index into LBL28 offset array
    """

    marker: int = 0xE0  # Type E0 marker byte
    bits_field: int = 0x2B  # 0x2B for <256 tiles, 0x25 for ≥256 tiles
    lat_min: int = 0  # Latitude minimum in Garmin map units (32-bit signed)
    lon_min: int = 0  # Longitude minimum in Garmin map units (32-bit signed)
    lat_max: int = 0  # Latitude maximum in Garmin map units (32-bit signed)
    lon_max: int = 0  # Longitude maximum in Garmin map units (32-bit signed)
    block_size: int = 0  # JPEG file size in bytes
    image_index: int = 0  # Index into LBL28 offset array (0-based)

    def get_record_size(self) -> int:
        """
        Calculate binary record size based on bits_field.

        Returns:
            23 bytes for 8-bit index (bits_field=0x2B)
            24 bytes for 16-bit index (bits_field=0x25)
        """
        if self.bits_field == 0x2B:
            return 23  # marker + bits_field + 4×coords + block_size + uint8 index
        else:
            return 24  # marker + bits_field + 4×coords + block_size + uint16 index


@dataclass
class LBL28Section:
    """
    LBL28 section: Image index table.

    Contains an array of uint32 offsets pointing to JPEG images in LBL29.
    Each offset is relative to the start of the LBL29 section.
    """

    offsets: list[int] = field(default_factory=list)  # uint32 offsets to LBL29 JPEGs

    def get_section_size(self) -> int:
        """Calculate binary size of LBL28 section (N × 4 bytes)."""
        return len(self.offsets) * 4


@dataclass
class LBL29Section:
    """
    LBL29 section: Image storage.

    Contains concatenated JPEG files indexed by LBL28.
    JPEGs are stored sequentially with no padding between files.
    """

    jpeg_data: list[bytes] = field(default_factory=list)  # List of JPEG files as bytes

    def get_section_size(self) -> int:
        """Calculate binary size of LBL29 section (sum of all JPEG sizes)."""
        return sum(len(jpeg) for jpeg in self.jpeg_data)


@dataclass
class LBLSectionInfo:
    """
    LBL section position and size information for sub-header.

    Tracks the positions and sizes of LBL labels, LBL28, and LBL29 sections
    within the LBL subfile data area.
    """

    labels_position: int = 0  # Offset relative to LBL sub-header start
    labels_size: int = 0
    lbl28_position: int = 0  # Offset relative to LBL sub-header start
    lbl28_size: int = 0
    lbl29_position: int = 0  # Offset relative to LBL sub-header start
    lbl29_size: int = 0


@dataclass
class Subdivision:
    """
    A spatial subdivision within a Garmin raster IMG file.

    Each subdivision represents a geographic region at a specific zoom level.
    Tiles are assigned to subdivisions based on their geographic position,
    and each subdivision gets its own TRE2 record, TRE7 entry, and RGN2 data group.

    The subdivision hierarchy matches the SwissTopo reference format:
    fewer subdivisions at overview zoom levels, more at detailed levels.

    TRE2 binary format:
      Non-last zoom levels: 16 bytes
        [rgn_offset(3)] [objects(1)] [lon(3)] [lat(3)] [width(2)] [height(2)] [nextLevel(2)]
      Last zoom level: 14 bytes (no nextLevel field)
        [rgn_offset(3)] [objects(1)] [lon(3)] [lat(3)] [width(2)] [height(2)]

    width encodes: bit 15 = has children, bits 0-14 = encoded horizontal extent
    height encodes: signed vertical extent (negative → has_points flag)
    """

    # Geographic center (WGS84 decimal degrees)
    center_lat: float
    center_lon: float

    # Which zoom level this subdivision belongs to (index into zoom_levels list)
    zoom_level_index: int

    # Tile data for this subdivision: list of (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
    tile_entries: list = field(default_factory=list)

    # RGN2 byte offset (computed during layout, not set at construction)
    rgn2_offset: int = 0

    # TRE7 flag byte (0=normal data, 1=boundary/empty)
    tre7_flag: int = 0

    # Index of first child subdivision at next zoom level
    next_level_index: int = 0

    # Geographic bounds of this subdivision (WGS84 decimal degrees)
    bounds_west: float = 0.0
    bounds_east: float = 0.0
    bounds_north: float = 0.0
    bounds_south: float = 0.0

    def get_tile_count(self) -> int:
        """Return the number of tiles in this subdivision."""
        return len(self.tile_entries)

    def encode_tre2_width(self, shift: int) -> int:
        """Encode the horizontal extent for TRE2 width field.

        Returns width with bit 15 set if this subdivision has children
        (i.e., is not at the last zoom level — caller must set bit 15).
        The encoded value represents (extent_in_map_units >> shift).
        Clamped to 0x7FFF to fit in 15-bit TRE2 width field.
        """
        center_mu = int(self.center_lon * (2**24) / 360)
        west_mu = int(self.bounds_west * (2**24) / 360)
        w = 2 * (center_mu - west_mu)
        mask = (1 << shift) - 1
        encoded = ((w + 1) // 2 + mask) >> shift
        return min(encoded, 0x7FFF)

    def encode_tre2_height(self, shift: int) -> int:
        """Encode the vertical extent for TRE2 height field.

        Returns signed height value in encoded map units.
        Clamped to 0x7FFF to fit in 15-bit TRE2 height field.
        """
        center_mu = int(self.center_lat * (2**24) / 360)
        south_mu = int(self.bounds_south * (2**24) / 360)
        h = 2 * (center_mu - south_mu)
        mask = (1 << shift) - 1
        encoded = ((h + 1) // 2 + mask) >> shift
        return min(encoded, 0x7FFF)


@dataclass
class IMGFile:
    """
    Top-level container representing a complete Garmin .img file.

    Aggregates all components: header, subfiles, tiles, zoom levels, and metadata.
    This is the primary interface for reading and writing IMG files.
    """

    header: IMGHeader
    subfiles: list[SubfileHeader] = field(default_factory=list)
    tiles: list[TileRecord] = field(default_factory=list)
    zoom_levels: list[ZoomLevel] = field(default_factory=list)
    draw_order: DrawOrderEntry = field(default_factory=DrawOrderEntry)

    # GMP-specific metadata (stored in GMP subfile header)
    map_id: int = 0  # 8-character hex ID (e.g., 0x09C102B0)
    gmp_creation_date: Optional[datetime] = None  # GMP subfile creation timestamp
    copyright_string: str = "Copyright 1995-2022 by GARMIN Corporation."
    description: str = "Raster Map"
    character_encoding: str = "CP-1252"  # Windows-1252 Western European

    # Geographic bounds (WGS84)
    bounds_north: float = 0.0
    bounds_south: float = 0.0
    bounds_west: float = 0.0
    bounds_east: float = 0.0

    # Product identification (typically 0 for custom maps)
    product_id: int = 0  # PID
    family_id: int = 0  # FID

    def get_total_tile_count(self) -> int:
        """Get total number of tiles across all zoom levels."""
        return len(self.tiles)

    def get_gmp_subfile(self) -> Optional[SubfileHeader]:
        """
        Find and return the GMP subfile header.

        Returns:
            GMP SubfileHeader if present, None otherwise
        """
        for subfile in self.subfiles:
            if subfile.subfile_type == SubfileType.GMP:
                return subfile
        return None

    def get_file_size(self) -> int:
        """
        Calculate total file size based on subfiles.

        Returns:
            Total size in bytes
        """
        if not self.subfiles:
            return 512  # Header only

        max_offset = 0
        for subfile in self.subfiles:
            physical_offset = subfile.get_physical_offset(self.header.block_size)
            end_offset = physical_offset + subfile.length
            max_offset = max(max_offset, end_offset)

        return max_offset

    def validate_size_constraints(self) -> tuple[bool, list[str]]:
        """
        Validate file against Garmin IMG size constraints.

        Returns:
            (is_valid, list_of_violations) tuple
        """
        violations = []

        # Check 4 GB file size limit
        file_size = self.get_file_size()
        if file_size > 4_294_967_296:
            violations.append(f"File size {file_size} exceeds 4 GB limit")

        # Check tile size limits
        for i, tile in enumerate(self.tiles):
            if not tile.validate_size_limit():
                violations.append(
                    f"Tile {i} at ({tile.row}, {tile.col}) exceeds 3.5 MB limit: "
                    f"{tile.data_length} bytes"
                )

        # Check tile count (practical limit)
        if len(self.tiles) > 1_000_000:
            violations.append(
                f"Tile count {len(self.tiles)} exceeds practical limit of 1M"
            )

        # Check zoom level count
        if len(self.zoom_levels) > 24:
            violations.append(
                f"Zoom level count {len(self.zoom_levels)} exceeds limit of 24"
            )

        return (len(violations) == 0, violations)

    def get_zoom_level_by_number(self, level_number: int) -> Optional[ZoomLevel]:
        """
        Find zoom level by its level number.

        Args:
            level_number: Garmin zoom level number (e.g., 24)

        Returns:
            ZoomLevel if found, None otherwise
        """
        for zoom in self.zoom_levels:
            if zoom.level_number == level_number:
                return zoom
        return None
