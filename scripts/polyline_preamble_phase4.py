#!/usr/bin/env python3
"""
Phase 4: Final confirmation of the polyline preamble encoding.

KEY FINDING from Phase 3:
- b01 * 4 gives the exact lon_min delta in 24-bit map units
- The ratio between consecutive b01 differences and lon differences is exactly 4.0
- So: lon_min_24 = some_center_lon_24 + b01 * 4
- But group 0 center doesn't work (offset of ~43632)

The question is: what is the actual center coordinate being used?
And is it the same for ALL tiles, or does it change per subdivision?
"""

import struct
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.img_analysis import IMGParser

IMG_PATH = "/home/tobias/kdrive/garmin/my_SwissTopo_West.img"


def garmin_32_to_deg(val):
    return val * 180.0 / (2**31)


def map_units_24_to_deg(val):
    return val * 360.0 / (2**24)


def deg_to_map_units_24(deg):
    return int(deg * (2**24) / 360)


def main():
    print("=" * 80)
    print("Phase 4: Confirm the Polyline Preamble Center Coordinate")
    print("=" * 80)

    with IMGParser(IMG_PATH) as img:
        img.parse_header()
        img.parse_fat()

        gmp_key = None
        for key in img.subfiles:
            if img.subfiles[key]["type"] == "GMP":
                gmp_key = key
                break

        gmp = img.parse_gmp_container(gmp_key)
        data = gmp["data"]

        tre = img.parse_tre(gmp)
        rgn = img.parse_rgn(gmp)
        groups = tre.get("groups_16byte", [])

        rgn2_pos = rgn["rgn2"]["position"]
        rgn2_size = rgn["rgn2"]["size"]
        rgn2_data = data[rgn2_pos : rgn2_pos + rgn2_size]

        # Parse first 72 polyline+E0 pairs
        pos = 0
        records = []
        while pos < min(len(rgn2_data), 5000):
            if rgn2_data[pos] == 0x06 and rgn2_data[pos + 1] == 0xB3:
                preamble = rgn2_data[pos + 2 : pos + 18]
                e0_pos = pos + 18
                if e0_pos + 24 <= len(rgn2_data) and rgn2_data[e0_pos] == 0xE0:
                    bits_field = rgn2_data[e0_pos + 1]
                    idx_size = 2 if bits_field in (0x2D, 0x25) else 1
                    img_idx = struct.unpack_from(
                        "<H" if idx_size == 2 else "<B", rgn2_data, e0_pos + 2
                    )[0]
                    coord_off = e0_pos + 2 + idx_size
                    lat_min = struct.unpack_from("<i", rgn2_data, coord_off)[0]
                    lon_min = struct.unpack_from("<i", rgn2_data, coord_off + 4)[0]
                    lat_max = struct.unpack_from("<i", rgn2_data, coord_off + 8)[0]
                    lon_max = struct.unpack_from("<i", rgn2_data, coord_off + 12)[0]

                    records.append(
                        {
                            "preamble": bytes(preamble),
                            "lat_min": lat_min,
                            "lon_min": lon_min,
                            "lat_max": lat_max,
                            "lon_max": lon_max,
                            "img_idx": img_idx,
                            "rgn2_offset": pos,
                        }
                    )
                    pos = e0_pos + 2 + idx_size + 16 + 4
                    continue
            pos += 1

        print(f"Parsed {len(records)} records")

        # =====================================================================
        # STEP 1: Compute the exact center from the first record
        # =====================================================================
        print("\n--- Computing center coordinate ---")

        rec = records[0]
        b01 = struct.unpack_from("<h", rec["preamble"], 0)[0]
        b23 = struct.unpack_from("<h", rec["preamble"], 2)[0]
        b45 = struct.unpack_from("<h", rec["preamble"], 4)[0]
        b67 = struct.unpack_from("<h", rec["preamble"], 6)[0]

        e0_lat_min_24 = rec["lat_min"] >> 8
        e0_lon_min_24 = rec["lon_min"] >> 8
        e0_lat_max_24 = rec["lat_max"] >> 8
        e0_lon_max_24 = rec["lon_max"] >> 8

        # If lon_min_24 = center_lon + b01 * 4
        # Then: center_lon = lon_min_24 - b01 * 4
        center_lon_from_b01 = e0_lon_min_24 - b01 * 4
        center_lat_from_b23 = e0_lat_min_24 - b23 * 4

        # Also compute from b67 (lon_max) and b45 (lat_max?)
        center_lon_from_b67 = e0_lon_max_24 - b67 * 4
        center_lat_from_b45 = e0_lat_max_24 - b45 * 4

        print(f"\n  From b01 (lon_min): center_lon_24 = {center_lon_from_b01}")
        print(f"  From b23 (lat_min): center_lat_24 = {center_lat_from_b23}")
        print(f"  From b67 (lon_max): center_lon_24 = {center_lon_from_b67}")
        print(f"  From b45 (lat_max): center_lat_24 = {center_lat_from_b45}")

        print(
            f"\n  Center lon consistency: {center_lon_from_b01 == center_lon_from_b67}"
        )
        print(f"  Center lat consistency: {center_lat_from_b23 == center_lat_from_b45}")

        if center_lon_from_b01 != center_lon_from_b67:
            print(f"  Lon diff: {center_lon_from_b01 - center_lon_from_b67}")
        if center_lat_from_b23 != center_lat_from_b45:
            print(f"  Lat diff: {center_lat_from_b23 - center_lat_from_b45}")

        # Verify with multiple records
        print("\n  Verifying center with all records:")
        center_lons = []
        center_lats = []
        for rec in records[:20]:
            b01 = struct.unpack_from("<h", rec["preamble"], 0)[0]
            b23 = struct.unpack_from("<h", rec["preamble"], 2)[0]

            cl = (rec["lon_min"] >> 8) - b01 * 4
            cla = (rec["lat_min"] >> 8) - b23 * 4
            center_lons.append(cl)
            center_lats.append(cla)

        unique_lons = set(center_lons)
        unique_lats = set(center_lats)
        print(f"    Unique center lon values: {unique_lons}")
        print(f"    Unique center lat values: {unique_lats}")

        # Now decode ALL preamble fields using this center
        center_lon = list(unique_lons)[0]
        center_lat = list(unique_lats)[0]

        print(
            f"\n  Computed center: lon_24={center_lon} ({map_units_24_to_deg(center_lon):.6f}), "
            f"lat_24={center_lat} ({map_units_24_to_deg(center_lat):.6f})"
        )

        # =====================================================================
        # STEP 2: Verify the complete preamble structure
        # =====================================================================
        print("\n--- Verifying complete preamble structure ---")

        print(
            "\n  Format: b01=lon_min_delta/4, b23=lat_min_delta/4, b45=lat_max_delta/4?, b67=lon_max_delta/4?"
        )
        print("  All deltas in 24-bit map units, multiplied by 4")

        for i in range(min(10, len(records))):
            rec = records[i]
            b01 = struct.unpack_from("<h", rec["preamble"], 0)[0]
            b23 = struct.unpack_from("<h", rec["preamble"], 2)[0]
            b45 = struct.unpack_from("<h", rec["preamble"], 4)[0]
            b67 = struct.unpack_from("<h", rec["preamble"], 6)[0]

            computed_lon_min = center_lon + b01 * 4
            computed_lat_min = center_lat + b23 * 4
            computed_lat_max = center_lat + b45 * 4
            computed_lon_max = center_lon + b67 * 4

            actual_lon_min = rec["lon_min"] >> 8
            actual_lat_min = rec["lat_min"] >> 8
            actual_lon_max = rec["lon_max"] >> 8
            actual_lat_max = rec["lat_max"] >> 8

            match_lon_min = computed_lon_min == actual_lon_min
            match_lat_min = computed_lat_min == actual_lat_min
            match_lon_max = computed_lon_max == actual_lon_max
            match_lat_max = computed_lat_max == actual_lat_max

            print(f"\n  Record {i} (img_idx={rec['img_idx']}):")
            print(
                f"    lon_min: computed={computed_lon_min}, actual={actual_lon_min}, match={match_lon_min}"
            )
            print(
                f"    lat_min: computed={computed_lat_min}, actual={actual_lat_min}, match={match_lat_min}"
            )
            print(
                f"    lat_max: computed={computed_lat_max}, actual={actual_lat_max}, match={match_lat_max}"
            )
            print(
                f"    lon_max: computed={computed_lon_max}, actual={actual_lon_max}, match={match_lon_max}"
            )

            if not all([match_lon_min, match_lat_min, match_lon_max, match_lat_max]):
                # Try different field orderings
                print("    Trying alternate orderings...")

                # Maybe b45 = lon_max and b67 = lat_max?
                alt_lon_max = center_lon + b45 * 4
                alt_lat_max = center_lat + b67 * 4
                print(
                    f"    Alt: b45→lon_max={alt_lon_max} (actual={actual_lon_max}), "
                    f"b67→lat_max={alt_lat_max} (actual={actual_lat_max})"
                )

        # =====================================================================
        # STEP 3: What are the remaining bytes 8-15?
        # =====================================================================
        print("\n--- Analyzing bytes 8-15 ---")

        for i in range(min(10, len(records))):
            rec = records[i]
            b8_9 = struct.unpack_from("<H", rec["preamble"], 8)[0]
            b10_11 = struct.unpack_from("<H", rec["preamble"], 10)[0]
            b12_13 = struct.unpack_from("<H", rec["preamble"], 12)[0]
            b14_15 = struct.unpack_from("<H", rec["preamble"], 14)[0]

            print(
                f"  Record {i}: b8-9={b8_9} b10-11={b10_11} b12-13={b12_13} b14-15={b14_15} "
                f"img_idx={rec['img_idx']} blk_sz={rec.get('block_size', 'N/A')}"
            )

        # b8-9 is always 0x0080 = 32768 (or -32768 as int16)
        # b10-11 is either 0x171C = 5916 or 0x170C = 5900
        #   5916 - 5900 = 16
        #   This might be the tile width in pixels? 256/4 = 64? No...
        #   Or maybe it's related to the bitmap format.
        # b12-13 increments and seems related to image offset
        # b14-15 is always 0

        # Let me check b10-11 vs the tile's lat extent
        print("\n  b10-11 vs tile lat extent:")
        for i in range(min(10, len(records))):
            rec = records[i]
            b10_11 = struct.unpack_from("<h", rec["preamble"], 10)[0]
            lat_extent_deg = garmin_32_to_deg(rec["lat_min"]) - garmin_32_to_deg(
                rec["lat_max"]
            )
            lon_extent_deg = garmin_32_to_deg(rec["lon_max"]) - garmin_32_to_deg(
                rec["lon_min"]
            )

            print(
                f"  Record {i}: b10-11={b10_11}, lat_ext_deg={lat_extent_deg:.6f}, "
                f"lon_ext_deg={lon_extent_deg:.6f}, "
                f"lat_ext*4={lat_extent_deg * 4:.4f}, lon_ext*4={lon_extent_deg * 4:.4f}"
            )

        # =====================================================================
        # STEP 4: Check what the actual center is
        # =====================================================================
        print("\n--- What is the computed center? ---")

        print(
            f"  Computed center: ({map_units_24_to_deg(center_lat):.6f}, {map_units_24_to_deg(center_lon):.6f})"
        )
        print(f"  In 24-bit map units: lat={center_lat}, lon={center_lon}")
        print(f"  In 32-bit map units: lat={center_lat << 8}, lon={center_lon << 8}")

        # Compare with TRE bounds
        print("\n  TRE bounds:")
        print(f"    North: {tre['north_deg']:.6f} ({tre['north']})")
        print(f"    South: {tre['south_deg']:.6f} ({tre['south']})")
        print(f"    West: {tre['west_deg']:.6f} ({tre['west']})")
        print(f"    East: {tre['east_deg']:.6f} ({tre['east']})")

        # Compare with group centers
        print("\n  Group centers near computed center:")
        for i, g in enumerate(groups[:10]):
            dist_lat = abs(g["lat_center"] - center_lat)
            dist_lon = abs(g["lon_center"] - center_lon)
            if dist_lat < 1000 and dist_lon < 1000:
                print(
                    f"    Group {i}: ({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f}) "
                    f"dist=({dist_lat}, {dist_lon})"
                )

        # The center doesn't match any group. It might be the TRE bounds origin
        # or some other reference point.
        # Let me check: is it the map bounds?
        map_west_24 = deg_to_map_units_24(tre["west_deg"])
        map_south_24 = deg_to_map_units_24(tre["south_deg"])
        map_north_24 = deg_to_map_units_24(tre["north_deg"])
        map_east_24 = deg_to_map_units_24(tre["east_deg"])

        print("\n  Map bounds in 24-bit:")
        print(f"    West: {map_west_24}")
        print(f"    South: {map_south_24}")
        print(f"    North: {map_north_24}")
        print(f"    East: {map_east_24}")
        print(f"    Center lon vs West: {center_lon - map_west_24}")
        print(f"    Center lat vs South: {center_lat - map_south_24}")

        # What about the group 0 center specifically?
        g0 = groups[0]
        print(f"\n  Group 0 center: lat={g0['lat_center']}, lon={g0['lon_center']}")
        print(
            f"    Delta from computed: lat={center_lat - g0['lat_center']}, lon={center_lon - g0['lon_center']}"
        )

        # Let me check: maybe the center is (0, 0) - i.e., the preamble encodes
        # absolute 24-bit coordinates divided by 4?
        print("\n  Checking if center is (0, 0):")
        print(f"    lon_min = b01*4 = {b01 * 4} vs actual {e0_lon_min_24}")
        # Nope, b01*4 for record 0 = -3684*4 = -14736, not 274300

        # =====================================================================
        # STEP 5: Maybe the preamble encodes absolute coords, not deltas
        # =====================================================================
        print("\n--- Preamble as absolute coordinates (divided by some factor) ---")

        for i in range(min(5, len(records))):
            rec = records[i]
            b01 = struct.unpack_from("<H", rec["preamble"], 0)[0]  # unsigned
            b23 = struct.unpack_from("<H", rec["preamble"], 2)[0]
            b45 = struct.unpack_from("<H", rec["preamble"], 4)[0]
            b67 = struct.unpack_from("<H", rec["preamble"], 6)[0]

            lon_min_24 = rec["lon_min"] >> 8
            lat_min_24 = rec["lat_min"] >> 8
            lon_max_24 = rec["lon_max"] >> 8
            lat_max_24 = rec["lat_max"] >> 8

            print(f"\n  Record {i}:")
            print(
                f"    b01={b01}, lon_min_24={lon_min_24}, ratio={lon_min_24 / b01 if b01 != 0 else 'N/A':.6f}"
            )
            print(
                f"    b23={b23}, lat_min_24={lat_min_24}, ratio={lat_min_24 / b23 if b23 != 0 else 'N/A':.6f}"
            )
            print(
                f"    b45={b45}, lon_max_24={lon_max_24}, ratio={lon_max_24 / b45 if b45 != 0 else 'N/A':.6f}"
            )
            print(
                f"    b67={b67}, lat_max_24={lat_max_24}, ratio={lat_max_24 / b67 if b67 != 0 else 'N/A':.6f}"
            )

        # =====================================================================
        # STEP 6: Let me try reading the QMapShack wiki
        # =====================================================================
        print("\n" + "=" * 80)
        print("Reading QMapShack Raster IMG Wiki")
        print("=" * 80)

        # I'll use the web reader to get the wiki page
        try:
            import urllib.request

            url = "https://raw.githubusercontent.com/Maproom/qmapshack/master/wiki/RasterImg_AWhiter.md"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                wiki_content = response.read().decode("utf-8")
                # Save to file for reference
                with open("/tmp/qmapshack_raster_wiki.md", "w") as f:
                    f.write(wiki_content)
                print(f"  Downloaded {len(wiki_content)} bytes")

                # Search for polyline/bitmap/RGN2 section
                lines = wiki_content.split("\n")
                for i, line in enumerate(lines):
                    if any(
                        kw in line.lower()
                        for kw in [
                            "polyline",
                            "bitmap",
                            "rgn2",
                            "0x06",
                            "type 6",
                            "subtype",
                        ]
                    ):
                        start = max(0, i - 2)
                        end = min(len(lines), i + 5)
                        print(f"\n  --- Line {i} context ---")
                        for j in range(start, end):
                            print(f"  {j:4d}: {lines[j]}")
        except Exception as e:
            print(f"  Failed to download wiki: {e}")

        # =====================================================================
        # STEP 7: The QMapShack wiki might use the "IOM" file's format.
        # Let me look at the IOM file's polyline structure instead.
        # =====================================================================
        iom_path = "/home/tobias/kdrive/garmin/IOM.img"
        if os.path.exists(iom_path):
            print("\n" + "=" * 80)
            print("IOM Reference Analysis")
            print("=" * 80)

            with IMGParser(iom_path) as iom:
                iom.parse_header()
                iom.parse_fat()

                iom_gmp_key = None
                for key in iom.subfiles:
                    if "00355951" in key:
                        iom_gmp_key = key
                        break

                if iom_gmp_key:
                    iom_gmp = iom.parse_gmp_container(iom_gmp_key)
                    iom_data = iom_gmp["data"]
                    iom_tre = iom.parse_tre(iom_gmp)
                    iom_rgn = iom.parse_rgn(iom_gmp)
                    iom_groups = iom_tre.get("groups_16byte", [])

                    iom_tre_off = iom_gmp["sections"]["TRE"]
                    iom_tre_bytes = iom_data[iom_tre_off:]

                    print(
                        f"\n  IOM TRE parameters (0x42-0x49): {iom_tre_bytes[0x42:0x4A].hex()}"
                    )

                    if "rgn2" in iom_rgn and iom_rgn["rgn2"]["size"] > 0:
                        iom_rgn2_pos = iom_rgn["rgn2"]["position"]
                        iom_rgn2_size = iom_rgn["rgn2"]["size"]
                        iom_rgn2 = iom_data[iom_rgn2_pos : iom_rgn2_pos + iom_rgn2_size]

                        print(f"\n  IOM RGN2 data ({iom_rgn2_size} bytes):")
                        for row in range(0, min(200, len(iom_rgn2)), 16):
                            hex_bytes = " ".join(
                                f"{b:02x}" for b in iom_rgn2[row : row + 16]
                            )
                            print(f"    {row:04x}: {hex_bytes}")

                        # Parse IOM polyline records
                        print("\n  IOM polyline parsing:")
                        iom_pos = 0
                        while iom_pos < len(iom_rgn2):
                            marker = iom_rgn2[iom_pos]

                            if marker == 0x0D:
                                length = iom_rgn2[iom_pos + 1]
                                print(f"\n    0D at {iom_pos}: length={length}")
                                print(
                                    f"    hex: {iom_rgn2[iom_pos : iom_pos + 2 + length].hex()}"
                                )
                                iom_pos += 2 + length

                            elif marker == 0x06:
                                sub = iom_rgn2[iom_pos + 1]
                                # Find the E0 marker
                                for preamble_size in range(4, 50):
                                    test_pos = iom_pos + 2 + preamble_size
                                    if (
                                        test_pos < len(iom_rgn2)
                                        and iom_rgn2[test_pos] == 0xE0
                                    ):
                                        preamble = iom_rgn2[
                                            iom_pos + 2 : iom_pos + 2 + preamble_size
                                        ]
                                        print(
                                            f"\n    06 at {iom_pos}: sub=0x{sub:02X}, preamble_size={preamble_size}"
                                        )
                                        print(f"    preamble: {preamble.hex()}")

                                        # Parse E0
                                        e0_pos = iom_pos + 2 + preamble_size
                                        e0_bits = iom_rgn2[e0_pos + 1]
                                        idx_size = 1 if e0_bits == 0x2B else 2
                                        img_idx = (
                                            iom_rgn2[e0_pos + 2]
                                            if idx_size == 1
                                            else struct.unpack_from(
                                                "<H", iom_rgn2, e0_pos + 2
                                            )[0]
                                        )
                                        coord_off = e0_pos + 2 + idx_size
                                        lat_min = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off
                                        )[0]
                                        lon_min = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off + 4
                                        )[0]
                                        lat_max = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off + 8
                                        )[0]
                                        lon_max = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off + 12
                                        )[0]
                                        blk_sz = struct.unpack_from(
                                            "<I", iom_rgn2, coord_off + 16
                                        )[0]

                                        print(
                                            f"    E0: bits=0x{e0_bits:02X} idx={img_idx} blk_sz={blk_sz}"
                                        )
                                        print(
                                            f"    E0: lat=[{garmin_32_to_deg(lat_min):.6f},{garmin_32_to_deg(lat_max):.6f}]"
                                        )
                                        print(
                                            f"    E0: lon=[{garmin_32_to_deg(lon_min):.6f},{garmin_32_to_deg(lon_max):.6f}]"
                                        )

                                        # Check preamble fields
                                        if preamble_size >= 8:
                                            pb01 = struct.unpack_from(
                                                "<h", preamble, 0
                                            )[0]
                                            pb23 = struct.unpack_from(
                                                "<h", preamble, 2
                                            )[0]
                                            pb45 = struct.unpack_from(
                                                "<h", preamble, 4
                                            )[0]
                                            pb67 = struct.unpack_from(
                                                "<h", preamble, 6
                                            )[0]

                                            # Compute center from E0 coords
                                            iom_lon_min_24 = lon_min >> 8
                                            iom_lat_min_24 = lat_min >> 8
                                            iom_center_lon = iom_lon_min_24 - pb01 * 4
                                            iom_center_lat = iom_lat_min_24 - pb23 * 4

                                            print(
                                                f"    Preamble int16: b01={pb01} b23={pb23} b45={pb45} b67={pb67}"
                                            )
                                            print(
                                                f"    Computed center: lon_24={iom_center_lon}, lat_24={iom_center_lat}"
                                            )

                                            # Check with IOM group center
                                            if iom_groups:
                                                for gi in range(
                                                    min(10, len(iom_groups))
                                                ):
                                                    g = iom_groups[gi]
                                                    if (
                                                        abs(
                                                            g["lon_center"]
                                                            - iom_center_lon
                                                        )
                                                        < 100
                                                        and abs(
                                                            g["lat_center"]
                                                            - iom_center_lat
                                                        )
                                                        < 100
                                                    ):
                                                        print(
                                                            f"    Near group {gi}: ({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f})"
                                                        )

                                        break
                                iom_pos += 1

                            elif marker == 0xBC:
                                print(f"\n    BC at {iom_pos}")
                                iom_pos += 3

                            elif marker == 0xE0:
                                print(f"\n    E0 at {iom_pos}")
                                e0_bits = iom_rgn2[iom_pos + 1]
                                idx_size = 1 if e0_bits == 0x2B else 2
                                img_idx = (
                                    iom_rgn2[iom_pos + 2]
                                    if idx_size == 1
                                    else struct.unpack_from(
                                        "<H", iom_rgn2, iom_pos + 2
                                    )[0]
                                )
                                coord_off = iom_pos + 2 + idx_size
                                lat_min = struct.unpack_from("<i", iom_rgn2, coord_off)[
                                    0
                                ]
                                lon_min = struct.unpack_from(
                                    "<i", iom_rgn2, coord_off + 4
                                )[0]
                                lat_max = struct.unpack_from(
                                    "<i", iom_rgn2, coord_off + 8
                                )[0]
                                lon_max = struct.unpack_from(
                                    "<i", iom_rgn2, coord_off + 12
                                )[0]
                                print(
                                    f"    Standalone: idx={img_idx} lat=[{garmin_32_to_deg(lat_min):.6f},{garmin_32_to_deg(lat_max):.6f}] "
                                    f"lon=[{garmin_32_to_deg(lon_min):.6f},{garmin_32_to_deg(lon_max):.6f}]"
                                )
                                iom_pos += 2 + idx_size + 20

                            else:
                                iom_pos += 1

                            if iom_pos > 500:
                                break


if __name__ == "__main__":
    main()
