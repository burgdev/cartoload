"""Checkpoint management for build resume support.

Writes a JSON checkpoint file after each zoom level completes,
allowing interrupted builds to resume without reprocessing.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# JSON schema version for forward compatibility
CHECKPOINT_VERSION = 1


class CheckpointData:
    """In-memory representation of a build checkpoint."""

    def __init__(
        self,
        layer_id: str,
        completed_zoom_levels: list[int] | None = None,
        remaining_zoom_levels: list[int] | None = None,
        total_tiles: int = 0,
        processed_tiles: int = 0,
        started_at: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        self.layer_id = layer_id
        self.completed_zoom_levels = completed_zoom_levels or []
        self.remaining_zoom_levels = remaining_zoom_levels or []
        self.total_tiles = total_tiles
        self.processed_tiles = processed_tiles
        self.started_at = started_at or _now_iso()
        self.updated_at = updated_at or _now_iso()

    def to_dict(self) -> dict:
        return {
            "version": CHECKPOINT_VERSION,
            "layer": self.layer_id,
            "completed_zoom_levels": self.completed_zoom_levels,
            "remaining_zoom_levels": self.remaining_zoom_levels,
            "total_tiles": self.total_tiles,
            "processed_tiles": self.processed_tiles,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CheckpointData:
        version = data.get("version", 0)
        if version > CHECKPOINT_VERSION:
            logger.warning(
                "Checkpoint version %d is newer than supported (%d)",
                version,
                CHECKPOINT_VERSION,
            )
        return cls(
            layer_id=data["layer"],
            completed_zoom_levels=data.get("completed_zoom_levels", []),
            remaining_zoom_levels=data.get("remaining_zoom_levels", []),
            total_tiles=data.get("total_tiles", 0),
            processed_tiles=data.get("processed_tiles", 0),
            started_at=data.get("started_at"),
            updated_at=data.get("updated_at"),
        )


def checkpoint_path(cache_dir: Path, layer_id: str) -> Path:
    """Return the checkpoint file path for a given layer."""
    return cache_dir / f"{layer_id}.checkpoint"


def write_checkpoint(
    cache_dir: Path,
    data: CheckpointData,
) -> Path:
    """Write a checkpoint file atomically (temp file + rename).

    Args:
        cache_dir: Directory to write the checkpoint file in
        data: Checkpoint data to persist

    Returns:
        Path to the written checkpoint file
    """
    data.updated_at = _now_iso()
    target = checkpoint_path(cache_dir, data.layer_id)
    payload = json.dumps(data.to_dict(), indent=2) + "\n"

    # Atomic write: write to temp file in same dir, then rename
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(cache_dir),
        prefix=f".{data.layer_id}.checkpoint.",
        suffix=".tmp",
    )
    try:
        with open(fd, "w") as f:
            f.write(payload)
        Path(tmp_path).rename(target)
    except BaseException:
        # Clean up temp file on failure
        Path(tmp_path).unlink(missing_ok=True)
        raise

    logger.debug("Checkpoint written: %s", target)
    return target


def read_checkpoint(cache_dir: Path, layer_id: str) -> CheckpointData | None:
    """Read a checkpoint file if it exists and is valid.

    Args:
        cache_dir: Directory containing the checkpoint file
        layer_id: Layer ID to look up

    Returns:
        CheckpointData if valid checkpoint exists, None otherwise
    """
    path = checkpoint_path(cache_dir, layer_id)
    if not path.exists():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if "layer" not in data:
            logger.warning("Checkpoint %s missing 'layer' field", path)
            return None
        cp = CheckpointData.from_dict(data)
        return cp
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Corrupt checkpoint %s: %s", path, e)
        return None


def delete_checkpoint(cache_dir: Path, layer_id: str) -> bool:
    """Delete the checkpoint file for a layer.

    Args:
        cache_dir: Directory containing the checkpoint file
        layer_id: Layer ID

    Returns:
        True if a checkpoint was deleted, False if none existed
    """
    path = checkpoint_path(cache_dir, layer_id)
    if path.exists():
        path.unlink()
        logger.debug("Checkpoint deleted: %s", path)
        return True
    return False


def mark_zoom_complete(
    cache_dir: Path,
    data: CheckpointData,
    zoom: int,
    tiles_processed: int,
) -> Path:
    """Mark a zoom level as completed in the checkpoint.

    Moves zoom from remaining to completed list and updates tile count,
    then writes the checkpoint atomically.

    Args:
        cache_dir: Directory for checkpoint file
        data: Current checkpoint data (modified in-place)
        zoom: Zoom level that completed
        tiles_processed: Number of tiles processed for this zoom level

    Returns:
        Path to the written checkpoint file
    """
    if zoom in data.remaining_zoom_levels:
        data.remaining_zoom_levels.remove(zoom)
    if zoom not in data.completed_zoom_levels:
        data.completed_zoom_levels.append(zoom)
    data.processed_tiles += tiles_processed
    return write_checkpoint(cache_dir, data)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
