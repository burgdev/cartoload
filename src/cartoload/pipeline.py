from __future__ import annotations

from pathlib import Path

from cartoload.config import LayerConfig


async def build_layer(
    layer: LayerConfig,
    cache_dir: str | Path = "./cache",
    output_dir: str | Path = "./output",
) -> Path:
    """Orchestrate download -> process -> export for a single layer.

    This is a stub — actual pipeline logic will be implemented in future changes.
    """
    raise NotImplementedError("Pipeline not yet implemented.")
