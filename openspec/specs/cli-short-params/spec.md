## ADDED Requirements

### Requirement: Short flag aliases for CLI parameters

Every CLI parameter SHALL have a short flag alias as defined in the mapping below. The long form SHALL remain unchanged and functional.

**Mapping:**

| Long           | Short | Commands              |
| -------------- | ----- | --------------------- |
| `--sources`    | `-S`  | build, download, list |
| `--layers`     | `-L`  | build, download, list |
| `--layer`      | `-l`  | build, download       |
| `--exporter`   | `-e`  | build                 |
| `--bbox`       | `-b`  | build, download       |
| `--lng`        | `-x`  | build, download       |
| `--lat`        | `-y`  | build, download       |
| `--width`      | `-W`  | build, download       |
| `--height`     | `-H`  | build, download       |
| `--zoom`       | `-z`  | build, download       |
| `--output-dir` | `-o`  | build, split          |
| `--cache-dir`  | `-c`  | build, download       |
| `--force`      | `-f`  | build                 |
| `--quality`    | `-q`  | build                 |

`--no-download` SHALL NOT receive a short form.

#### Scenario: Short flag invokes same behavior as long form

- **WHEN** user runs `cartoload build -S sources.yaml -L layers.yaml -l switzerland -z 12 -o ./out`
- **THEN** the command behaves identically to `cartoload build --sources sources.yaml --layers layers.yaml --layer switzerland --zoom 12 --output-dir ./out`

#### Scenario: Mixing short and long forms

- **WHEN** user runs `cartoload build -S sources.yaml --layers layers.yaml -l switzerland`
- **THEN** the command works as expected, combining short and long forms freely

#### Scenario: Help output shows short flags

- **WHEN** user runs `cartoload build --help`
- **THEN** the help text displays both short and long forms for every parameter (e.g., `-S, --sources`)
