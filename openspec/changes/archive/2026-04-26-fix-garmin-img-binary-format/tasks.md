## 1. TRE5 Section Fix

- [x] 1.1 Add TRE5 as a separate 3-byte section in GMP layout (allocate `tre5_pos` separate from `tre8_pos`, set `tre5_size=3`)
- [x] 1.2 Write TRE5 data bytes `4B 02 01` in the GMP data section
- [x] 1.3 Update TRE5 descriptor in `_build_tre_subheader()`: position=tre5_pos, size=3, rec_size=3, pad=`01 00 00 00`

## 2. TRE8 Section Fix

- [x] 2.1 Change `tre8_size` from 6 to 3 in LayoutComputer and GMPWriter
- [x] 2.2 Write TRE8 data as `06 02 13` (single entry) instead of `06 06 13 0d 06 01` (two entries)
- [x] 2.3 Update TRE8 pad at offset 0x94 in `_build_tre_subheader()` from `00 00 00 00` to `00 00 01 00`

## 3. TRE7 Pad Fix

- [x] 3.1 Change TRE7 pad bytes at offset 0x86 in `_build_tre_subheader()` from `01 00 00 00` to `81 04 00 00`

## 4. TRE Name Area Fix

- [x] 4.1 Replace ASCII map name at TRE offset 0xD3 with binary zeros in `_build_tre_subheader()`

## 5. TRE9/TRE10 Fix

- [x] 5.1 Add TRE9 descriptor fields at offset 0xAE: position=RGN1 position, size=0, rec_size=0
- [x] 5.2 Add TRE10 descriptor fields at offset 0xBC: position=RGN1 position, size=0, rec_size=1

## 6. TRE3 Copyright Fix

- [x] 6.1 Replace hardcoded `00 80 a4 4f 05 58` TRE3 copyright data with `0C 00 00 32 00 00`

## 7. Size Accounting

- [x] 7.1 Update `_compute_gmp_size()` to account for the new TRE5 section (3 bytes) and reduced TRE8 size (3 instead of 6)

## 8. Tests

- [x] 8.1 Add test verifying TRE5 descriptor: position, size=3, rec_size=3, pad bytes
- [x] 8.2 Add test verifying TRE8 data is `06 02 13` (3 bytes) with correct pad
- [x] 8.3 Add test verifying TRE7 pad is `81 04 00 00`
- [x] 8.4 Add test verifying TRE name area at 0xD3 is all zeros
- [x] 8.5 Add test verifying TRE9/TRE10 point to RGN1 position with rec_size=1
- [x] 8.6 Add test verifying TRE3 copyright data is `0C 00 00 32 00 00`
- [x] 8.7 Run full test suite and verify all 93+ tests pass
