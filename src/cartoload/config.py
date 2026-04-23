from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceConfig:
    """Configuration for a geodata source (WMTS, GeoTIFF/STAC, etc.)."""

    id: str
    type: str  # wmts, geotiff, gpkg, geojson, pbf
    url_template: str | None = None
    stac_url: str | None = None
    attribution: str = ""
    rate_limit_ms: int = 150
    max_threads: int = 4


@dataclass
class LayerConfig:
    """Configuration for a map layer to build."""

    id: str
    name: str
    description: str = ""
    type: str = "raster"  # raster, raster_overlay, vector
    source: str = ""
    wmts_fallback: str | None = None
    wmts_layer: str | None = None
    geotiff_product: str | None = None
    zoom_levels: list[int] = field(default_factory=list)
    exporter: str = "garmin_img"
    output: str = ""
    bounds: dict[str, float] | None = None


@dataclass
class Config:
    """Top-level configuration container holding all sources and layers."""

    sources: dict[str, SourceConfig]
    layers: dict[str, LayerConfig]
    bounds: dict[str, float] | None = None


# Allowed source types for Phase 1
ALLOWED_SOURCE_TYPES = {"wmts", "geotiff"}

# Required fields for each source type
SOURCE_TYPE_REQUIRED_FIELDS = {
    "wmts": ["url_template"],
    "geotiff": ["stac_url"],
}

logger = logging.getLogger(__name__)


def load_sources_file(path: str) -> dict[str, SourceConfig]:
    """
    Load and parse a YAML sources configuration file.

    Args:
        path: Path to the YAML file containing sources

    Returns:
        Dictionary of SourceConfig instances keyed by source ID

    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If validation fails (missing required fields, invalid types, etc.)
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{path}: Expected YAML dict, got {type(data).__name__}")

    if "sources" not in data:
        raise ValueError(f"{path}: Missing required top-level 'sources' key")

    sources_data = data["sources"]
    if not isinstance(sources_data, dict):
        raise ValueError(
            f"{path}: 'sources' must be a dict, got {type(sources_data).__name__}"
        )

    sources = {}
    for source_id, source_dict in sources_data.items():
        if not isinstance(source_dict, dict):
            raise ValueError(
                f"{path}: Source '{source_id}' must be a dict, got {type(source_dict).__name__}"
            )

        # Validate 'type' field exists
        if "type" not in source_dict:
            raise ValueError(
                f"{path}: Source '{source_id}' missing required field 'type'"
            )

        source_type = source_dict["type"]

        # Validate type is in allowed list
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"{path}: Source '{source_id}' has invalid type '{source_type}'. "
                f"Valid types: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}"
            )

        # Validate type-specific required fields
        if source_type in SOURCE_TYPE_REQUIRED_FIELDS:
            for required_field in SOURCE_TYPE_REQUIRED_FIELDS[source_type]:
                if (
                    required_field not in source_dict
                    or source_dict[required_field] is None
                ):
                    raise ValueError(
                        f"{path}: Source '{source_id}' (type={source_type}) "
                        f"missing required field '{required_field}'"
                    )

        # Validate optional fields have correct types
        if "rate_limit_ms" in source_dict and not isinstance(
            source_dict.get("rate_limit_ms"), int
        ):
            raise ValueError(
                f"{path}: Source '{source_id}' field 'rate_limit_ms' must be an integer"
            )

        if "max_threads" in source_dict and not isinstance(
            source_dict.get("max_threads"), int
        ):
            raise ValueError(
                f"{path}: Source '{source_id}' field 'max_threads' must be an integer"
            )

        # Create SourceConfig instance
        sources[source_id] = SourceConfig(
            id=source_id,
            type=source_type,
            url_template=source_dict.get("url_template"),
            stac_url=source_dict.get("stac_url"),
            attribution=source_dict.get("attribution", ""),
            rate_limit_ms=source_dict.get("rate_limit_ms", 150),
            max_threads=source_dict.get("max_threads", 4),
        )

    return sources


def load_layers_file(
    path: str,
) -> tuple[dict[str, LayerConfig], dict[str, float] | None]:
    """
    Load and parse a YAML layers configuration file.

    Args:
        path: Path to the YAML file containing layers

    Returns:
        Tuple of (layers dict, bounds dict or None)

    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If validation fails
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Layer file not found: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{path}: Expected YAML dict, got {type(data).__name__}")

    if "layers" not in data:
        raise ValueError(f"{path}: Missing required top-level 'layers' key")

    layers_data = data["layers"]
    if not isinstance(layers_data, dict):
        raise ValueError(
            f"{path}: 'layers' must be a dict, got {type(layers_data).__name__}"
        )

    # Extract file-level bounds if present
    bounds = None
    if "bounds" in data:
        bounds_data = data["bounds"]
        if not isinstance(bounds_data, dict):
            raise ValueError(f"{path}: 'bounds' must be a dict")

        # Validate bounds fields
        required_bounds_fields = ["west", "east", "south", "north"]
        for field in required_bounds_fields:
            if field not in bounds_data:
                raise ValueError(f"{path}: 'bounds' missing required field '{field}'")
            if not isinstance(bounds_data[field], (int, float)):
                raise ValueError(f"{path}: 'bounds.{field}' must be numeric")

        # Validate bounds make sense
        if bounds_data["west"] >= bounds_data["east"]:
            raise ValueError(
                f"{path}: 'bounds' invalid: west ({bounds_data['west']}) >= east ({bounds_data['east']})"
            )
        if bounds_data["south"] >= bounds_data["north"]:
            raise ValueError(
                f"{path}: 'bounds' invalid: south ({bounds_data['south']}) >= north ({bounds_data['north']})"
            )

        bounds = bounds_data

    # Parse layers
    layers = {}
    required_layer_fields = ["name", "source", "zoom_levels", "exporter", "output"]

    for layer_id, layer_dict in layers_data.items():
        if not isinstance(layer_dict, dict):
            raise ValueError(
                f"{path}: Layer '{layer_id}' must be a dict, got {type(layer_dict).__name__}"
            )

        # Validate required fields
        for field in required_layer_fields:
            if (
                field not in layer_dict
                or layer_dict[field] is None
                or layer_dict[field] == ""
            ):
                raise ValueError(
                    f"{path}: Layer '{layer_id}' missing required field '{field}'"
                )

        # Validate zoom_levels
        zoom_levels = layer_dict["zoom_levels"]
        if not isinstance(zoom_levels, list):
            raise ValueError(
                f"{path}: Layer '{layer_id}' field 'zoom_levels' must be a list, "
                f"got {type(zoom_levels).__name__}"
            )

        if len(zoom_levels) == 0:
            raise ValueError(
                f"{path}: Layer '{layer_id}' field 'zoom_levels' cannot be empty"
            )

        for zoom in zoom_levels:
            if not isinstance(zoom, int):
                raise ValueError(
                    f"{path}: Layer '{layer_id}' field 'zoom_levels' must contain integers, "
                    f"got {type(zoom).__name__}"
                )
            if zoom < 0 or zoom > 22:
                raise ValueError(
                    f"{path}: Layer '{layer_id}' has invalid zoom level {zoom}. "
                    f"Valid range: 0-22"
                )

        # Validate layer-level bounds if present
        layer_bounds = None
        if "bounds" in layer_dict and layer_dict["bounds"] is not None:
            bounds_data = layer_dict["bounds"]
            if not isinstance(bounds_data, dict):
                raise ValueError(
                    f"{path}: Layer '{layer_id}' field 'bounds' must be a dict"
                )

            required_bounds_fields = ["west", "east", "south", "north"]
            for field in required_bounds_fields:
                if field not in bounds_data:
                    raise ValueError(
                        f"{path}: Layer '{layer_id}' bounds missing required field '{field}'"
                    )
                if not isinstance(bounds_data[field], (int, float)):
                    raise ValueError(
                        f"{path}: Layer '{layer_id}' bounds.{field} must be numeric"
                    )

            if bounds_data["west"] >= bounds_data["east"]:
                raise ValueError(
                    f"{path}: Layer '{layer_id}' bounds invalid: "
                    f"west ({bounds_data['west']}) >= east ({bounds_data['east']})"
                )
            if bounds_data["south"] >= bounds_data["north"]:
                raise ValueError(
                    f"{path}: Layer '{layer_id}' bounds invalid: "
                    f"south ({bounds_data['south']}) >= north ({bounds_data['north']})"
                )

            layer_bounds = bounds_data
        elif bounds is not None:
            # Inherit file-level bounds if layer has none
            layer_bounds = bounds

        # Create LayerConfig instance
        layers[layer_id] = LayerConfig(
            id=layer_id,
            name=layer_dict["name"],
            description=layer_dict.get("description", ""),
            type=layer_dict.get("type", "raster"),
            source=layer_dict["source"],
            wmts_fallback=layer_dict.get("wmts_fallback"),
            wmts_layer=layer_dict.get("wmts_layer"),
            geotiff_product=layer_dict.get("geotiff_product"),
            zoom_levels=zoom_levels,
            exporter=layer_dict["exporter"],
            output=layer_dict["output"],
            bounds=layer_bounds,
        )

    return (layers, bounds)


def merge_sources(*source_dicts: dict[str, SourceConfig]) -> dict[str, SourceConfig]:
    """
    Merge multiple source dictionaries with last-file-wins semantics.

    Args:
        *source_dicts: Variable number of source dictionaries to merge

    Returns:
        Merged dictionary of SourceConfig instances
    """
    merged = {}
    for source_dict in source_dicts:
        for source_id, source_config in source_dict.items():
            if source_id in merged:
                logger.warning(
                    f"Source '{source_id}' defined multiple times, using later definition"
                )
            merged[source_id] = source_config
    return merged


def merge_layers(
    *layer_results: tuple[dict[str, LayerConfig], dict[str, float] | None],
) -> tuple[dict[str, LayerConfig], dict[str, float] | None]:
    """
    Merge multiple layer results with last-file-wins semantics for both layers and bounds.

    Args:
        *layer_results: Variable number of (layers dict, bounds dict or None) tuples

    Returns:
        Tuple of (merged layers dict, merged bounds dict or None)
    """
    merged_layers = {}
    merged_bounds = None

    for layers_dict, bounds in layer_results:
        for layer_id, layer_config in layers_dict.items():
            if layer_id in merged_layers:
                logger.warning(
                    f"Layer '{layer_id}' defined multiple times, using later definition"
                )
            merged_layers[layer_id] = layer_config

        if bounds is not None:
            if merged_bounds is not None:
                logger.warning(
                    "File-level bounds defined multiple times, using later definition"
                )
            merged_bounds = bounds

    return (merged_layers, merged_bounds)


def resolve_references(
    layers: dict[str, LayerConfig], sources: dict[str, SourceConfig]
) -> None:
    """
    Validate that all layer source references point to loaded sources.

    Args:
        layers: Dictionary of LayerConfig instances
        sources: Dictionary of SourceConfig instances

    Raises:
        ValueError: If any layer references an undefined source
    """
    unresolved = []
    for layer_id, layer_config in layers.items():
        if layer_config.source not in sources:
            unresolved.append((layer_id, layer_config.source))

    if unresolved:
        available_sources = ", ".join(sorted(sources.keys()))
        error_lines = [
            f"  - Layer '{layer_id}' references undefined source '{source_ref}'"
            for layer_id, source_ref in unresolved
        ]
        raise ValueError(
            "Unresolved source references:\n"
            + "\n".join(error_lines)
            + f"\n\nAvailable sources: {available_sources}"
        )


def load_config(source_paths: list[str], layer_paths: list[str]) -> Config:
    """
    Load and merge all configuration files into a single Config object.

    Args:
        source_paths: List of paths to source YAML files
        layer_paths: List of paths to layer YAML files

    Returns:
        Config object containing merged sources and layers

    Raises:
        FileNotFoundError: If any config file does not exist
        ValueError: If any validation fails
    """
    # Load all source files
    source_dicts = []
    for path in source_paths:
        source_dicts.append(load_sources_file(path))

    # Merge sources
    merged_sources = merge_sources(*source_dicts) if source_dicts else {}

    # Load all layer files
    layer_results = []
    for path in layer_paths:
        layer_results.append(load_layers_file(path))

    # Merge layers and bounds
    merged_layers, merged_bounds = (
        merge_layers(*layer_results) if layer_results else ({}, None)
    )

    # Resolve source references
    if merged_layers:
        resolve_references(merged_layers, merged_sources)

    return Config(sources=merged_sources, layers=merged_layers, bounds=merged_bounds)
