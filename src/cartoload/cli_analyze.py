"""CLI commands for analyzing Garmin IMG binary files.

Provides `cartoload analyze img info` for inspection and
`cartoload analyze img compare` for side-by-side comparison.
"""

from __future__ import annotations

import struct

import click
from rich.console import Console
from rich.rule import Rule
from rich.status import Status

from .analysis.compare import compare_files
from .analysis.img_parser import IMGParser, format_hex_dump
from .analysis.rgn2 import analyze_rgn2, analyze_rgn2_segments

LARGE_FILE_THRESHOLD = 200 * 1024 * 1024  # 200 MB

ENCODING_NAMES = {
    0: "ASCII",
    1: "Latin-1 (ISO 8859-1)",
    2: "CP 1252, Western European",
    3: "UTF-8",
    4: "CP 1250, Central European",
    5: "CP 1251, Cyrillic",
    6: "CP 1253, Greek",
    7: "CP 1254, Turkish",
    8: "CP 1255, Hebrew",
    9: "CP 1256, Arabic",
    10: "CP 1257, Baltic",
    11: "CP 1258, Vietnamese",
}

# Descriptions for IMG sections and sub-sections
SECTION_DESCRIPTIONS: dict[str, str] = {
    "TRE": "Map structure: bounds, zoom levels, subdivisions, and spatial indexing",
    "TRE1": "Zoom level definitions (level number, zoom code, subdivision count)",
    "TRE2": "Subdivision/tiling records that partition the map into spatial groups",
    "TRE3": "Copyright strings section",
    "TRE4": "Extended POI type definitions",
    "TRE5": "Extended polyline type definitions",
    "TRE6": "Extended polygon type definitions",
    "TRE7": "Raster layer offset table — maps zoom subdivisions to RGN2 tile data",
    "TRE8": "Object type parameter definitions",
    "TRE9": "Product info section",
    "TRE10": "Additional product info",
    "RGN": "Region data: the actual map content (tiles, polylines, polygons, POIs)",
    "RGN1": "Standard map objects (polylines, polygons, POIs)",
    "RGN2": "Extended type data — raster tile records (E0) with bitmap placement per zoom level",
    "RGN3": "Extended POI data",
    "RGN4": "Extended polyline data",
    "RGN5": "Extended polygon data",
    "LBL": "Label data: text strings, encodings, and bitmap image references",
    "LBL1": "Label text strings (map object names, city names, etc.)",
    "LBL28": "Bitmap image offset table",
    "LBL29": "Bitmap image storage data",
    "NET": "Road network routing data",
}

# Sections we have dedicated parsers for
KNOWN_SECTIONS = {"TRE", "RGN", "LBL"}

# Sub-section keys that each top-level section can contain
SUBSECTION_KEYS: dict[str, list[str]] = {
    "TRE": [
        "TRE1",
        "TRE2",
        "TRE3",
        "TRE4",
        "TRE5",
        "TRE6",
        "TRE7",
        "TRE8",
        "TRE9",
        "TRE10",
    ],
    "RGN": ["RGN1", "RGN2", "RGN3", "RGN4", "RGN5"],
    "LBL": ["LBL1", "LBL28", "LBL29"],
}


def _human_size(size: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size //= 1024
    return f"{size:.1f} TB"


def _styled_path(*parts: str) -> str:
    """Build a styled path title: ancestors dim, last segment bold cyan.

    _part1_ > _part2_ > **last**
    """
    if not parts:
        return ""
    styled = []
    for part in parts[:-1]:
        styled.append(f"[dim]{part}[/]")
    styled.append(f"[bold cyan]{parts[-1]}[/]")
    sep = " [dim]>[/] "
    return "[bold cyan]──[/] " + sep.join(styled)


def _print_bitmap_stats(rgn_parsed: dict, console: Console) -> None:
    """Print bitmap tile statistics from RGN2 E0 records."""
    recs = rgn_parsed.get("rgn2_records", [])
    e0_recs = [r for r in recs if r["type"] == "E0 (raster tile)"]
    if not e0_recs:
        return
    img_indices = set(r["image_index"] for r in e0_recs)
    console.print(
        f"  Bitmaps: [cyan]{len(e0_recs):,}[/] tiles, [cyan]{len(img_indices):,}[/] images"
    )


def _section_header(
    console: Console,
    *path_parts: str,
    description: str | None = None,
    descriptions: bool = True,
) -> None:
    """Print a left-aligned section header with styled path."""
    console.print(Rule(_styled_path(*path_parts), style="bold cyan", align="left"))
    if descriptions and description:
        console.print(f"[dim italic]{description}[/]")


def _subsection_header(
    console: Console,
    title: str,
    info: str,
    description: str | None = None,
    *,
    descriptions: bool = True,
) -> None:
    """Print a sub-section header with optional description."""
    console.print(f"  [bold]{title}[/]: {info}")
    if descriptions and description:
        console.print(f"    [dim italic]{description}[/]")


def _truncated(console: Console, remaining: int, section_hint: str) -> None:
    """Print a truncation hint with the command to see all entries."""
    console.print(
        f"    [dim]... {remaining:,} more, "
        f"use [bold]--section {section_hint} --limit 0[/] to see all[/]"
    )


def _print_subsection_list(
    console: Console, parent: str, data: dict, key_map: list[str]
) -> None:
    """Print available sub-sections for a parent section."""
    found = [k for k in key_map if k.lower() in data]
    if found:
        console.print(f"  Sections: {', '.join(found)}")


def _print_generic_section(console: Console, name: str, gmp: dict) -> None:
    """Print a generic GMP section we don't have a dedicated parser for."""
    data = gmp["data"]
    offset = gmp["sections"].get(name, 0)
    if offset == 0:
        return

    section_data = data[offset:]
    if len(section_data) < 21:
        console.print(f"  {name}: offset={offset}, data too small to parse header")
        return

    hdr_len = struct.unpack_from("<H", section_data, 0)[0]
    sig = section_data[2:12].decode("ascii", errors="replace")
    version = section_data[12]

    desc = SECTION_DESCRIPTIONS.get(name, "Unknown section")
    _subsection_header(
        console,
        name,
        f"pos={offset}, hdr={hdr_len} bytes, sig={sig!r}, version={version}",
        desc,
    )


def _print_tre(
    console: Console, tre: dict, limit: int, *, descriptions: bool = True
) -> None:
    """Print TRE section details."""
    _section_header(
        console,
        "IMG",
        "GMP",
        "TRE",
        description=SECTION_DESCRIPTIONS.get("TRE"),
        descriptions=descriptions,
    )
    console.print(
        f"  Header: {tre['sub_header']['header_length']} bytes, "
        f"version={tre['sub_header']['version']}"
    )
    console.print(
        f"  Bounds: N={tre['north_deg']:.6f}, S={tre['south_deg']:.6f}, "
        f"W={tre['west_deg']:.6f}, E={tre['east_deg']:.6f}"
    )
    _print_subsection_list(console, "TRE", tre, SUBSECTION_KEYS["TRE"])

    if "levels" in tre:
        _subsection_header(
            console,
            "TRE1 Levels",
            f"count=[cyan]{len(tre['levels'])}[/]",
            SECTION_DESCRIPTIONS.get("TRE1"),
            descriptions=descriptions,
        )
        for i, lvl in enumerate(tre["levels"]):
            console.print(
                f"      [{i}] level={lvl['level_number']:3d}  zoom={lvl['zoom_code']:3d}  "
                f"subdivs=[cyan]{lvl['subdivision_count']:5d}[/]"
            )

    if "display_priority" in tre:
        console.print(f"  Display priority: {tre['display_priority']}")

    if "map_id" in tre:
        console.print(f"  Map ID: [cyan]0x{tre['map_id']:08X}[/]")

    if "matching_number" in tre:
        console.print(f"  Matching number: 0x{tre['matching_number']:08X}")

    if "map_name" in tre:
        console.print(f"  Map name: {tre['map_name']}")

    if "tre2" in tre:
        t2 = tre["tre2"]
        total = len(tre["groups_16byte"]) if "groups_16byte" in tre else 0
        show_count = total if limit == 0 else min(total, limit)
        _subsection_header(
            console,
            "TRE2 Subdivisions",
            f"pos={t2['position']}, size={t2['size']}, records=[cyan]{total}[/]",
            SECTION_DESCRIPTIONS.get("TRE2"),
            descriptions=descriptions,
        )
        if "groups_16byte" in tre:
            for i, g in enumerate(tre["groups_16byte"][:show_count]):
                console.print(
                    f"      [{i}] rgn_off={g['rgn_offset']:8d} obj={g['obj_types']} "
                    f"lon={g['lon_center_deg']:.6f} lat={g['lat_center_deg']:.6f} "
                    f"flags=[cyan]0x{g['flags']:04X}[/] subdivs={g['subdiv_count']} "
                    f"next={g['next_level_index']}"
                )
            if limit > 0 and total > show_count:
                _truncated(console, total - show_count, "TRE2")

    if "tre7" in tre:
        t7 = tre["tre7"]
        total = len(tre["tre7_offsets"]) if "tre7_offsets" in tre else 0
        show_count = total if limit == 0 else min(total, limit)
        _subsection_header(
            console,
            "TRE7 Raster layer",
            f"pos={t7['position']}, size={t7['size']}, "
            f"rec_size={t7['record_size']}, entries=[cyan]{total}[/]",
            SECTION_DESCRIPTIONS.get("TRE7"),
            descriptions=descriptions,
        )
        if "tre7_offsets" in tre:
            for i, entry in enumerate(tre["tre7_offsets"][:show_count]):
                console.print(f"      [{i}] {entry}")
            if limit > 0 and total > show_count:
                _truncated(console, total - show_count, "TRE7")

    if "tre8" in tre:
        t8 = tre["tre8"]
        _subsection_header(
            console,
            "TRE8 Object types",
            f"pos={t8['position']}, size={t8['size']}, rec_size={t8['record_size']}",
            SECTION_DESCRIPTIONS.get("TRE8"),
            descriptions=descriptions,
        )
        if "tre8_entries" in tre:
            for i, entry in enumerate(tre["tre8_entries"]):
                console.print(
                    f"      [{i}] type={entry['type']} param1={entry['param1']} "
                    f"param2={entry['param2']} raw={entry['raw']}"
                )

    for sec_name in ["tre4", "tre5", "tre6", "tre9", "tre10"]:
        if sec_name in tre:
            sec = tre[sec_name]
            _subsection_header(
                console,
                sec_name.upper(),
                f"pos={sec['position']}, size={sec['size']}, rec_size={sec['record_size']}",
                SECTION_DESCRIPTIONS.get(sec_name.upper()),
                descriptions=descriptions,
            )


def _print_rgn(
    console: Console, rgn_parsed: dict, limit: int, *, descriptions: bool = True
) -> None:
    """Print RGN section details."""
    _section_header(
        console,
        "IMG",
        "GMP",
        "RGN",
        description=SECTION_DESCRIPTIONS.get("RGN"),
        descriptions=descriptions,
    )
    console.print(f"  Header: {rgn_parsed['sub_header']['header_length']} bytes")
    _print_subsection_list(console, "RGN", rgn_parsed, SUBSECTION_KEYS["RGN"])

    for sec_name in ["rgn1", "rgn2", "rgn3", "rgn4", "rgn5"]:
        if sec_name in rgn_parsed:
            sec = rgn_parsed[sec_name]
            _subsection_header(
                console,
                sec_name.upper(),
                f"pos={sec['position']}, size={sec['size']}",
                SECTION_DESCRIPTIONS.get(sec_name.upper()),
                descriptions=descriptions,
            )

    _print_bitmap_stats(rgn_parsed, console)

    if "rgn2_records" in rgn_parsed:
        recs = rgn_parsed["rgn2_records"]
        total = len(recs)
        show_count = total if limit == 0 else min(total, limit)
        console.print(f"  RGN2 records ([cyan]{total}[/]):")
        for rec in recs[:show_count]:
            if rec["type"] == "E0 (raster tile)":
                console.print(
                    f"      {rec['type']} @{rec['offset']}: "
                    f"bounds=({rec['lat_min_deg']:.6f},{rec['lon_min_deg']:.6f})-"
                    f"({rec['lat_max_deg']:.6f},{rec['lon_max_deg']:.6f}) "
                    f"blk_sz={rec['block_size']} img_idx=[cyan]{rec['image_index']}[/]"
                )
            else:
                console.print(
                    f"      {rec['type']} @{rec['offset']}: {rec.get('raw_hex', '')}"
                )
        if limit > 0 and total > show_count:
            _truncated(console, total - show_count, "RGN2")

    if "rgn5_hex" in rgn_parsed:
        console.print(f"  RGN5 data hex: {rgn_parsed['rgn5_hex'][:200]}")


def _print_lbl(
    console: Console, lbl: dict | None, limit: int, *, descriptions: bool = True
) -> None:
    """Print LBL section details."""
    _section_header(
        console,
        "IMG",
        "GMP",
        "LBL",
        description=SECTION_DESCRIPTIONS.get("LBL"),
        descriptions=descriptions,
    )
    if not lbl:
        console.print("  (No LBL section)")
        return
    console.print(f"  Header: {lbl['sub_header']['header_length']} bytes")
    if "encoding" in lbl:
        enc_name = ENCODING_NAMES.get(lbl["encoding"], f"unknown ({lbl['encoding']})")
        console.print(f"  Encoding: {enc_name}")
    _print_subsection_list(console, "LBL", lbl, SUBSECTION_KEYS["LBL"])

    if "lbl1" in lbl:
        _subsection_header(
            console,
            "LBL1",
            f"pos={lbl['lbl1']['position']}, size={lbl['lbl1']['size']}, "
            f"offset_mult={lbl['lbl1']['offset_multiplier']}",
            SECTION_DESCRIPTIONS.get("LBL1"),
            descriptions=descriptions,
        )
    if "lbl28" in lbl:
        _subsection_header(
            console,
            "LBL28",
            f"pos={lbl['lbl28']['position']}, size={lbl['lbl28']['size']}",
            SECTION_DESCRIPTIONS.get("LBL28"),
            descriptions=descriptions,
        )
    if "lbl29" in lbl:
        _subsection_header(
            console,
            "LBL29",
            f"pos={lbl['lbl29']['position']}, size={lbl['lbl29']['size']}",
            SECTION_DESCRIPTIONS.get("LBL29"),
            descriptions=descriptions,
        )
    if "labels" in lbl:
        show_count = (
            len(lbl["labels"]) if limit == 0 else min(len(lbl["labels"]), limit)
        )
        console.print(f"  Labels (first {show_count}): {lbl['labels'][:show_count]}")
        console.print(f"  Total labels: {lbl['total_labels']}")


def _print_generic_gmp_section(
    console: Console, name: str, gmp: dict, *, descriptions: bool = True
) -> None:
    """Print a GMP section we don't have a dedicated parser for."""
    desc = SECTION_DESCRIPTIONS.get(name, "Unknown section")
    _section_header(
        console,
        "IMG",
        "GMP",
        name,
        description=desc,
        descriptions=descriptions,
    )
    _print_generic_section(console, name, gmp)


def _print_subsection(
    console: Console,
    section_name: str,
    tre: dict,
    rgn_parsed: dict,
    lbl: dict | None,
    limit: int,
    *,
    descriptions: bool = True,
) -> bool:
    """Print a specific sub-section. Returns True if the section was found."""
    name = section_name.upper()
    desc = SECTION_DESCRIPTIONS.get(name, "")

    # TRE sub-sections
    if name == "TRE1" and "levels" in tre:
        console.print(
            Rule(
                _styled_path("IMG", "GMP", "TRE", "TRE1"),
                style="bold cyan",
                align="left",
            )
        )
        if descriptions and desc:
            console.print(f"[dim italic]{desc}[/]")
        console.print(f"  Count: [cyan]{len(tre['levels'])}[/]")
        for i, lvl in enumerate(tre["levels"]):
            console.print(
                f"    [{i}] level={lvl['level_number']:3d}  zoom={lvl['zoom_code']:3d}  "
                f"subdivs=[cyan]{lvl['subdivision_count']:5d}[/]"
            )
        return True

    if name == "TRE2" and "tre2" in tre:
        t2 = tre["tre2"]
        total = len(tre["groups_16byte"]) if "groups_16byte" in tre else 0
        show_count = total if limit == 0 else min(total, limit)
        console.print(Rule(_styled_path("IMG", "GMP", "TRE", "TRE2"), align="left"))
        if descriptions and desc:
            console.print(f"[dim italic]{desc}[/]")
        console.print(f"  pos={t2['position']}, size={t2['size']}")
        if "groups_16byte" in tre:
            console.print(f"  16-byte group records ([cyan]{total}[/]):")
            for i, g in enumerate(tre["groups_16byte"][:show_count]):
                console.print(
                    f"    [{i}] rgn_off={g['rgn_offset']:8d} obj={g['obj_types']} "
                    f"lon={g['lon_center_deg']:.6f} lat={g['lat_center_deg']:.6f} "
                    f"flags=[cyan]0x{g['flags']:04X}[/] subdivs={g['subdiv_count']} "
                    f"next={g['next_level_index']}"
                )
            if limit > 0 and total > show_count:
                _truncated(console, total - show_count, "TRE2")
        return True

    if name == "TRE7" and "tre7" in tre:
        t7 = tre["tre7"]
        total = len(tre["tre7_offsets"]) if "tre7_offsets" in tre else 0
        show_count = total if limit == 0 else min(total, limit)
        console.print(Rule(_styled_path("IMG", "GMP", "TRE", "TRE7"), align="left"))
        if descriptions and desc:
            console.print(f"[dim italic]{desc}[/]")
        console.print(
            f"  pos={t7['position']}, size={t7['size']}, rec_size={t7['record_size']}"
        )
        if "tre7_offsets" in tre:
            console.print(f"  Offset table ([cyan]{total}[/] entries):")
            for i, entry in enumerate(tre["tre7_offsets"][:show_count]):
                console.print(f"    [{i}] {entry}")
            if limit > 0 and total > show_count:
                _truncated(console, total - show_count, "TRE7")
        return True

    if name == "TRE8" and "tre8" in tre:
        t8 = tre["tre8"]
        console.print(Rule(_styled_path("IMG", "GMP", "TRE", "TRE8"), align="left"))
        if descriptions and desc:
            console.print(f"[dim italic]{desc}[/]")
        console.print(
            f"  pos={t8['position']}, size={t8['size']}, rec_size={t8['record_size']}"
        )
        if "tre8_entries" in tre:
            for i, entry in enumerate(tre["tre8_entries"]):
                console.print(
                    f"    [{i}] type={entry['type']} param1={entry['param1']} "
                    f"param2={entry['param2']} raw={entry['raw']}"
                )
        return True

    for sec_name in ["TRE3", "TRE4", "TRE5", "TRE6", "TRE9", "TRE10"]:
        key = sec_name.lower()
        if name == sec_name and key in tre:
            sec = tre[key]
            console.print(
                Rule(_styled_path("IMG", "GMP", "TRE", sec_name), align="left")
            )
            if descriptions and desc:
                console.print(f"[dim italic]{desc}[/]")
            console.print(
                f"  pos={sec['position']}, size={sec['size']}, rec_size={sec['record_size']}"
            )
            return True

    # RGN sub-sections
    if name == "RGN2":
        sec = rgn_parsed.get("rgn2")
        if sec:
            console.print(Rule(_styled_path("IMG", "GMP", "RGN", "RGN2"), align="left"))
            if descriptions and desc:
                console.print(f"[dim italic]{desc}[/]")
            console.print(f"  pos={sec['position']}, size={sec['size']}")
            if "rgn2_records" in rgn_parsed:
                recs = rgn_parsed["rgn2_records"]
                total = len(recs)
                show_count = total if limit == 0 else min(total, limit)
                console.print(f"  Records ([cyan]{total}[/]):")
                for rec in recs[:show_count]:
                    if rec["type"] == "E0 (raster tile)":
                        console.print(
                            f"    {rec['type']} @{rec['offset']}: "
                            f"bounds=({rec['lat_min_deg']:.6f},{rec['lon_min_deg']:.6f})-"
                            f"({rec['lat_max_deg']:.6f},{rec['lon_max_deg']:.6f}) "
                            f"blk_sz={rec['block_size']} img_idx=[cyan]{rec['image_index']}[/]"
                        )
                    else:
                        console.print(
                            f"    {rec['type']} @{rec['offset']}: {rec.get('raw_hex', '')}"
                        )
                if limit > 0 and total > show_count:
                    _truncated(console, total - show_count, "RGN2")
            return True

    for sec_name in ["RGN1", "RGN3", "RGN4", "RGN5"]:
        key = sec_name.lower()
        if name == sec_name and key in rgn_parsed:
            sec = rgn_parsed[key]
            console.print(
                Rule(_styled_path("IMG", "GMP", "RGN", sec_name), align="left")
            )
            if descriptions and desc:
                console.print(f"[dim italic]{desc}[/]")
            console.print(f"  pos={sec['position']}, size={sec['size']}")
            return True

    # LBL sub-sections
    if lbl:
        for sec_name in ["LBL1", "LBL28", "LBL29"]:
            key = sec_name.lower()
            if name == sec_name and key in lbl:
                sec = lbl[key]
                console.print(
                    Rule(_styled_path("IMG", "GMP", "LBL", sec_name), align="left")
                )
                if descriptions and desc:
                    console.print(f"[dim italic]{desc}[/]")
                console.print(f"  pos={sec['position']}, size={sec['size']}")
                if key == "lbl1":
                    console.print(f"  offset_mult={sec['offset_multiplier']}")
                return True

    return False


@click.group()
def analyze() -> None:
    """Analyze geodata files."""


@analyze.group()
def img() -> None:
    """Analyze Garmin IMG binary files."""


@img.command()
@click.argument("img_file", type=click.Path(exists=True))
@click.option("-s", "--subfile", default=None, help="Subfile name (e.g. '00355951')")
@click.option(
    "-n",
    "--section",
    default=None,
    help="Show only one section (TRE, TRE7, RGN, RGN2, LBL, NET, etc.)",
)
@click.option(
    "--limit",
    type=int,
    default=20,
    help="Max entries per section (default: 20, 0 = unlimited)",
)
@click.option("-x", "--hex", "hex_section", default=None, help="Dump hex of section")
@click.option(
    "-d",
    "--dump",
    "dump_section",
    default=None,
    help="Full hex dump of section with ASCII",
)
@click.option("-l", "--list", "list_subfiles", is_flag=True, help="List subfiles only")
@click.option("-a", "--all", "dump_all", is_flag=True, help="Dump all sections")
@click.option("--raw-offset", type=int, default=None, help="Read raw bytes at offset")
@click.option(
    "--raw-size", type=int, default=64, help="Size for raw read (default: 64)"
)
@click.option(
    "-r",
    "--rgn2",
    is_flag=True,
    help="Show annotated RGN2 analysis. RGN2 contains raster tile records (E0) "
    "and polyline/polygon preambles that describe bitmap placement per zoom level.",
)
@click.option(
    "-g",
    "--segments",
    is_flag=True,
    help="Segment RGN2 by zoom level using TRE7 offsets. Shows how raster tiles "
    "are grouped into zoom levels within the RGN2 data section.",
)
@click.option(
    "-m",
    "--summary",
    "show_summary",
    is_flag=True,
    help="Show concise summary (bounds, bitmaps, encoding, map name)",
)
@click.option(
    "-q",
    "--no-descriptions",
    is_flag=True,
    help="Hide section descriptions",
)
@click.option("--no-color", is_flag=True, help="Disable colored output")
def info(
    img_file: str,
    subfile: str | None,
    section: str | None,
    limit: int,
    hex_section: str | None,
    dump_section: str | None,
    list_subfiles: bool,
    dump_all: bool,
    raw_offset: int | None,
    raw_size: int,
    rgn2: bool,
    segments: bool,
    show_summary: bool,
    no_descriptions: bool,
    no_color: bool,
) -> None:
    """Analyze a Garmin IMG file."""
    # Rich Console auto-disables colors when piped; --no-color forces it off
    console = Console(force_terminal=False if no_color else None, no_color=no_color)
    show_desc = not no_descriptions

    with IMGParser(img_file) as parser:
        parser.parse_header()
        parser.parse_fat()

        # --list: just list subfiles
        if list_subfiles:
            console.print(Rule(_styled_path("IMG File"), align="left"))
            console.print(f"  File: {img_file} ({parser.filesize:,} bytes)")
            console.print(
                f"  Header: {parser.header['date']}, {parser.header['magic']}, block_size={parser.header['block_size']}"
            )
            console.print(f"  Mapset: {parser.header['description']}")
            console.print(f"  Found [cyan]{len(parser.subfiles)}[/] subfiles:")
            for key, sf in parser.subfiles.items():
                total_blocks = sum(len(p["blocks"]) for p in sf["parts"])
                console.print(
                    f"    {sf['name']:12s} [dim]{sf['type']:3s}[/]  size={sf['size']:>10,}  "
                    f"parts={len(sf['parts'])}  blocks={total_blocks}"
                )
            return

        # Select subfile
        gmp_key = None
        if subfile:
            for key in parser.subfiles:
                if subfile.upper() in key.upper():
                    gmp_key = key
                    break
            if not gmp_key:
                console.print(f"[red]Subfile '{subfile}' not found.[/] Available:")
                for key in parser.subfiles:
                    console.print(f"  {key}")
                return
        else:
            for key in parser.subfiles:
                if parser.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break

        if not gmp_key:
            console.print("[red]No GMP subfile found![/]")
            return

        # Show spinner for large files, clear before output
        use_spinner = parser.filesize > LARGE_FILE_THRESHOLD
        if use_spinner:
            with Status("Parsing IMG file...", console=console):
                gmp = parser.parse_gmp_container(gmp_key)
                tre = parser.parse_tre(gmp)
                rgn_parsed = parser.parse_rgn(gmp)
                lbl = parser.parse_lbl(gmp)
        else:
            gmp = parser.parse_gmp_container(gmp_key)
            tre = parser.parse_tre(gmp)
            rgn_parsed = parser.parse_rgn(gmp)
            lbl = parser.parse_lbl(gmp)

        # --summary: concise overview
        if show_summary:
            console.print(Rule(_styled_path("IMG", "Summary"), align="left"))
            console.print(f"  File: {img_file} ({_human_size(parser.filesize)})")
            console.print(f"  Mapset: {parser.header['description']}")
            console.print(f"  Subfile: {gmp_key}")
            console.print(f"  Date: {gmp['date']}")
            console.print(
                f"  Bounds: N={tre['north_deg']:.6f}, S={tre['south_deg']:.6f}, "
                f"W={tre['west_deg']:.6f}, E={tre['east_deg']:.6f}"
            )
            console.print("  Projection: WGS 84 (geographic, lat/lon)")
            if "display_priority" in tre:
                console.print(f"  Priority: {tre['display_priority']}")
            if "levels" in tre:
                levels = tre["levels"]
                console.print(
                    f"  Levels: {[lvl['level_number'] for lvl in levels]}, "
                    f"zoom: {[lvl['zoom_code'] for lvl in levels]}"
                )
            if "map_name" in tre:
                console.print(f"  Map name: {tre['map_name']}")
            if "map_id" in tre:
                console.print(f"  Map ID: [cyan]0x{tre['map_id']:08X}[/]")
            _print_bitmap_stats(rgn_parsed, console)
            if lbl and "encoding" in lbl:
                enc_name = ENCODING_NAMES.get(
                    lbl["encoding"], f"unknown ({lbl['encoding']})"
                )
                console.print(f"  Encoding: {enc_name}")
            return

        # --hex / --dump: raw section output
        if hex_section:
            hex_str = parser.dump_section_hex(gmp, hex_section)
            console.print(
                Rule(_styled_path("IMG", "GMP", f"Hex: {hex_section}"), align="left")
            )
            console.print(hex_str)
            return

        if dump_section:
            hex_str = parser.dump_section_hex(gmp, dump_section)
            if hex_str and not hex_str.startswith("("):
                console.print(
                    Rule(
                        _styled_path("IMG", "GMP", f"Hex dump: {dump_section}"),
                        align="left",
                    )
                )
                console.print(format_hex_dump(bytes.fromhex(hex_str)))
            else:
                console.print(hex_str)
            return

        # --rgn2: annotated RGN2 analysis
        if rgn2:
            analyze_rgn2(parser, gmp_key, console.print)
            return

        # --segments: TRE7-based segmentation
        if segments:
            analyze_rgn2_segments(parser, gmp_key, console.print)
            return

        # --section: show only one section
        if section:
            name = section.upper()
            # Sub-sections first
            if _print_subsection(
                console,
                section,
                tre,
                rgn_parsed,
                lbl,
                limit,
                descriptions=show_desc,
            ):
                return
            # Top-level sections
            if name == "TRE":
                _print_tre(console, tre, limit, descriptions=show_desc)
            elif name == "RGN":
                _print_rgn(console, rgn_parsed, limit, descriptions=show_desc)
            elif name == "LBL":
                _print_lbl(console, lbl, limit, descriptions=show_desc)
            elif name in gmp["sections"]:
                _print_generic_gmp_section(console, name, gmp, descriptions=show_desc)
            else:
                console.print(f"[red]Unknown section: {section}[/]")
                known = sorted(KNOWN_SECTIONS | set(gmp["sections"].keys()))
                console.print(f"Available: {', '.join(known)}")
            return

        # Default: full analysis
        console.print(Rule(_styled_path(f"IMG: {img_file}"), align="left"))
        console.print(
            f"  Size: {parser.filesize:,} bytes ({_human_size(parser.filesize)})"
        )
        console.print(
            f"  Header: {parser.header['date']}, {parser.header['magic']}, block_size={parser.header['block_size']}"
        )
        console.print(f"  Mapset: {parser.header['description']}")
        console.print("  Projection: WGS 84 (geographic, lat/lon)")

        console.print(Rule(_styled_path("IMG", "GMP Container"), align="left"))
        console.print(f"  Subfile: {gmp_key}")
        console.print(
            f"  Signature: {gmp['signature']}, version={gmp['version']}, date={gmp['date']}"
        )
        console.print(f"  Data size: {gmp['data_size']:,} bytes")
        console.print(f"  Sections: {', '.join(gmp['sections'].keys())}")

        # Print all known sections
        _print_tre(console, tre, limit, descriptions=show_desc)
        _print_rgn(console, rgn_parsed, limit, descriptions=show_desc)
        _print_lbl(console, lbl, limit, descriptions=show_desc)

        # Print unknown GMP sections (NET, S5, S6, S7, etc.)
        for name in gmp["sections"]:
            if name not in KNOWN_SECTIONS:
                _print_generic_gmp_section(console, name, gmp, descriptions=show_desc)

        if dump_all:
            console.print(Rule(_styled_path("IMG", "GMP", "Hex Dump"), align="left"))
            all_data = gmp["data"]
            dump_limit = len(all_data) if limit == 0 else min(len(all_data), 2048)
            console.print(format_hex_dump(all_data[:dump_limit]))
            if limit > 0 and len(all_data) > dump_limit:
                _truncated(console, len(all_data) - dump_limit, "GMP")

        if raw_offset is not None:
            raw = parser.read_at(raw_offset, raw_size)
            console.print(
                Rule(_styled_path("IMG", f"Raw @ 0x{raw_offset:X}"), align="left")
            )
            console.print(format_hex_dump(raw))


@img.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.option("--no-color", is_flag=True, help="Disable colored output")
def compare(file1: str, file2: str, no_color: bool) -> None:
    """Compare two IMG files side by side (RGN headers and RGN2 data)."""
    console = Console(force_terminal=False if no_color else None, no_color=no_color)
    compare_files(file1, file2, console.print)
