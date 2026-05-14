## ADDED Requirements

### Requirement: Composite layer respects quality parameter
The composite build pipeline SHALL apply the `--quality` CLI parameter to the final JPEG encoding of composited tiles, consistent with how single-layer builds apply quality.

#### Scenario: Quality parameter reduces composite IMG file size
- **WHEN** a composite layer is built with `--quality 30`
- **THEN** the resulting IMG file size SHALL be comparable to a single-layer build with the same quality setting (not 2-3x larger)

#### Scenario: Composite tiles composed at full quality then re-encoded
- **WHEN** sub-layer tiles are composited for a composite layer
- **THEN** each sub-layer tile SHALL be loaded at its original quality, the composite SHALL be performed at full resolution, and the `--quality` parameter SHALL only be applied during the final JPEG encoding step

#### Scenario: Default quality when not specified
- **WHEN** a composite layer is built without `--quality`
- **THEN** the composite processor SHALL use quality 85 as default (existing behavior)
