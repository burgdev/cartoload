## Context

JPEG quantization tables control which DCT frequency coefficients are preserved vs discarded. Pillow's `quality` parameter scales the standard JPEG tables (from Annex K of ITU-T T.81). These standard tables are optimized for natural photographs — they preserve mid-frequency detail that matters for faces and textures but are less important for map tiles.

The Garmin IOM reference file uses custom tables with a distinctive shape:
- Luminance: very low values (8-61, mean ~27) — preserves fine detail
- Chrominance: heavily clamped at 50 for most coefficients — aggressive color simplification

This shape prioritizes luminance detail (lines, text) over chrominance detail (subtle color gradients), which matches map tile characteristics.

## Goals / Non-Goals

**Goals:**
- Research and develop custom quantization tables optimized for Swiss topographic map tiles
- Implement configurable qtables support in the encoding pipeline
- Provide presets based on IOM reference tables at different quality levels
- Achieve 5-15% file size reduction with acceptable visual quality

**Non-Goals:**
- Not replacing the `quality` parameter — custom tables are optional
- Not developing a general-purpose JPEG optimizer — specific to map tiles
- Not changing the tile dimensions, subsampling, or progressive encoding

## Decisions

### D1: Use scaled IOM tables as presets

**Choice**: Derive presets by scaling the IOM luminance table by a quality factor, keeping the chrominance table fixed (clamped at 50 for most coefficients as in IOM).

**Rationale**: The IOM tables are proven on Garmin devices. Their shape (prioritize luminance, sacrifice chrominance) is well-suited for maps. Scaling preserves the shape while adjusting overall compression level.

**Implementation**: A quality scale factor `s` (0.5 to 5.0) multiplies all luminance values. Scale 1.0 = IOM native quality. Scale 4.0 ≈ our current quality 25 compression level but with the Garmin-optimized shape.

### D2: Configuration via CLI and config file

**Choice**: Add `--qtables` CLI option (accepts preset names like `iom-1x`, `iom-2x`, `iom-4x` or `default`) and optional `jpeg_qtables` field in layer config.

**Rationale**: Makes it easy to experiment without code changes. The `default` preset uses Pillow's standard tables (current behavior).

### D3: A/B testing methodology

**Choice**: For each candidate table set, generate a small preview map and compare:
1. File size vs default tables at same quality
2. Visual quality on key test areas (text labels, contour lines, forest/water boundaries)
3. Garmin device rendering quality

## Risks / Trade-offs

- **Visual quality regression** → Custom tables change which details are preserved. At aggressive scaling, thin lines may soften or text may blur. → Mitigation: start conservative (scale 2x), increase gradually with visual QA at each step.
- **Device-specific rendering** → Garmin devices may render slightly different results than GPXSee for the same JPEG data. → Mitigation: test on device, not just on screen.
- **Over-optimization for one map style** → Tables tuned for Swiss topo may not work well for other map styles. → Mitigation: keep the `default` preset available, document which presets work for which map types.
