## ADDED Requirements

### Requirement: Shared human_size utility
The system SHALL provide a single `human_size(bytes_value)` function that formats byte counts as human-readable strings. All 4 existing copies SHALL be replaced by imports from `utils.py`.

#### Scenario: Format various byte sizes
- **WHEN** `human_size(1536)` is called
- **THEN** it returns a string like "1.5 KB"

#### Scenario: No duplicate implementations
- **WHEN** the codebase is searched for `_human_size` function definitions
- **THEN** they only appear in `utils.py`

### Requirement: Shared encode_jpeg utility
The system SHALL provide an `encode_jpeg(img, quality=95, optimize=True) -> bytes` function. All 11 inline JPEG encoding patterns SHALL use this function.

#### Scenario: Encode PIL Image to JPEG
- **WHEN** `encode_jpeg(pil_image, quality=90)` is called
- **THEN** it returns valid JPEG bytes

### Requirement: Shared ensure_rgba utility
The system SHALL provide an `ensure_rgba(img) -> Image.Image` function that converts any PIL Image mode to RGBA. All 4 inline RGBA normalization patterns SHALL use this function.

#### Scenario: Convert RGB to RGBA
- **WHEN** `ensure_rgba(rgb_image)` is called
- **THEN** it returns the same image with alpha channel added

### Requirement: Shared normalize_bands utility
The system SHALL provide a `normalize_bands(data: np.ndarray, target_bands: int = 3) -> np.ndarray` function. Duplicated band normalization logic SHALL use this function.

#### Scenario: Normalize single-band to 3-band
- **WHEN** `normalize_bands(single_band_array, target_bands=3)` is called
- **THEN** it returns a 3-band array with the single band repeated

### Requirement: Shared progress callback type aliases
The `ProgressCallback` and `ExportProgressCallback` type aliases SHALL be defined once in `utils.py` and imported by all modules that use them.

#### Scenario: Single callback type definitions
- **WHEN** the codebase is searched for `ProgressCallback =` or `ExportProgressCallback =` definitions
- **THEN** each appears exactly once
