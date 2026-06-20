## Context

The Garmin IMG FAT (File Allocation Table) format has two size limits:

1. **FAT part number limit**: 1-byte part number at offset 0x11, max 256 entries per subfile, each covering 240 × 32KB = 7.5 MB. Limit per GMP subfile: ~1.88 GB.

2. **FAT block number limit**: Block numbers are uint16 (confirmed in GPXSee's `imgdata.cpp`), so the total addressable space is 65535 × 32KB = **~2 GB per IMG file**. This is a hard limit — block numbers > 65535 cause `struct.pack` overflow.

SwissTopo's 1.4 GB file is safely under both limits.

GPXSee creates one `VectorTile` per unique 8-byte FAT name in the IMG file. Multiple GMP subfiles in one IMG file are supported. However, even with multiple GMP subfiles, the total IMG file cannot exceed ~2 GB due to the uint16 block number limit.

For maps exceeding ~2 GB total (e.g. Switzerland at 11 GB), the only option is **multiple IMG files**, each under the ~2 GB limit.

## Goals / Non-Goals

**Goals:**
- Produce IMG file(s) for any map size by splitting into geographic bands when needed
- Each IMG file stays under ~1.8 GB (both the FAT part number and block number limits)
- GPXSee correctly renders all tiles from all IMG files
- Preserve existing behavior for maps that fit in a single IMG (<1.8 GB)

**Non-Goals:**
- Optimal balancing of IMG file sizes (close-enough is fine)
- Single IMG file for maps > 2 GB (not possible due to uint16 block numbers)
- Changing the Garmin IMG binary format itself

## Decisions

### Decision 1: Multiple IMG files (not multiple GMP subfiles in one IMG)

The initial approach was multiple GMP subfiles in one IMG file. This was **rejected** after discovering the uint16 block number limit (~2 GB total per IMG). Even with multiple GMP subfiles, the combined block numbers overflow.

**Revised approach**: When total map data exceeds `MAX_GMP_SIZE`, partition tiles into geographic latitude bands and write each band as a **separate IMG file**. Each IMG file has its own FAT, headers, and GMP subfile.

**Trade-off**: Users get multiple files (e.g. `switzerland_1.img`, `switzerland_2.img`, ...) instead of one. GPXSee loads all `.img` files from a directory, so this works for viewing. Garmin devices also handle multiple map files.

### Decision 2: Geographic bands for tile assignment

Sort tiles by center latitude, compute cumulative JPEG size, split at boundaries where adding more tiles would exceed `MAX_GMP_SIZE * 0.7` (the 0.7 factor accounts for header/RGN2 overhead).

### Decision 3: MAX_GMP_SIZE = 1.8 GB

Define `MAX_GMP_SIZE = 1_800_000_000` (~1.73 GB) as the practical per-IMG-file limit. This is below both the FAT part number limit (~1.88 GB) and the block number limit (~2 GB), providing margin for overhead.

### Decision 4: Each IMG file has full map bounds

Each IMG file's TRE contains the full map bounds (not just the band's geographic range). This ensures GPXSee's zoom level filtering works correctly — all files are visible at all zoom levels.

## Risks / Trade-offs

- **[User experience]** → Multiple files instead of one. Mitigated by GPXSee loading all `.img` files from a directory. Garmin devices also handle multiple map files.
- **[Map ID collisions]** → Each IMG file needs a unique map ID. Use `map_id + band_index` to derive unique IDs.
- **[File size overhead]** → Each IMG file has its own headers (~1KB each). Negligible for large maps.
