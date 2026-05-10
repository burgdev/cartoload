# Garmin IMG Format — Overview

The Garmin IMG format is a proprietary binary container used by Garmin GPS devices to store map data. This page provides a high-level overview. For byte-level details, see the [detailed specification](detailed-spec.md).

## Two Variants: Raster and Vector

The IMG format supports two fundamentally different map types:

| | Raster | Vector |
|---|---|---|
| **Content** | JPEG tile imagery (aerial photos, topo scans) | Points, polylines, polygons |
| **Rendering** | Pre-rendered images | Device renders from geometry |
| **Search/routing** | Limited | Full support |
| **Tool support** | Very limited | Extensive (mkgmap, cGPSmapper) |
| **File size** | Large (imagery) | Compact |

**cartoload currently supports raster IMG only.** Vector IMG generation is planned for a future release.

## File Structure

An IMG file is a self-contained filesystem with three main layers:

```
┌────────────────────────────────────────┐
│ IMG File                               │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │ Header (512 bytes)               │  │
│  │  - Magic: DSKIMG                 │  │
│  │  - Block size, creation date     │  │
│  ├──────────────────────────────────┤  │
│  │ FAT (File Allocation Table)      │  │
│  │  - Lists subfiles and block      │  │
│  │    locations                      │  │
│  ├──────────────────────────────────┤  │
│  │ Subfiles                          │  │
│  │  ┌────────────────────────────┐  │  │
│  │  │ GMP (Garmin Map Package)  │  │  │
│  │  │  - TRE: spatial index     │  │  │
│  │  │  - RGN: map data          │  │  │
│  │  │  - LBL: labels/images     │  │  │
│  │  │  - NET: routing (vector)  │  │  │
│  │  └────────────────────────────┘  │  │
│  │  ┌────────────────────────────┐  │  │
│  │  │ MPS (MapSource metadata)   │  │  │
│  │  └────────────────────────────┘  │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

### Single-map vs multi-map

An IMG file can contain one or many GMP subfiles:

- **Single-map**: One GMP subfile covering the entire area (e.g., a city map)
- **Multi-map**: Multiple GMP subfiles, each covering a geographic tile (e.g., the IOM reference file has 51 subfiles)

## How Raster Tiles Are Stored

Raster IMG files store map imagery as JPEG tiles inside the GMP subfile:

1. **TRE** defines the spatial index — zoom levels and subdivisions (rectangular map regions)
2. **RGN2** contains metadata records for each tile — position, size, and which JPEG image it references
3. **LBL28** is an index table pointing to JPEG offsets
4. **LBL29** contains the concatenated JPEG data

When a device displays the map, it:

1. Finds subdivisions overlapping the current view (from TRE)
2. Reads tile metadata from RGN2
3. Fetches the JPEG from LBL29 via LBL28 index
4. Renders the JPEG at the correct position

## Device Compatibility

| Device type | Raster IMG | Vector IMG |
|---|---|---|
| Fenix watches (6+) | Yes | Yes |
| Handheld GPS (GPSMap, Montana, Oregon) | Yes | Yes |
| Automotive (Drive, DriveSmart) | Limited | Yes |

Raster IMG maps work on both Garmin watches and handheld GPS units.

## Further Reading

- [Detailed specification](detailed-spec.md) — complete binary format reference with byte offsets and field descriptions
- [Tools & resources](tools-resources.md) — third-party tools, format documentation, and reference implementations
