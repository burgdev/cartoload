from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseDownloader(ABC):
    """Abstract base class for geodata downloaders."""

    @abstractmethod
    async def download(self, output_dir: Path) -> list[Path]:
        """Download data and return list of downloaded file paths."""
