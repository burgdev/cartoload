## Why

To render vector data (skitours, hiking routes) as raster overlays or Garmin vector maps, cartoload needs a unified styling system. Currently there is no way to define how vector features should look — no colors, line widths, dash patterns, or zoom-dependent behavior. The style engine provides this, bridging the gap between raw GPKG data and visual output for both the Pillow rasterizer (Path B) and the mkgmap pipeline (Path C).

## What Changes

- New `StyleEngine` module that parses styling rules from three sources:
  1. **Inline YAML** — simple `match` + `style` rules in the layer config (color, width, dash, border)
  2. **Zoom-dependent YAML** — per-zoom-level style variants with nearest-zoom fallback
  3. **QGIS QML import** — parse categorized and rule-based renderer QML files via `xml.etree.ElementTree`
- Match expression syntax compatible with mkgmap (`tag=value`, `tag~regex`, `tag>number`, `*` wildcard)
- Internal style model that normalizes all three tiers into a single representation
- Zoom level selection logic (nearest defined zoom, or `default` fallback)
- Visual properties: color (RGB), width, dash pattern, border (color + width), opacity

## Capabilities

### New Capabilities
- `vector-style-engine`: Parse, normalize, and evaluate styling rules for vector data layers across three tiers (inline YAML, zoom-dependent YAML, QGIS QML)

### Modified Capabilities

## Impact

- **New module**: `src/cartoload/style/` — style engine, QML parser, match expression evaluator
- **Config**: Layer config gains optional `style` (path to .qml or inline rules) and `rules` fields
- **No new dependencies**: QML parsing uses stdlib `xml.etree.ElementTree`
- **Downstream**: Consumed by the rasterizer (Path B) and mkgmap pipeline (Path C) changes
