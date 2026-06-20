## Context

The Garmin IMG raster exporter (`garmin_img_writer.py`) generates binary IMG files that differ structurally from SwissTopo reference files (both West and East). Field-by-field comparison using `img_analysis.py` and GMT revealed 8 specific differences in the TRE header, extended sections, and RGN1 area. The most visible symptom is GMT showing `>-  >TestMap` instead of a hex map ID like `09C102B0  >Svizzera_W Raster Map`.

All fixes target `garmin_img_writer.py` in the `_build_tre_subheader()` function and the GMP layout/write logic. The model file (`garmin_img_model.py`) needs no changes.

## Goals / Non-Goals

**Goals:**
- Match SwissTopo_West and SwissTopo_Est TRE header binary structure exactly
- Fix TRE5, TRE7 pad, TRE8, TRE9/TRE10, name area, and TRE3 copyright fields
- Make GMT display correct map name and metadata
- Maintain backward compatibility with existing test suite (93 tests passing)

**Non-Goals:**
- Implementing RGN1 data generation (SwissTopo has ~1.5KB but its purpose is unclear — leave RGN1 empty for now)
- Changing the subdivision system or spatial layout
- Changing tile extraction or JPEG encoding

## Decisions

### 1. TRE5: Write 3-byte data `4b 02 01` instead of leaving empty

SwissTopo_West and SwissTopo_Est both have TRE5 with size=3, rec_size=3, data=`4b 02 01`, pad=`01 00 00 00`. Our output has size=0, rec_size=2, pad=`00 00 00 00`.

**Decision**: Write TRE5 as a separate 3-byte section (`4b 02 01`) with rec_size=3 and pad flag `01 00 00 00`. This requires allocating TRE5 at its own position (currently it shares TRE8's position with size=0).

**Rationale**: Both SwissTopo references agree. The `4b` byte likely encodes a parameter (0x4B = 75), `02` and `01` are sub-parameters. Without official docs, we match the reference exactly.

### 2. TRE8: Single entry `06 02 13` instead of two entries

SwissTopo references have 1 entry (3 bytes): type=0x06, param1=0x02, param2=0x13. Our output has 2 entries (6 bytes): `06 06 13 0d 06 01`. The extra entry `0d 06 01` is incorrect. The pad at 0x94 should be `00 00 01 00` not `00 00 00 00`.

**Decision**: Write TRE8 as 3 bytes (`06 02 13`) with pad `00 00 01 00`. This changes `tre8_size` from 6 to 3 and the param1 byte from 0x06 to 0x02.

**Rationale**: SwissTopo uses param1=0x02 (not 0x06). The second entry (`0d 06 01`) appears nowhere in the references. The pad `00 00 01 00` is a flag byte at 0x96 = 0x01.

### 3. TRE7 pad at 0x86: `81 04 00 00`

SwissTopo has `81 04 00 00` (which is 0x0481 LE = 1153). Our output has `01 00 00 00`.

**Decision**: Write `81 04 00 00` at offset 0x86-0x89 in the TRE header. This is a 4-byte field — currently only 2 bytes are written (`buf[0x86] = 0x01, buf[0x87] = 0x00`). Need to write all 4 bytes as `0x81, 0x04, 0x00, 0x00`.

**Rationale**: This value likely encodes flags + record count or offset information. Both SwissTopo East and West agree.

### 4. TRE name area at 0xD3: Binary zeros instead of ASCII

SwissTopo has binary data (extended TRE field references) at offset 0xD3. We write the ASCII map name "TestMap\0", which GMT interprets as garbage (`>-`).

**Decision**: Write binary zeros at 0xD3 instead of the map name string. The TRE name area is not a human-readable field in raster IMG files.

**Rationale**: The map name is already in the GMP container header and MPS subfile. SwissTopo uses 0xD3 for extended binary data. Writing ASCII there corrupts the TRE header from GMT's perspective.

### 5. TRE9/TRE10: Point to RGN1 position

SwissTopo has TRE9 and TRE10 pointing to the RGN1 section position with TRE10 rec_size=1. Our output leaves both at pos=0, rec_size=0.

**Decision**: Set TRE9 position = RGN1 position, TRE10 position = RGN1 position. Set TRE10 rec_size=1. Even though RGN1 has size=0 (no data), the positions must point to valid section offsets.

**Rationale**: SwissTopo points these to RGN1. Having pos=0 causes GMT to read from offset 0 (the main header), producing garbage.

### 6. TRE3 copyright: Label offset indices

SwissTopo has `0c 00 00 32 00 00` (6 bytes). Our output has hardcoded `00 80 a4 4f 05 58`.

**Decision**: Write `0c 00 00 32 00 00` as the TRE3 copyright data. This matches the SwissTopo format where the first 3 bytes are label offset indices.

**Rationale**: The hardcoded value `00 80 a4 4f 05 58` has no documented meaning. SwissTopo's `0c 00 00 32 00 00` is consistent across both East and West references.

## Risks / Trade-offs

- **RGN1 remains empty**: SwissTopo has ~1.5KB of RGN1 data but we don't know its format. → Mitigation: RGN1 with size=0 is acceptable; TRE9/TRE10 will point to the correct position.
- **TRE5 data meaning unknown**: `4b 02 01` may have specific semantics we don't understand. → Mitigation: Exact binary match with reference files is the safest approach for device compatibility.
- **TRE7 pad value `81 04 00 00`**: The exact meaning is unclear (possibly flags + offset). → Mitigation: Both SwissTopo East and West agree on this value.
- **GMT map listing shows `>-` instead of hex ID**: GMT reads a proprietary map ID hash at TRE offset 0x9A (10 bytes) to compose the map name prefix. We cannot compute this hash without reverse-engineering Garmin's algorithm. → Mitigation: This is purely cosmetic in GMT's listing display. The map data is correctly detected (Bitmaps, correct bounds, correct CP). Garmin devices use the FAT name and MPS subfile, not this hash.
