# Tools & Resources

A curated list of tools, documentation, and libraries for working with Garmin IMG files.

## Tools

### Map Creation

| Tool | Type | Description |
|------|------|-------------|
| [mkgmap](http://www.mkgmap.org.uk/) | CLI (Java) | Converts OpenStreetMap data to Garmin vector IMG. The definitive open-source vector IMG writer. |
| [cGPSmapper](http://cgpsmapper.com/) | CLI | Compiles Polish (.mp) format files to Garmin vector IMG. Freeware for personal use. |
| [GPSMapEdit](http://www.gpsmaped.com/) | GUI | Commercial map editor. Exports to cGPSmapper format (.mp). |
| [splitter](https://svn.mkgmap.org.uk/splitter/) | CLI (Java) | Splits large OSM datasets into tiles for mkgmap. |

### Map Inspection

| Tool | Type | Description |
|------|------|-------------|
| [GMapTool](http://www.gmaptool.eu/) | GUI/CLI | IMG file inspection, splitting, and merging. The primary tool for analyzing IMG structure. |
| [GPXSee](https://github.com/tumic0/GPXSee) | Desktop (C++/Qt) | GPS data viewer with full Garmin IMG parser. Useful reference for understanding how devices parse raster data. |
| cartoload analyze | CLI | Built-in IMG inspection and comparison. See [Analyze IMG files](../guides/analyze-img.md). |

### Tile Download

| Tool | Type | Description |
|------|------|-------------|
| [Mobile Atlas Creator (MOBAC)](https://sourceforge.net/projects/mobac/) | GUI (Java) | Downloads map tiles from online sources. Exports to Garmin Custom Maps (KMZ), not IMG directly. |

## Format Documentation

There is no official public specification for the Garmin IMG format. All documentation is reverse-engineered.

### Comprehensive Specifications

| Document | Author | Coverage |
|----------|--------|----------|
| Garmin IMG Format (PDF) | Herbert Oppmann | Authoritative reverse-engineered spec for container and subfile formats. The most up-to-date reference. |
| [IMG Format Specification 1.0](https://forum.gpsfiledepot.com/index.php?action=dlattach;topic=2033.0;attach=5014) | John Mechalas (2005) | The most comprehensive vector IMG specification. Complete header fields, FAT structure, subfile formats. |
| [Exploring Garmin's IMG Format](https://www.pinns.co.uk/osm/docs/expl_img2015.pdf) | N. Willink (2015) | Practical guide to parsing vector IMG internals. Corrects several errors in the Mechalas spec. |

### Community Resources

- [QMapShack Wiki — Raster IMG Format](https://github.com/Maproom/qmapshack/wiki/RasterImg_AWhiter) — The most comprehensive community documentation for raster-specific IMG format. Complete TRE header layout for raster maps, RGN Type E0 records, LBL28/LBL29 structure.
- [OSM Wiki — OSM Map On Garmin](https://wiki.openstreetmap.org/wiki/OSM_Map_On_Garmin) — Garmin map creation workflows and mkgmap tutorials.

## Reference Implementations

| Project | Language | Description |
|---------|----------|-------------|
| [mkgmap](https://svn.mkgmap.org.uk/mkgmap/) | Java | Reference implementation for IMG writing. Key packages: `imgfmt`, `building`. |
| [GPXSee](https://github.com/tumic0/GPXSee) | C++/Qt | Reference IMG parser. Key files: `src/map/IMG/rgnfile.cpp`, `trefile.cpp`, `lblfile.cpp`. |

## Device Compatibility

| Device type | Raster IMG | Vector IMG | JNX (BirdsEye) | KMZ (Custom Maps) |
|---|---|---|---|---|
| Fenix watches (6+) | Yes | Yes | No | No |
| Handheld GPS (GPSMap, Montana, Oregon) | Yes | Yes | Yes | Yes (100 tile limit) |
| Automotive (Drive, DriveSmart) | Limited | Yes | No | No |

## Alternative Raster Formats

### JNX (BirdsEye)

Simpler raster format with JPEG tiles and metadata. Better documented than raster IMG. Supported on handheld GPS devices but **not** on Garmin watches.

### KMZ (Garmin Custom Maps)

ZIP archive with JPEG tiles + KML metadata. Simple to create. Limited to 100 tiles per file. Not suitable for large-scale maps.

## Key Differences: Raster vs Vector IMG

| | Raster | Vector |
|---|---|---|
| Content | Pre-rendered JPEG tile imagery | Points, polylines, polygons |
| Rendering | Device displays JPEG images | Device renders from geometry data |
| Search/routing | Limited or none | Full address search, turn-by-turn routing |
| Tool support | Very limited (no open-source writer existed before cartoload) | Extensive (mkgmap, cGPSmapper) |
| File size | Large (imagery) | Compact |

Garmin's professional maps can combine both raster and vector data in a single IMG file — raster background imagery with vector overlays for roads, POIs, and labels.
