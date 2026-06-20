# Header, FAT & Size Constraints

This page covers the IMG file header, FAT (File Allocation Table) structure, MPS metadata subfile, size constraints, and date encoding. The header and FAT form the outer container; the GMP subfiles inside are described in [GMP Container](gmp-container.md).

## 1. File Header Structure

The IMG file begins with a 512-byte header containing metadata and file system information.

### 1.1 Header Field Reference

| Offset      | Size | Field              | Description                                                                                                                                                                                                                                |
| ----------- | ---- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0x00        | 1    | XOR byte           | Encryption key (0x00 = no encryption)                                                                                                                                                                                                      |
| 0x01-0x07   | 7    | Reserved           | Zero padding                                                                                                                                                                                                                               |
| 0x08-0x09   | 2    | Map version        | Typically 0x0000                                                                                                                                                                                                                           |
| 0x0A-0x0B   | 2    | Update month/year  | Update marker (0x0020 observed)                                                                                                                                                                                                            |
| 0x0E-0x0F   | 2    | Checksum/ID        | 2-byte field. mkgmap always sets this to 0x0000 and notes "Checksum is not checked." GPXSee does not validate it either. Some reference files use non-zero values (e.g., 0x5000) but these are not required for device compatibility. |
| 0x10        | 6    | Magic signature    | `DSKIMG` (ASCII)                                                                                                                                                                                                                           |
| 0x16        | 1    | Unknown            | Always 0x00                                                                                                                                                                                                                                |
| 0x17        | 1    | Format version     | Always 0x02                                                                                                                                                                                                                                |
| 0x18-0x19   | 2    | Sectors per track  | CHS geometry (cosmetic). mkgmap picks from [4,8,16,32] so that sectors × heads × cylinders > file size in 512-byte sectors. Not validated by devices. Typical: 32.                                                                                                                                       |
| 0x1A-0x1B   | 2    | Heads per cylinder | CHS geometry (cosmetic). mkgmap picks from [16,32,64,128,256]. Not validated by devices. Typical: 256. IOM: 16.                                                                                                                          |
| 0x1C-0x1F   | 4    | Cylinders          | CHS geometry (cosmetic). 10-bit value, top 2 bits stored in sector field. Varies per file size.                                                                                                                                            |
| 0x39-0x3E   | 6    | Creation date      | `year_LE(2) + month(1) + day(1) + hour(1) + min(1) + sec(1)`                                                                                                                                                                               |
| 0x40        | 1    | FAT block number   | Physical block number of FAT start (8 = 0x1000)                                                                                                                                                                                            |
| 0x41-0x48   | 8    | Creator string     | `GARMIN\0\0` (null-padded to 8 bytes)                                                                                                                                                                                                      |
| 0x49-0x5C   | 20   | Map description    | ASCII, space-padded (20 bytes)                                                                                                                                                                                                             |
| 0x5D-0x5E   | 2    | Heads (copy)       | 0x0001                                                                                                                                                                                                                                     |
| 0x5F-0x60   | 2    | Sectors (copy)     | 0x0020                                                                                                                                                                                                                                     |
| 0x61        | 1    | Block size exp E1  | 0x09 (base = 2^9 = 512)                                                                                                                                                                                                                    |
| 0x62        | 1    | Block size exp E2  | 0x06 (block_size = 512 × 2^6 = 32768)                                                                                                                                                                                                      |
| 0x63-0x64   | 2    | Total block count  | Total data blocks, or 0xFFFF if overflow                                                                                                                                                                                                   |
| 0x1BE-0x1CD | 16   | Partition entry    | MBR-style partition table entry                                                                                                                                                                                                            |
| 0x1FE-0x1FF | 2    | Boot signature     | 0xAA55 (standard x86 boot sector signature)                                                                                                                                                                                                |

### 1.2 Creation Date Encoding

**Offset: 0x39-0x3E** — 6 bytes, little-endian (confirmed by Mechalas spec):

```
byte 0-1: year   (uint16 LE)
byte 2:   month  (0-11, NOT 1-12 as in some references)
byte 3:   day    (1-31)
byte 4:   hour   (0-23)
byte 5:   second (0-59)
```

Note: offset 0x3E stores seconds, not minutes. The header does not include minutes. The Mechalas spec confirms: year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1) at 0x39-0x3F but some references show only 6 bytes (0x39-0x3E).

### 1.3 Block Size Calculation

```
BLOCK_SIZE = 512 × 2^E2 = 512 × 2^6 = 32768 bytes
```

The FAT block size is always 512 bytes. The data block size is 32768 bytes.

### 1.4 Partition Table

At offset 0x1BE, a standard MBR partition table entry:

- 0x1BE: Boot indicator (0x00 = not bootable)
- 0x1BF-0x1C1: Start CHS
- 0x1C2: System type (0xFF = auto-detect)
- 0x1C3-0x1C5: End CHS
- 0x1C6-0x1C9: Relative sectors (LBA start, uint32 LE)
- 0x1CA-0x1CD: Total sectors (uint32 LE)


## 2. FAT (File Allocation Table) Structure

### 2.1 FAT Layout

GMT reports format: `fat: <start> - <directory> - <extent>`

- **FAT start offset:** 0x1000 (4096 bytes from file start)
- **Physical block number:** 8 (stored in header at 0x40)
- **FAT entry size:** 512 bytes each

### 2.2 FAT Entry Format (512 bytes)

| Offset | Size | Field        | Description                                                                                       |
| ------ | ---- | ------------ | ------------------------------------------------------------------------------------------------- |
| 0x00   | 1    | Flag         | 0x01=active, 0x00=terminator                                                                      |
| 0x01   | 8    | Subfile name | 8-char name, space-padded (e.g., "09C102B0")                                                      |
| 0x09   | 3    | Subfile type | ASCII type code (e.g., "GMP", "MPS")                                                              |
| 0x0C   | 4    | Subfile size | uint32 LE, only valid in part 0                                                                   |
| 0x10   | 1    | Flag2        | 0x00=normal, 0x03=special directory entry                                                         |
| 0x11   | 1    | Part number  | 0 for first part, increments for multi-part (uint16 per spec, but high byte always 0 in practice) |
| 0x12   | 14   | Reserved     | Zeros                                                                                             |
| 0x20   | 480  | Block table  | 240 × uint16 LE block numbers (0xFFFF = unused)                                                   |

### 2.3 Special Directory FAT Entry

The first FAT entry is a special directory entry that covers the blocks from offset 0 through the start of the data region:

- Name: 8 spaces
- Type: 3 spaces
- Flag2: 0x03 (special)
- Block table: sequential block numbers 0..N (header + FAT blocks)

### 2.4 Subfile FAT Entries

Each subfile gets one or more FAT entries:

- Name: For GMP subfiles, this is the map ID as 8-char uppercase hex (e.g., `09C102B0`). For MPS, it's `MAPSOURC`.
- Large subfiles span multiple FAT entries (part 0, 1, 2...) each holding up to 240 block pointers.
- Block pointers are physical block numbers (offset / BLOCK_SIZE), not FAT indices.


### 3.9 MPS Subfile (98 bytes)

| Offset | Size | Field      | Description           |
| ------ | ---- | ---------- | --------------------- |
| 0x00   | 2    | Signature  | `MP`                  |
| 0x02   | 32   | Map name   | Null-terminated ASCII |
| 0x22   | 2    | Product ID | uint16 LE             |
| 0x24   | 2    | Family ID  | uint16 LE             |
| 0x26   | 4    | Map ID     | uint32 LE             |


## 8. Size Constraints and Limits

### 8.1 File Size Limits

| Constraint           | Value                | Notes                 |
| -------------------- | -------------------- | --------------------- |
| Maximum file size    | 4 GB (4,294,967,296) | Limited by 32-bit FAT |
| Data block size      | 32,768 bytes         | 512 × 2^6             |
| FAT entry size       | 512 bytes            |                       |
| Blocks per FAT entry | 240                  | After 32-byte header  |
| Max tile size        | 3,670,016 bytes      | 3.5 MB compressed     |

### 8.2 FAT Block Capacity

Each FAT entry holds 240 block pointers (240 × 32KB = 7.5MB per FAT entry). For large files:

- 1.4 GB GMP ≈ 45,623 data blocks ≈ 191 FAT entries
- Single-map FAT extent: 0x20000 (131,072 bytes = 256 FAT entries)

### 8.3 Map Splitting

When approaching 4 GB, split into multiple `.img` files by geographic region (e.g., large maps are split by region). Each file is self-contained with no cross-file references.


## 9. Garmin Date Format

### 9.1 6-byte Header Date (at offset 0x39)

```
bytes 0-1: year   (uint16 LE)
byte 2:    month  (1-12)
byte 3:    day    (1-31)
byte 4:    hour   (0-23)
byte 5:    second (0-59)
```

### 9.2 7-byte Sub-Header Date (in common headers)

Same as 6-byte but with an additional byte for day-of-week (or padding):

```
bytes 0-1: year   (uint16 LE)
byte 2:    month  (1-12)
byte 3:    day    (1-31)
byte 4:    hour   (0-23)
byte 5:    minute (0-59)
byte 6:    second (0-59)
byte 7:    dow    (0, padding)
```
