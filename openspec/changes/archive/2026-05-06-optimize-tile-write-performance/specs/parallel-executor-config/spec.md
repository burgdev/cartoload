## ADDED Requirements

### Requirement: Persistent executor pool across tile batches

The system SHALL create the parallel executor (ProcessPoolExecutor or ThreadPoolExecutor) once before the batch loop begins, reuse it for all tile batches within a GMP subfile, and shut it down after all tiles are processed. The executor SHALL NOT be recreated per batch.

#### Scenario: Executor created once for all batches

- **WHEN** processing 585K tiles with batch_size=5000 using parallel mode
- **THEN** the executor SHALL be created exactly once
- **AND** all ~117 batches SHALL submit futures to the same executor instance
- **AND** the executor SHALL be shut down only after all tiles are processed

#### Scenario: Executor shutdown on error

- **WHEN** an exception occurs during tile processing
- **THEN** the executor SHALL be shut down via `try/finally` or context manager
- **AND** no orphaned worker processes SHALL remain

### Requirement: Pre-loaded libraries in worker initializer

The system SHALL use the executor's `initializer` parameter to pre-load rasterio, numpy, and other heavy libraries once per worker process. Worker functions SHALL reference the pre-loaded function via a module-level global variable.

#### Scenario: Libraries loaded once per worker

- **WHEN** a worker process is spawned
- **THEN** the initializer SHALL import `warp_tile_to_jpeg` from `cartoload.processor.rasterio_warp`
- **AND** subsequent tile processing calls SHALL use the pre-loaded function
- **AND** no per-tile module import SHALL occur

### Requirement: Configurable executor mode (process or thread)

The system SHALL support a `--executor` CLI parameter accepting `process` (default) or `thread`. The executor mode SHALL also be configurable via the `CARTOLOAD_EXECUTOR` environment variable. Process mode uses `ProcessPoolExecutor` (faster, more memory). Thread mode uses `ThreadPoolExecutor` (less memory, slightly slower).

#### Scenario: Default executor mode is process

- **WHEN** no `--executor` parameter or `CARTOLOAD_EXECUTOR` environment variable is set
- **THEN** the system SHALL use `ProcessPoolExecutor`
- **AND** each worker SHALL run in a separate process with its own rasterio/GDAL instance

#### Scenario: Thread mode selected

- **WHEN** `--executor thread` is specified (or `CARTOLOAD_EXECUTOR=thread`)
- **THEN** the system SHALL use `ThreadPoolExecutor`
- **AND** all workers SHALL share the same rasterio/GDAL instance (lower memory)
- **AND** processing SHALL be slower than process mode due to GIL contention

#### Scenario: Invalid executor mode

- **WHEN** `--executor foo` is specified
- **THEN** the system SHALL report an error and exit with non-zero status
