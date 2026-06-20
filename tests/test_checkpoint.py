"""Tests for checkpoint management: create, resume, force-restart, corrupt handling, cleanup."""

from __future__ import annotations

import json
from pathlib import Path


from cartoload.processor.checkpoint import (
    CheckpointData,
    delete_checkpoint,
    mark_zoom_complete,
    read_checkpoint,
    write_checkpoint,
    checkpoint_path,
)


# ---------------------------------------------------------------------------
# CheckpointData unit tests
# ---------------------------------------------------------------------------


class TestCheckpointData:
    def test_defaults(self):
        cp = CheckpointData(layer_id="test_layer")
        assert cp.layer_id == "test_layer"
        assert cp.completed_zoom_levels == []
        assert cp.remaining_zoom_levels == []
        assert cp.total_tiles == 0
        assert cp.processed_tiles == 0
        assert cp.started_at is not None
        assert cp.updated_at is not None

    def test_to_dict_roundtrip(self):
        original = CheckpointData(
            layer_id="lyr",
            completed_zoom_levels=[10],
            remaining_zoom_levels=[12, 14],
            total_tiles=100,
            processed_tiles=30,
            started_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T01:00:00+00:00",
        )
        d = original.to_dict()
        assert d["layer"] == "lyr"
        assert d["version"] == 1
        assert d["completed_zoom_levels"] == [10]
        assert d["remaining_zoom_levels"] == [12, 14]
        assert d["total_tiles"] == 100
        assert d["processed_tiles"] == 30

        restored = CheckpointData.from_dict(d)
        assert restored.layer_id == original.layer_id
        assert restored.completed_zoom_levels == original.completed_zoom_levels
        assert restored.remaining_zoom_levels == original.remaining_zoom_levels
        assert restored.total_tiles == original.total_tiles
        assert restored.processed_tiles == original.processed_tiles

    def test_from_dict_missing_optional_fields(self):
        data = {"layer": "minimal"}
        cp = CheckpointData.from_dict(data)
        assert cp.layer_id == "minimal"
        assert cp.completed_zoom_levels == []
        assert cp.remaining_zoom_levels == []


# ---------------------------------------------------------------------------
# Write and read tests
# ---------------------------------------------------------------------------


class TestWriteReadCheckpoint:
    def test_write_creates_file(self, tmp_path: Path):
        cp = CheckpointData(layer_id="test", remaining_zoom_levels=[10, 12])
        path = write_checkpoint(tmp_path, cp)

        assert path.exists()
        assert path.name == "test.checkpoint"

    def test_write_is_valid_json(self, tmp_path: Path):
        cp = CheckpointData(layer_id="test")
        path = write_checkpoint(tmp_path, cp)

        data = json.loads(path.read_text())
        assert data["layer"] == "test"

    def test_read_returns_data(self, tmp_path: Path):
        cp = CheckpointData(
            layer_id="test",
            completed_zoom_levels=[10],
            remaining_zoom_levels=[12],
        )
        write_checkpoint(tmp_path, cp)

        result = read_checkpoint(tmp_path, "test")
        assert result is not None
        assert result.layer_id == "test"
        assert result.completed_zoom_levels == [10]
        assert result.remaining_zoom_levels == [12]

    def test_read_missing_returns_none(self, tmp_path: Path):
        assert read_checkpoint(tmp_path, "nonexistent") is None

    def test_read_corrupt_json_returns_none(self, tmp_path: Path):
        cp_file = tmp_path / "corrupt.checkpoint"
        cp_file.write_text("not valid json{{{")

        result = read_checkpoint(tmp_path, "corrupt")
        assert result is None

    def test_read_missing_layer_field_returns_none(self, tmp_path: Path):
        cp_file = tmp_path / "bad.checkpoint"
        cp_file.write_text(json.dumps({"version": 1}) + "\n")

        result = read_checkpoint(tmp_path, "bad")
        assert result is None

    def test_write_overwrites_existing(self, tmp_path: Path):
        cp1 = CheckpointData(layer_id="test", completed_zoom_levels=[10])
        write_checkpoint(tmp_path, cp1)

        cp2 = CheckpointData(layer_id="test", completed_zoom_levels=[10, 12])
        write_checkpoint(tmp_path, cp2)

        result = read_checkpoint(tmp_path, "test")
        assert result is not None
        assert result.completed_zoom_levels == [10, 12]

    def test_atomic_write_no_temp_left_on_success(self, tmp_path: Path):
        cp = CheckpointData(layer_id="test")
        write_checkpoint(tmp_path, cp)

        # No temp files should remain
        temp_files = list(tmp_path.glob(".*.checkpoint.*.tmp"))
        assert len(temp_files) == 0


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------


class TestDeleteCheckpoint:
    def test_delete_existing(self, tmp_path: Path):
        cp = CheckpointData(layer_id="test")
        write_checkpoint(tmp_path, cp)

        assert delete_checkpoint(tmp_path, "test") is True
        assert read_checkpoint(tmp_path, "test") is None

    def test_delete_nonexistent(self, tmp_path: Path):
        assert delete_checkpoint(tmp_path, "nonexistent") is False


# ---------------------------------------------------------------------------
# mark_zoom_complete tests
# ---------------------------------------------------------------------------


class TestMarkZoomComplete:
    def test_marks_zoom_and_updates_count(self, tmp_path: Path):
        cp = CheckpointData(
            layer_id="test",
            remaining_zoom_levels=[10, 12, 14],
            completed_zoom_levels=[],
            processed_tiles=0,
        )
        mark_zoom_complete(tmp_path, cp, 10, 25)

        assert 10 in cp.completed_zoom_levels
        assert 10 not in cp.remaining_zoom_levels
        assert cp.processed_tiles == 25

    def test_multiple_zooms(self, tmp_path: Path):
        cp = CheckpointData(
            layer_id="test",
            remaining_zoom_levels=[10, 12, 14],
            completed_zoom_levels=[],
            processed_tiles=0,
        )
        mark_zoom_complete(tmp_path, cp, 10, 20)
        mark_zoom_complete(tmp_path, cp, 12, 80)

        assert cp.completed_zoom_levels == [10, 12]
        assert cp.remaining_zoom_levels == [14]
        assert cp.processed_tiles == 100

    def test_persists_to_disk(self, tmp_path: Path):
        cp = CheckpointData(
            layer_id="test",
            remaining_zoom_levels=[10, 12],
            completed_zoom_levels=[],
            processed_tiles=0,
        )
        mark_zoom_complete(tmp_path, cp, 10, 30)

        result = read_checkpoint(tmp_path, "test")
        assert result is not None
        assert result.completed_zoom_levels == [10]
        assert result.remaining_zoom_levels == [12]
        assert result.processed_tiles == 30

    def test_idempotent_double_mark(self, tmp_path: Path):
        cp = CheckpointData(
            layer_id="test",
            remaining_zoom_levels=[10],
            completed_zoom_levels=[],
            processed_tiles=0,
        )
        mark_zoom_complete(tmp_path, cp, 10, 5)
        mark_zoom_complete(tmp_path, cp, 10, 5)

        # Should only appear once in completed, but tiles counted twice
        assert cp.completed_zoom_levels == [10]
        assert cp.processed_tiles == 10


# ---------------------------------------------------------------------------
# checkpoint_path tests
# ---------------------------------------------------------------------------


class TestCheckpointPath:
    def test_path_format(self, tmp_path: Path):
        p = checkpoint_path(tmp_path, "my_layer")
        assert p == tmp_path / "my_layer.checkpoint"


# ---------------------------------------------------------------------------
# Integration: resume scenario
# ---------------------------------------------------------------------------


class TestCheckpointResume:
    def test_resume_skips_completed_zooms(self, tmp_path: Path):
        """Simulate: zoom 10 done, interrupt, resume for zoom 12."""
        # First run: complete zoom 10
        cp = CheckpointData(
            layer_id="test",
            remaining_zoom_levels=[10, 12],
            completed_zoom_levels=[],
            processed_tiles=0,
        )
        write_checkpoint(tmp_path, cp)
        mark_zoom_complete(tmp_path, cp, 10, 25)

        # Simulate resume: read checkpoint back
        resumed = read_checkpoint(tmp_path, "test")
        assert resumed is not None
        assert resumed.completed_zoom_levels == [10]
        assert resumed.remaining_zoom_levels == [12]

        # Complete zoom 12
        mark_zoom_complete(tmp_path, resumed, 12, 100)

        assert resumed.completed_zoom_levels == [10, 12]
        assert resumed.remaining_zoom_levels == []
        assert resumed.processed_tiles == 125

    def test_force_restarts_from_scratch(self, tmp_path: Path):
        """--force should delete checkpoint and start fresh."""
        cp = CheckpointData(
            layer_id="test",
            completed_zoom_levels=[10, 12],
            processed_tiles=125,
        )
        write_checkpoint(tmp_path, cp)

        # --force deletes checkpoint
        delete_checkpoint(tmp_path, "test")

        assert read_checkpoint(tmp_path, "test") is None

    def test_corrupt_checkpoint_treated_as_missing(self, tmp_path: Path):
        """A corrupt checkpoint file should not prevent starting."""
        cp_file = tmp_path / "test.checkpoint"
        cp_file.write_text("CORRUPTED!!!")

        result = read_checkpoint(tmp_path, "test")
        assert result is None
