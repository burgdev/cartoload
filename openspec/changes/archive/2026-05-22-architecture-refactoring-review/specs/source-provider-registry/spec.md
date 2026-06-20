## MODIFIED Requirements

### Requirement: Source and processor registries use generic Registry class
The source registry (`source/base.py`, renamed from `downloader/source.py`) and processor registry (`processor/base.py`, renamed from `processor/provider.py`) SHALL use the generic `Registry[T]` class. Their public API SHALL remain functionally equivalent:
- Source: `register_source`, `resolve_source`, `get_source_registry`
- Processor: `register_processor` (renamed from `register_provider`), `make_processor` (renamed from `make_provider`), `get_processor_registry` (renamed from `get_provider_registry`)

#### Scenario: Existing source registration still works
- **WHEN** a source class is registered via `register_source("wmts", WmtsSource)`
- **THEN** `resolve_source("wmts")` returns `WmtsSource`

#### Scenario: Existing processor registration still works
- **WHEN** a processor class is registered via `register_processor("geotiff", GeotiffProcessor)`
- **THEN** `make_processor("geotiff", ...)` creates a `GeotiffProcessor` instance
