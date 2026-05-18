from __future__ import annotations

import pytest

from cartoload.config import LayerConfig, SourceConfig


@pytest.fixture
def sample_source() -> SourceConfig:
    """A sample WMTS source config for testing."""
    return SourceConfig(
        id="test_wmts",
        type="wmts",
        urls=["https://example.com/{layer}/{z}/${x}/${y}.png"],
        attribution="© Test",
        rate_limit_ms=100,
        max_threads=2,
    )


@pytest.fixture
def sample_layer() -> LayerConfig:
    """A sample raster layer config for testing."""
    return LayerConfig(
        id="test_layer",
        name="Test Layer",
        description="A test layer",
        type="raster",
        format="wmts",
        source="test_wmts",
        zoom_levels=[10, 12, 14],
    )
