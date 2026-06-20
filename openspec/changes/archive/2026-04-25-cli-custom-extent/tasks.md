## 1. Extent Parsing Helpers

- [x] 1.1 Add `_parse_bbox(value)` function to parse `--bbox` tuple of 4 floats into a bounds dict
- [x] 1.2 Add `_compute_bounds_from_center(lng, lat, width_km, height_km)` function that converts center+km to a bounds dict using the flat-earth approximation
- [x] 1.3 Add `_resolve_extent(bbox, lng, lat, width, height)` function that validates mutual exclusivity and returns the effective bounds dict or None
- [x] 1.4 Add `_validate_extent_within_layer(extent, layer_bounds)` function that checks containment and raises `click.BadParameter` if the requested extent exceeds layer bounds

## 2. CLI Option Wiring

- [x] 2.1 Remove `--bounds` option and `_parse_bounds` function from both `build` and `download` commands
- [x] 2.2 Add `--bbox` (nargs=4), `--lng`, `--lat`, `--width`, `--height` options to the `build` command
- [x] 2.3 Add same options to the `download` command
- [x] 2.4 Wire `_resolve_extent` and `_validate_extent_within_layer` into both commands, replacing the old `_parse_bounds` call

## 3. Tests

- [x] 3.1 Test `_parse_bbox` with valid and invalid inputs
- [x] 3.2 Test `_compute_bounds_from_center` with known coordinates (verify km→degree conversion)
- [x] 3.3 Test `_resolve_extent` mutual exclusivity: rejects when both modes specified, returns correct dict for each single mode
- [x] 3.4 Test `_validate_extent_within_layer`: accepts contained extents, rejects exceeding ones
- [x] 3.5 Test CLI integration: `build --bbox ...`, `build --lng --lat --width --height`, and error cases via Click's CliRunner
