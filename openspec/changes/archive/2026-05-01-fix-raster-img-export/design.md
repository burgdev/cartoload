## Context

Cartoload writes Garmin IMG raster map files entirely in Python — no external proprietary tools (bld_gmap32.exe, gmt.exe) are used. The current implementation produces files that GMT can parse, but Garmin devices don't render the raster tiles.

Reference implementations (jnx2img, SasPlanet) both delegate to `bld_gmap32.exe` (Garmin's proprietary MapSource Product Creator) for the actual binary IMG compilation. This means no open-source reference exists for the exact binary format of raster IMG files — we had to reverse-engineer it from the SwissTopo_West.img reference file and by studying GPXSee's parser.

The key architectural insight from studying GPXSee's RGN parser (`rgnfile.cpp`):

```
┌─────────────────────────────────────────────────────────────┐
│  How Garmin Devices Parse Raster Tiles                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TRE7 entries (per subdivision):                            │
│    [uint32 extPolygonsOffset] [padding...]                  │
│    → Points into _polygons section of RGN (i.e., RGN2)     │
│    → Each entry's offset = START of that subdivision's data │
│    → Next entry's offset = END of this subdivision's data   │
│                                                             │
│  RGN sub-header:                                            │
│    0x15: _base (RGN1) offset + size                         │
│    0x1D: _polygons (RGN2) offset + size                     │
│    0x25+: _polygons extended section (optional for NT)      │
│                                                             │
│  RGN2 parsing per subdivision:                              │
│    segment = {start, end} from TRE7 offsets + _polygons.off │
│    while pos < segment.end:                                 │
│      read type(1) + subtype(1) + lon(2) + lat(2) + len(var) │
│      poly.type = 0x10000 | (type<<8) | (subtype & 0x1F)    │
│      if type==0x06 && subtype==0xB3:                        │
│        poly.type = 0x10613 → isRaster()                     │
│        subtype & 0x80 → readClassFields → readRasterInfo    │
│        readRasterInfo: read imgId(var) + top(4) + right(4)  │
│                         + bottom(4) + left(4)               │
│        → fetches JPEG from LBL29 via LBL28[imageId]        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Goals / Non-Goals

**Goals:**
- Fix the IMG binary format so raster maps display on Garmin devices
- Make the analysis tool capable of validating TRE7/RGN2 consistency
- Add structured comparison to detect format regressions against reference files
- Maintain compatibility with the existing pipeline (no architectural changes to the export flow)

**Non-Goals:**
- Supporting vector map export (only raster)
- Matching jnx2img exactly byte-for-byte (different maps will always differ)
- Supporting NT format (only OF_GMP format, same as SwissTopo reference)
- Multi-volume splitting fixes (separate concern)

## Decisions

### 1. RGN2 segment boundaries via TRE7 offsets

**Decision**: TRE7 entries encode per-subdivision RGN2 segment boundaries as pairs: each entry's `extPolygonsOffset` is the start of that subdivision's data, and the next entry's offset is the end. This is how GPXSee's `subdivInit` constructs segments.

**Current bug**: Our TRE7 offsets point to the correct RGN2 positions, but the RGN header's `_polygons` section (at offset 0x1D-0x24) is used as the base address. The TRE7 offsets must be **relative to `_polygons.offset`**, not the full RGN start. We currently write them as offsets from RGN2 start, which is the same thing since `_polygons.offset = rgn2_pos`. This part appears correct.

**However**, the critical issue is that GPXSee uses TRE7 offsets to form **segment boundaries**. Each subdivision's extended polygon data spans from its own offset to the next subdivision's offset. Our current code writes all RGN2 data as one contiguous block per subdivision but doesn't ensure the TRE7 offsets correctly delimit each subdivision's segment within the RGN2 section.

**Rationale**: Verified from GPXSee `trefile.cpp:241-256` and `rgnfile.cpp:1103-1130`.

### 2. RGN sub-header `_polygons` extended section

**Decision**: The RGN sub-header has fields at offsets 0x25-0x2C for the extended polygons section (separate from the base RGN2 at 0x1D). For NT/GMP format raster maps, this section may need to be populated.

**Current state**: Our RGN header is 125 bytes with mostly zeros after offset 0x25. The SwissTopo reference has non-zero bytes at 0x25, 0x2D-0x33, 0x39-0x3B, etc.

**Approach**: Do a hex comparison of our RGN sub-header vs SwissTopo to identify which fields need values. The non-zero bytes in the reference RGN header likely encode the extended polygons section position/size that GPXSee reads for NT-format maps.

### 3. Polyline preamble encoding

**Decision**: Keep the 0x06/0xB3 preamble type encoding (confirmed correct via GPXSee: `type=0x06, subtype=0xB3 → poly.type = 0x10613 → isRaster()`). But fix the bitstream content.

**Current issue**: The preamble's bitstream (16 bytes after type+subtype) encodes the tile's geographic extent as coordinate deltas from the subdivision center. Our encoding uses a custom `_pack_signed_bits` function that may produce incorrect bitstream format.

**Approach**: Compare the SwissTopo reference's polyline preambles byte-by-byte with what our code generates for the same coordinates. The reference shows preambles like `06 B3 9C F1 F5 09 11 56 F2 08 00 80 1C 17 00 53 00 00`. Decode these to understand the exact bitstream format expected by devices.

### 4. E0 record format verification

**Decision**: The E0 record format appears mostly correct: `E0(1) + bits(1) + imgIdx(2) + top(4) + right(4) + bottom(4) + left(4) + size(4) = 24 bytes`. This matches GPXSee's `readRasterInfo` which reads `imgId(varSize) + top(u32) + right(u32) + bottom(u32) + left(u32)`.

**Note**: GPXSee reads the image ID as a variable-length uint (`readVUInt32`) whose size depends on `lbl->imageIdSize()`, which is derived from the number of images. Our code always uses `bits_field=0x2D` (16-bit index). This needs verification against the reference.

### 5. Analysis tool improvements

**Decision**: Add generic validation capabilities rather than raster-specific hacks:
- **Section consistency check**: Verify TRE7 offsets map to valid RGN2 regions
- **Structured section dump**: Parse and display RGN2 records per subdivision using TRE7 segment boundaries
- **Section comparison**: Compare corresponding sections between two IMG files at the parsed-record level

**Rationale**: These improvements help debug any future format issues too, not just the current raster problem.

## Risks / Trade-offs

- **[No open-source writer reference]** → Use GPXSee (reader) and SwissTopo (reference binary) as ground truth. Risk: reader may be lenient where devices are strict. Mitigation: test on actual device after each fix.
- **[Polyline bitstream is complex]** → The Garmin bitstream encoding is poorly documented and our custom pack function could have subtle bugs. Mitigation: decode reference preambles first, then match the encoding exactly.
- **[Multiple issues may be present]** → There could be several independent format issues preventing display. Mitigation: fix incrementally — validate with GPXSee parsing first, then test on device.
- **[Analysis tool changes may be extensive]** → Improving the analysis tool alongside the fix could double the scope. Mitigation: keep analysis changes minimal and focused on the validation we actually need.
