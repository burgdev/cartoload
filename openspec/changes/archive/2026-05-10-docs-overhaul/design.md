## Context

The documentation lives in `docs/` and is built with zensical (v0.0.33). The current state:

- 10 markdown pages mixed between user docs, binary format specs, and research notes
- `zensical.toml` has no `[project.theme]` section — default colors, no logo, no favicon
- Logo/favicon SVGs exist in `assets/logo/` and `assets/design/` but aren't used by the doc site
- Design system colors defined in `assets/design/color-palette.gpl` (Alpine green palette)
- `external_ignored/` directory is picked up by zensical and built as an orphan page
- Several nav items are placeholders ("Not yet implemented")
- `garmin-img.md` is 684 lines of binary format spec — correct content, wrong level for most users
- `garmin-img-resources.md` is a research document with implementation planning sections

## Goals / Non-Goals

**Goals:**
- Clear, task-oriented documentation structure (Guides, Configuration, Reference)
- Two-level IMG format docs: overview for users, detailed spec linked from overview
- Zensical site with proper branding (logo, favicon, Alpine green palette, dark mode)
- Clean nav without placeholder pages
- Remove swisstopo IMG file references (unclear provenance); keep swisstopo as example source config
- Move `cartoload analyze` docs from format spec into Guides

**Non-Goals:**
- Rewriting the detailed binary format spec content (keep as-is, just restructure)
- Adding new documentation content for features that don't exist yet (vector IMG, Python API)
- Changing the zensical version or build process
- Modifying any application code

## Decisions

### 1. Nav structure

```
Home
Getting started
Guides
  Build a map
  Analyze IMG files
  Split large maps
Configuration
  Sources
  Layers
IMG Format
  Overview
  Detailed specification
  Tools & resources
CLI Reference
API Reference
```

**Rationale:** Separates task-oriented content (Guides) from reference content (Configuration, IMG Format, CLI/API Reference). Users looking for "how do I build a map" go to Guides; users looking for "what fields does a source config accept" go to Configuration.

**What's removed from nav:** Style files (placeholder), Garmin vector IMG (placeholder), Adding exporters (skeleton).

### 2. IMG Format section split into three pages

- **Overview** — Simplified explanation: what IMG files are, raster vs vector, file structure at a high level, device compatibility. ~1 page.
- **Detailed specification** — Current `garmin-img.md` content, cleaned up (remove swisstopo IMG references, keep IOM references). Binary format reference for implementers.
- **Tools & resources** — Cleaned-up `garmin-img-resources.md`. Remove planning sections ("Approaches for writing", "Recommendations for this project", status markers). Keep: tool descriptions, format references, device compatibility, links.

### 3. Zensical branding approach

Copy logo/favicon files into `docs/assets/` and configure `zensical.toml`:

- `favicon = "assets/favicon.svg"` — SVG favicon (cleanest)
- `logo = "assets/logo-light.svg"` — light mode logo
- Color palette using CSS custom properties via `extra_css`:
  - Primary: `#6A9E7A` (Fern)
  - Accent: `#4E7A5F` (Forest)
  - Light background: `#F5F2EC` (Parchment)
  - Dark background: `#131512` (Dark BG)
- Light/dark mode toggle with appropriate colors for each

### 4. Exclude external_ignored from build

Add a `.zensicalignore` or handle via the `docs_dir` structure. Since zensical builds everything in `docs_dir`, move `external_ignored/` out of `docs/` or add it to zensical's exclude list. Simplest: the `zensical.toml` already has `docs_dir = "."` and the `.gitignore` in `site/` already lists `external_ignored/` — check if zensical respects this or if we need explicit exclusion.

## Risks / Trade-offs

- **Detailed spec page is large** → Acceptable; it's a reference document, not meant to be read top-to-bottom
- **Placeholder pages removed from nav** → Files still exist, can be added back when features are implemented. No content loss.
- **SVG favicon browser support** → All modern browsers support SVG favicons. Acceptable trade-off for quality.
- **Custom CSS for colors** → Zensical may support palette configuration natively via `[project.theme.palette]`. Prefer native config over custom CSS if possible.
