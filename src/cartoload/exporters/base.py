from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseExporter(ABC):
    """Abstract base class for map exporters."""

    @abstractmethod
    async def export(self, input_path: Path, output_path: Path) -> Path:
        """Export processed data to device-specific format."""
