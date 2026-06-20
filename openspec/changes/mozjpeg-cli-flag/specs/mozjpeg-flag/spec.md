## ADDED Requirements

### Requirement: User can control mozjpeg encoder selection
The `cartoload build` command SHALL accept a `--mozjpeg` / `--no-mozjpeg` flag that controls whether cjpeg (mozjpeg with trellis quantization) is used for JPEG encoding.

#### Scenario: Default behavior (no flag)
- **WHEN** `cartoload build` is run without `--mozjpeg` or `--no-mozjpeg`
- **THEN** cjpeg SHALL be used if available on PATH, otherwise Pillow SHALL be used

#### Scenario: Explicit mozjpeg enabled
- **WHEN** `cartoload build --mozjpeg` is run and cjpeg is available on PATH
- **THEN** cjpeg SHALL be used for JPEG encoding

#### Scenario: Explicit mozjpeg enabled but cjpeg not found
- **WHEN** `cartoload build --mozjpeg` is run and cjpeg is NOT available on PATH
- **THEN** the command SHALL fail immediately with a clear error message before any processing begins

#### Scenario: Explicit mozjpeg disabled
- **WHEN** `cartoload build --no-mozjpeg` is run
- **THEN** Pillow SHALL be used for all JPEG encoding, regardless of whether cjpeg is on PATH

#### Scenario: Fast mode with mozjpeg disabled
- **WHEN** `cartoload build --fast --no-mozjpeg` is run
- **THEN** Pillow SHALL be used with no mirror-padding (fast mode behavior)

#### Scenario: Fast mode with mozjpeg enabled
- **WHEN** `cartoload build --fast --mozjpeg` is run and cjpeg is available
- **THEN** cjpeg SHALL be used for final encoding, but mirror-padding SHALL be skipped
