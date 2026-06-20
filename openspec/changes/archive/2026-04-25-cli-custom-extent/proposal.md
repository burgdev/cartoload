## Why

Layer configs define a bounding box for the full coverage area (e.g. all of Switzerland), but for testing, preview, or quick iterations users often need a smaller extract. The existing `--bounds "W,S,E,N"` option requires quotes and comma-separated values. Two better alternatives are needed: `--bbox` with 4 separate arguments, and a `--center` + `--width`/`--height` (km) mode that auto-computes the bounding box from a point and dimensions.

## What Changes

- **BREAKING**: Remove the `--bounds` option
- Add `--bbox W S E N` option (4 separate arguments, no quoting needed)
- Add `--lat`, `--lng`, `--width`, `--height` options for center+dimensions (in km) extent specification
- Compute bounding box from center+dimensions using approximate degree-per-km conversion
- Validate that the requested extent fits within the layer's configured bounds
- Apply the custom extent in both `build` and `download` CLI commands

## Capabilities

### New Capabilities

- `cli-extent-override`: CLI options for specifying a custom map extent via bbox or center+km dimensions, with validation against layer bounds

### Modified Capabilities

<!-- No existing specs are modified -->

## Impact

- `src/cartoload/cli.py` — new CLI options and parsing logic for both `build` and `download` commands
- `src/cartoload/config.py` — no changes needed (bounds dict already supports the required shape)
- Users can choose between `--bbox` or `--center`+`--width`/`--height` (mutually exclusive)
