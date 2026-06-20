---
hide:
    - navigation
    - toc
---
<div class="landing-hero" markdown>

<div class="landing-brand" markdown>

![cartoload logo](assets/logo-light.svg){ .landing-logo }

# cartoload

</div>

<p class="landing-tagline">Convert raster tiles into Garmin GPS maps</p>

[Get started](getting-started.md){ .md-button .md-button--primary }
[View reference](reference.md){ .md-button }

</div>

`cartoload` is an open-source CLI tool and Python library that converts geodata from raster formats (e.g. WMTS, WMS, GeoTIFF) into maps for GPS devices — primarily Garmin IMG format.

## Features

<div class="grid cards" markdown>

- :material-download:{ .lg .middle } **Multiple tile sources**

    ---

    Download maps from WMTS, XYZ/TMS, and STAC/GeoTIFF sources. Configure any provider — swisstopo, open data portals, or custom endpoints.

- :material-map:{ .lg .middle } **Garmin IMG export**

    ---

    Export raster tiles to Garmin IMG format. Full support for tiled map display on compatible GPS devices.

- :material-cog:{ .lg .middle } **Source-agnostic config**

    ---

    Define sources and layers in simple YAML files. Swap providers without changing your build pipeline.

- :material-magnify:{ .lg .middle } **Built-in analysis tools**

    ---

    Inspect, compare, and debug IMG files. Validate tile coverage and verify output integrity.

- :material-console:{ .lg .middle } **CLI & Python API**

    ---

    Use as a standalone command-line tool or integrate as a Python library into your own workflow.

- :material-shield-check:{ .lg .middle } **Open source**

    ---

    [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.en.html) licensed, fully open source. View the [LICENSE](https://github.com/burgdev/cartoload/blob/main/LICENSE) file, inspect, contribute, or fork on [GitHub](https://github.com/burgdev/cartoload).

</div>
