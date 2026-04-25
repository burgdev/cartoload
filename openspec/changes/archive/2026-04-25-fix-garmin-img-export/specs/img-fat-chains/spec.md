## ADDED Requirements

### Requirement: FAT region contains valid block chain entries

The IMG writer SHALL populate the FAT region (offset 0x1000 to FAT_DIR_START) with valid block chain entries for every data block used by subfiles. Each FAT entry SHALL be a 4-byte little-endian integer pointing to the next block in the chain. The last block of each chain SHALL contain the end-of-chain marker (0xFFFFFFFF). Free blocks SHALL contain 0x00000000.

#### Scenario: Single contiguous GMP subfile

- **WHEN** a GMP subfile occupies blocks 3 through 100
- **THEN** FAT entries at blocks 3-99 SHALL contain the next block number (4, 5, ..., 100)
- **AND** FAT entry at block 100 SHALL contain 0xFFFFFFFF (end of chain)
- **AND** FAT entries at blocks 0-2 SHALL contain 0x00000000 (reserved for header/FAT/directory)

#### Scenario: Two subfiles (GMP + MPS) in sequence

- **WHEN** GMP occupies blocks 3-100 and MPS occupies blocks 101-102
- **THEN** FAT entries for blocks 3-99 point to the next block, block 100 points to 0xFFFFFFFF
- **AND** FAT entry for block 101 points to 102, block 102 points to 0xFFFFFFFF

### Requirement: FAT chain covers all subfile data blocks

The FAT region SHALL contain chain entries for every block used by every subfile. No data block SHALL be orphaned (not reachable from any FAT chain).

#### Scenario: All blocks accounted for

- **WHEN** an IMG file is written with GMP (N blocks) and MPS (M blocks)
- **THEN** the total number of non-zero, non-end-marker FAT entries SHALL equal N + M
- **AND** every data block SHALL be reachable by following FAT chains from the subfile directory start block entries

### Requirement: FAT page size is 512 bytes

Each FAT page/sector SHALL be exactly 512 bytes, consistent with the physical block size used for FAT management. The FAT region SHALL be a multiple of 512 bytes in size.

#### Scenario: FAT region alignment

- **WHEN** the FAT region is written from 0x1000 to 0x1200
- **THEN** the region size SHALL be 0x200 (512 bytes)
- **AND** all FAT entries SHALL be aligned to 4-byte boundaries within the region

### Requirement: Subfile directory entries reference correct start blocks

Each entry in the subfile directory SHALL contain the correct starting block number for its subfile. The start block SHALL be the physical block number (byte_offset / BLOCK_SIZE) where the subfile data begins.

#### Scenario: GMP subfile starts after directory

- **WHEN** the GMP subfile data starts at byte offset 0x8000 (block 4)
- **THEN** the GMP directory entry start_block field SHALL contain the value 4

### Requirement: GMP tile data offsets are absolute within GMP subfile

Tile index entries within the GMP subfile SHALL store offsets that are absolute positions from the start of the GMP subfile data, including the GMP header, zoom level table, draw order section, and tile index section.

#### Scenario: Tile offset calculation

- **WHEN** the GMP subfile has a 512-byte header, 160-byte zoom table, 16-byte draw order, and 48-byte tile index (total 736 bytes of metadata)
- **AND** the first tile's data begins immediately after the metadata at byte 736
- **THEN** the first tile index entry SHALL have data_offset = 736
- **AND** the second tile index entry SHALL have data_offset = 736 + len(first_tile_data)

#### Scenario: Tile data is readable via offset

- **WHEN** a tile index entry has data_offset = 736 and data_length = 8192
- **THEN** reading 8192 bytes starting at (GMP_start + 736) SHALL produce valid JPEG data (starting with FF D8)
