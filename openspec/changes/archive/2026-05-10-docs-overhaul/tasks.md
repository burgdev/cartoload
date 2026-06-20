## 1. Zensical Branding Setup

- [x] 1.1 Copy `assets/logo/favicon.svg` to `docs/assets/favicon.svg`
- [x] 1.2 Copy `assets/logo/logo_light.svg` to `docs/assets/logo-light.svg`
- [x] 1.3 Copy `assets/logo/logo_dark.svg` to `docs/assets/logo-dark.svg`
- [x] 1.4 Update `docs/zensical.toml`: add `[project.theme]` section with favicon, logo, palette (Alpine green), language, features, dark mode toggle
- [x] 1.5 Create `docs/stylesheets/extra.css` with custom color overrides if zensical native palette config is insufficient
- [x] 1.6 Build docs with `zensical build` and verify logo, favicon, and colors render correctly
- [x] 1.7 Exclude `external_ignored/` from zensical build (remove from site output)

## 2. Restructure Navigation and Create New Pages

- [x] 2.1 Create `docs/guides/build-a-map.md` — build workflow guide with examples
- [x] 2.2 Create `docs/guides/analyze-img.md` — analyze IMG files guide (moved from cli.md and garmin-img-resources.md sections)
- [x] 2.3 Create `docs/guides/split-maps.md` — split large maps guide
- [x] 2.4 Create `docs/img-format/overview.md` — simplified high-level overview of Garmin IMG format
- [x] 2.5 Move and clean `docs/exporters/garmin-img.md` to `docs/img-format/detailed-spec.md` — remove swisstopo IMG references, keep IOM references
- [x] 2.6 Create `docs/img-format/tools-resources.md` — cleaned-up version of `garmin-img-resources.md` (remove planning/status sections, keep tool descriptions and links)
- [x] 2.7 Create `docs/api-reference.md` — placeholder for Python API docs
- [x] 2.8 Rewrite `docs/index.md` — landing page, remove swisstopo IMG references
- [x] 2.9 Update `docs/getting-started.md` — keep swisstopo example config, ensure clean walkthrough

## 3. Update Existing Pages

- [x] 3.1 Update `docs/configuration/sources.md` — review for correctness and conciseness
- [x] 3.2 Update `docs/configuration/layers.md` — use generic bounds example
- [x] 3.3 Update `docs/cli.md` — keep as CLI reference, remove analyze examples that moved to guide (keep command synopsis only)

## 4. Clean Up and Remove Old Pages

- [x] 4.1 Remove `docs/configuration/style.md` from nav (placeholder)
- [x] 4.2 Remove `docs/exporters/garmin-img-vector.md` from nav (placeholder)
- [x] 4.3 Remove `docs/exporters/adding-exporters.md` from nav (skeleton)
- [x] 4.4 Remove `docs/exporters/garmin-img-resources.md` (replaced by `docs/img-format/tools-resources.md`)
- [x] 4.5 Remove old `docs/exporters/garmin-img.md` (replaced by `docs/img-format/detailed-spec.md`)

## 5. Final Verification

- [x] 5.1 Build docs with `zensical build` — no errors or warnings
- [x] 5.2 Verify all nav links work correctly
- [x] 5.3 Verify no swisstopo IMG file references remain (grep for SwissTopo_West, SwissTopo_Est, SwissTopo sample)
- [x] 5.4 Verify `external_ignored/` is excluded from site output
- [x] 5.5 Verify logo, favicon, and color scheme render in both light and dark mode
