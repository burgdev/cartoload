# Garmin IMG Test Samples

This directory contains test data for analyzing and validating the Garmin IMG format implementation.

## Sample Files

### SwissTopo Raster Maps (Swiss Topographic Maps)

These are real-world Garmin raster IMG files used for format reverse-engineering and validation.

**West Region:**

- File: `SwissTopo_West.img` (symlink to `/home/tobias/kdrive/garmin/my_SwissTopo_West.img`)
- Size: 1,495,072,768 bytes (1.4 GB)
- Map name: Svizzera_W Raster Map
- Coverage: Western Switzerland (W: 5.87°, E: 8.40°, S: 45.82°, N: 47.65°)
- Tiles: 32,443 JPEG-compressed tiles
- Zoom levels: [20, 21, 22, 23, 24]
- Created: 2022-04-16

**East Region:**

- File: `SwissTopo_Est.img` (symlink to `/home/tobias/kdrive/garmin/my_SwissTopo_Est.img`)
- Size: 1,421,049,856 bytes (1.4 GB)
- Map name: Svizzera_E Raster Map
- Coverage: Eastern Switzerland (W: 8.38°, E: 10.69°, S: 45.80°, N: 47.86°)
- Tiles: 28,737 JPEG-compressed tiles
- Zoom levels: [20, 21, 22, 23, 24]
- Created: 2022-04-20

### Analyzed Data

**GMT Output Files:**

- `SwissTopo_West_gmt_output.txt` - Verbose info from `gmt -i -v`
- `SwissTopo_Est_gmt_output.txt` - Verbose info from `gmt -i -v`

**Hex Dumps:**

- `SwissTopo_West_header_hex.txt` - First 512 bytes (header)
- `SwissTopo_Est_header_hex.txt` - First 512 bytes (header)

## Device Compatibility

These files are confirmed working on:

- ✅ **Garmin Fenix 6** (user-tested)
- Likely compatible with: Fenix 7, Fenix 8, Epix, other modern Garmin devices

## Usage

### Validation Script

Run the validation script to verify data model parsing:

```bash
python tests/validate_img_model.py
```

This script:

1. Parses GMT output into `IMGFile` data model instances
2. Validates all fields are captured correctly
3. Cross-references against expected values
4. Reports any discrepancies

### Generating GMT Output

To generate GMT output from the IMG files:

```bash
gmt -i -v SwissTopo_West.img > SwissTopo_West_gmt_output.txt
gmt -i -v SwissTopo_Est.img > SwissTopo_Est_gmt_output.txt
```

### Generating Hex Dumps

To generate hex dumps of the first 512 bytes:

```bash
xxd -l 512 SwissTopo_West.img > SwissTopo_West_header_hex.txt
xxd -l 512 SwissTopo_Est.img > SwissTopo_Est_header_hex.txt
```

## Format Documentation

See detailed format specification:

- **Format spec:** `docs/exporters/garmin-img.md`
- **Resources:** `docs/exporters/garmin-img-resources.md`
- **Data model:** `src/cartoload/exporters/garmin_img_model.py`

## Notes

- These are **raster IMG files**, not vector IMG files
- They use the GMP subfile format for storing JPEG-compressed tiles
- Block size: 32,768 bytes (32 KB)
- Compression: JPEG (type 4)
- Character encoding: Windows CP-1252 (Western European)
- Draw order priority: 24 (standard for raster basemaps)

## References

- **GMapTool (gmt):** http://www.gmaptool.eu/ - Used for analysis
- **Source:** SwissTopo official Garmin maps
- **Project:** cartoload - Open-source Garmin raster IMG creator
