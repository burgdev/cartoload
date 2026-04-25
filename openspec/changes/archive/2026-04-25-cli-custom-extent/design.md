## Context

The `cartoload build` and `cartoload download` commands currently accept a `--bounds "W,S,E,N"` option that overrides the layer config's bounding box. This requires quoting and comma-separated values. The user wants to replace it with more ergonomic alternatives.

Layer configs define a full coverage area (e.g. all of Switzerland: 5.96-10.49°E, 45.82-47.81°N). Users frequently want smaller extracts for testing or preview — for example "20 km around Bern" — but computing those coordinates by hand is error-prone.

## Goals / Non-Goals

**Goals:**

- Replace `--bounds` with `--bbox W S E N` (4 separate arguments, no quoting needed)
- Add `--lng`, `--lat`, `--width`, `--height` options for center + km dimensions
- Validate that the computed/requested bbox fits within the layer's configured bounds
- Apply to both `build` and `download` commands

**Non-Goals:**

- Supporting address/place-name resolution as center input
- Reprojection or CRS handling (everything is WGS84)
- Config-file-level overrides for extent (CLI-only for now)

## Decisions

### 1. `--bbox` as a 4-argument Click option replaces `--bounds`

Use `nargs=4` to accept 4 separate float arguments instead of a comma-separated string. This avoids quoting issues on different shells. Remove the old `--bounds` option entirely.

### 2. Center+km to bbox conversion using flat-earth approximation

For the center+dimensions mode, convert km to degrees using:

- Latitude: 1° ≈ 111.32 km (constant)
- Longitude: 1° ≈ 111.32 × cos(latitude) km

This is accurate enough for the typical use case (small extracts of 5-100 km). For a 20 km extent at 47°N, the error is <0.1%.

Alternative considered: Use pyproj for geodetic computation — rejected as over-engineering for the accuracy needed.

### 3. Mutual exclusivity via Click validation

`--bbox` and `--center`+`--width`/`--height` are mutually exclusive. Enforce this in a validation step after Click parses arguments, using a clear error message.

### 4. Bounds containment validation

After computing the effective bbox from whichever mode was chosen, validate that it is fully contained within the layer config's bounds. If not, error with a clear message showing both the requested and allowed extents.

## Risks / Trade-offs

- **Flat-earth approximation inaccuracy** → Acceptable for preview/testing use case. Error is <0.5% for extents up to 100 km in central European latitudes.
- **Breaking change removing `--bounds`** → Cartoload is pre-release, so breaking CLI changes are acceptable at this stage.
- **No projection support** → WGS84 only, which matches the entire pipeline already.
