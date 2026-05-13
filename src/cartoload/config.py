from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceConfig:
    """Configuration for a geodata source (WMTS, GeoTIFF/STAC, etc.)."""

    id: str
    type: str  # wmts, stac, geotiff
    url_template: str | None = None
    urls: list[str] = field(default_factory=list)
    attribution: str = ""
    rate_limit_ms: int = 150
    max_threads: int = 4
    crs: str | None = None
    defaults: dict[str, str] = field(default_factory=dict)
    asset_filter: dict[str, str] | None = None
    config_dir: str | None = (
        None  # Directory of the source config file (for relative path resolution)
    )


@dataclass
class CompositeSubLayer:
    """A sub-layer within a composite layer definition.

    Sub-layers are either inline (with their own source) or
    references to existing top-level layers. After resolution, all sub-layers
    have concrete source values.

    All template variables (layer, extension, etc.) are stored in source_args.
    Only per-tile variables (x, y, z, zoom) are predefined.
    """

    name: str = ""
    source: str = ""
    zoom_levels: list[int] = field(default_factory=list)
    opacity: float | dict[int, float] = 1.0
    ref: str | None = None
    source_args: dict[str, str] = field(default_factory=dict)

    @property
    def extension(self) -> str:
        """Tile format, derived from source_args.extension (default: jpeg)."""
        return self.source_args.get("extension", "jpeg")

    def is_resolved(self) -> bool:
        """Return True if this sub-layer has a concrete source (not a ref)."""
        return bool(self.source)


@dataclass
class LayerConfig:
    """Configuration for a map layer to build."""

    id: str
    name: str
    description: str = ""
    type: str = "raster"  # raster, raster_overlay, vector
    source: str = ""
    wmts_fallback: str | None = None
    source_args: dict[str, str] = field(default_factory=dict)
    asset_filter: dict[str, str] | None = None
    zoom_levels: list[int] = field(default_factory=list)
    exporter: str = "garmin_img"
    output: str = ""
    bounds: dict[str, float] | None = None
    layers: list[CompositeSubLayer] | None = None

    def is_composite(self) -> bool:
        """Return True if this layer is a composite of multiple sub-layers."""
        return self.layers is not None and len(self.layers) > 0


@dataclass
class Config:
    """Top-level configuration container holding all sources and layers."""

    sources: dict[str, SourceConfig]
    layers: dict[str, LayerConfig]
    bounds: dict[str, float] | None = None


# Allowed source types
ALLOWED_SOURCE_TYPES = {"wmts", "stac", "geotiff"}

# Required fields for each source type
SOURCE_TYPE_REQUIRED_FIELDS = {
    "wmts": ["url_template"],
    "stac": ["url_template"],
    "geotiff": ["url_template"],
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
                # url_template can be replaced by urls list for all types
                if required_field == "url_template":
                    has_url = (
                        "url_template" in source_dict
                        and source_dict["url_template"] is not None
                    ) or ("urls" in source_dict and source_dict["urls"])
                    if not has_url:
                        raise ValueError(
                            f"{path}: Source '{source_id}' (type={source_type}) "
                            f"missing required field 'url_template' or 'urls'"
                        )
                elif (
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

        if "crs" in source_dict and not isinstance(source_dict.get("crs"), str):
            raise ValueError(
                f"{path}: Source '{source_id}' field 'crs' must be a string"
            )

        # Parse URLs: accept url_template (string) or urls (list) or both
        url_template = source_dict.get("url_template")
        urls = source_dict.get("urls", [])
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list):
            raise ValueError(
                f"{path}: Source '{source_id}' field 'urls' must be a list or string"
            )

        # Parse defaults
        defaults_raw = source_dict.get("defaults", {})
        if defaults_raw is None:
            defaults_raw = {}
        if not isinstance(defaults_raw, dict):
            raise ValueError(
                f"{path}: Source '{source_id}' field 'defaults' must be a dict"
            )

        # Extract asset_filter before str coercion (it's a nested dict)
        asset_filter_raw = defaults_raw.pop("asset_filter", None)
        asset_filter: dict[str, str] | None = None
        if asset_filter_raw is not None:
            if not isinstance(asset_filter_raw, dict):
                raise ValueError(
                    f"{path}: Source '{source_id}' field 'defaults.asset_filter' must be a dict"
                )
            asset_filter = {str(k): str(v) for k, v in asset_filter_raw.items()}

        defaults = {str(k): str(v) for k, v in defaults_raw.items()}

        # Create SourceConfig instance
        sources[source_id] = SourceConfig(
            id=source_id,
            type=source_type,
            url_template=url_template,
            urls=urls,
            attribution=source_dict.get("attribution", ""),
            rate_limit_ms=source_dict.get("rate_limit_ms", 150),
            max_threads=source_dict.get("max_threads", 4),
            crs=source_dict.get("crs"),
            defaults=defaults,
            asset_filter=asset_filter,
            config_dir=str(file_path.parent.resolve()),
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
    required_layer_fields = ["name", "zoom_levels", "exporter", "output"]

    for layer_id, layer_dict in layers_data.items():
        if not isinstance(layer_dict, dict):
            raise ValueError(
                f"{path}: Layer '{layer_id}' must be a dict, got {type(layer_dict).__name__}"
            )

        # Check if this is a composite layer
        has_sub_layers = (
            "layers" in layer_dict
            and layer_dict["layers"] is not None
            and isinstance(layer_dict["layers"], list)
        )

        # Validate required fields (source is optional for composite layers)
        if has_sub_layers:
            for field in required_layer_fields:
                if (
                    field not in layer_dict
                    or layer_dict[field] is None
                    or layer_dict[field] == ""
                ):
                    raise ValueError(
                        f"{path}: Layer '{layer_id}' missing required field '{field}'"
                    )
        else:
            all_required = required_layer_fields + ["source"]
            for field in all_required:
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

        # Parse sub-layers if present (composite layer)
        sub_layers: list[CompositeSubLayer] | None = None
        if has_sub_layers:
            sub_layers = _parse_sub_layers(path, layer_id, layer_dict["layers"])

        # Parse source field: string (source ID) or dict (ref + args)
        raw_source = layer_dict.get("source", "")
        source_id, source_args, layer_asset_filter = _parse_source_field(raw_source)

        # Backward compat: merge wmts_layer into source_args as 'layer'
        wmts_layer = layer_dict.get("wmts_layer")
        if wmts_layer is not None and "layer" not in source_args:
            source_args["layer"] = wmts_layer

        # Backward compat: merge extension into source_args
        extension = layer_dict.get("extension")
        if extension is not None and "extension" not in source_args:
            source_args["extension"] = extension

        # Create LayerConfig instance
        layers[layer_id] = LayerConfig(
            id=layer_id,
            name=layer_dict["name"],
            description=layer_dict.get("description", ""),
            type=layer_dict.get("type", "raster"),
            source=source_id,
            wmts_fallback=layer_dict.get("wmts_fallback"),
            source_args=source_args,
            asset_filter=layer_asset_filter,
            zoom_levels=zoom_levels,
            exporter=layer_dict["exporter"],
            output=layer_dict["output"],
            bounds=layer_bounds,
            layers=sub_layers,
        )

    return (layers, bounds)


def _parse_source_field(
    raw_source: str | dict,
) -> tuple[str, dict[str, str], dict[str, str] | None]:
    """Parse a source field that can be a string (source ID) or dict.

    When a dict is provided, 'ref' is the source ID and remaining keys
    become source_args. All values are converted to strings.
    Nested dict values for 'asset_filter' are extracted separately.

    Returns:
        Tuple of (source_id, source_args, asset_filter or None)
    """
    if isinstance(raw_source, str):
        return (raw_source, {}, None)
    if isinstance(raw_source, dict):
        if "ref" not in raw_source:
            raise ValueError(
                f"Dict source must contain a 'ref' key, got keys: {list(raw_source.keys())}"
            )
        source_id = str(raw_source["ref"])

        # Extract asset_filter before str coercion
        af_raw = raw_source.get("asset_filter")
        asset_filter: dict[str, str] | None = None
        if af_raw is not None:
            if not isinstance(af_raw, dict):
                raise ValueError(
                    f"'asset_filter' must be a dict, got {type(af_raw).__name__}"
                )
            asset_filter = {str(k): str(v) for k, v in af_raw.items()}

        source_args = {
            str(k): str(v)
            for k, v in raw_source.items()
            if k not in ("ref", "asset_filter")
        }
        return (source_id, source_args, asset_filter)
    return ("", {}, None)


def _extract_source_id(raw_source: str | dict) -> str:
    """Extract just the source ID from a string or dict source field."""
    source_id, _, _ = _parse_source_field(raw_source)
    return source_id


def _build_sub_source_args(sub_dict: dict) -> dict[str, str]:
    """Build source_args for a sub-layer from its YAML dict.

    Handles both dict-style source (extract args from dict) and
    backward-compat wmts_layer and extension fields.
    """
    raw_source = sub_dict.get("source", "")
    _, source_args, _ = _parse_source_field(raw_source)

    # Backward compat: merge wmts_layer into source_args as 'layer'
    wmts_layer = sub_dict.get("wmts_layer")
    if wmts_layer is not None and "layer" not in source_args:
        source_args["layer"] = wmts_layer

    # Backward compat: merge extension into source_args
    extension = sub_dict.get("extension")
    if extension is not None and "extension" not in source_args:
        source_args["extension"] = extension

    return source_args


def _parse_sub_layers(
    path: str, layer_id: str, sub_layers_data: list
) -> list[CompositeSubLayer]:
    """Parse and validate sub-layers from a composite layer config.

    Args:
        path: Config file path (for error messages)
        layer_id: Parent layer ID (for error messages)
        sub_layers_data: List of sub-layer dicts from YAML

    Returns:
        List of CompositeSubLayer instances

    Raises:
        ValueError: If validation fails
    """
    if not isinstance(sub_layers_data, list):
        raise ValueError(f"{path}: Layer '{layer_id}' field 'layers' must be a list")

    if len(sub_layers_data) == 0:
        raise ValueError(f"{path}: Layer '{layer_id}' field 'layers' cannot be empty")

    result: list[CompositeSubLayer] = []
    for idx, sub_dict in enumerate(sub_layers_data):
        if not isinstance(sub_dict, dict):
            raise ValueError(
                f"{path}: Layer '{layer_id}' sub-layer [{idx}] must be a dict"
            )

        # Determine if this is a ref or inline sub-layer
        has_ref = "ref" in sub_dict and sub_dict["ref"] is not None
        has_source = "source" in sub_dict and sub_dict["source"] not in (None, "")

        if not has_ref and not has_source:
            raise ValueError(
                f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                f"must have either 'source' or 'ref'"
            )

        if has_ref and has_source:
            raise ValueError(
                f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                f"cannot have both 'source' and 'ref'"
            )

        # Validate opacity
        opacity = sub_dict.get("opacity", 1.0)
        opacity = _validate_opacity(path, layer_id, idx, opacity)

        # Validate extension (backward compat: moved into source_args)
        extension = sub_dict.get("extension")
        if extension is not None and (
            not isinstance(extension, str) or extension not in ("jpeg", "png")
        ):
            raise ValueError(
                f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                f"'extension' must be 'jpeg' or 'png'"
            )

        # Validate zoom_levels
        zoom_levels = sub_dict.get("zoom_levels", [])
        if zoom_levels:
            if not isinstance(zoom_levels, list):
                raise ValueError(
                    f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                    f"'zoom_levels' must be a list"
                )
            for z in zoom_levels:
                if not isinstance(z, int):
                    raise ValueError(
                        f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                        f"'zoom_levels' must contain integers"
                    )

        result.append(
            CompositeSubLayer(
                name=sub_dict.get("name", ""),
                source=_extract_source_id(sub_dict.get("source", "")),
                zoom_levels=zoom_levels,
                opacity=opacity,
                ref=sub_dict.get("ref") if has_ref else None,
                source_args=_build_sub_source_args(sub_dict),
            )
        )

    return result


def _validate_opacity(
    path: str, layer_id: str, idx: int, opacity: float | dict
) -> float | dict[int, float]:
    """Validate and return a normalized opacity value.

    Accepts a float (0.0–1.0) or a dict of {zoom_level: float}.
    """
    if isinstance(opacity, (int, float)):
        val = float(opacity)
        if val < 0.0 or val > 1.0:
            raise ValueError(
                f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                f"'opacity' must be between 0.0 and 1.0, got {val}"
            )
        return val

    if isinstance(opacity, dict):
        result: dict[int, float] = {}
        for k, v in opacity.items():
            zoom = int(k)
            val = float(v)
            if val < 0.0 or val > 1.0:
                raise ValueError(
                    f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
                    f"'opacity' value for zoom {zoom} must be between "
                    f"0.0 and 1.0, got {val}"
                )
            result[zoom] = val
        return result

    raise ValueError(
        f"{path}: Layer '{layer_id}' sub-layer [{idx}] "
        f"'opacity' must be a float or a dict, got {type(opacity).__name__}"
    )


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

    For composite layers, validates that each inline sub-layer's source
    references a loaded source. Ref sub-layers are validated separately
    by resolve_sub_layer_refs().

    Args:
        layers: Dictionary of LayerConfig instances
        sources: Dictionary of SourceConfig instances

    Raises:
        ValueError: If any layer references an undefined source
    """
    unresolved = []
    for layer_id, layer_config in layers.items():
        # Composite layers: validate inline sub-layer sources
        if layer_config.is_composite():
            for idx, sub in enumerate(layer_config.layers or []):
                if sub.ref is None and sub.source and sub.source not in sources:
                    unresolved.append((f"{layer_id}[{idx}]", sub.source))
        elif layer_config.source and layer_config.source not in sources:
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


def resolve_sub_layer_refs(
    layers: dict[str, LayerConfig],
) -> None:
    """Resolve ref sub-layers by merging referenced layer fields.

    For each composite layer, resolves sub-layers that use `ref` by looking
    up the referenced top-level layer and merging its fields with the
    sub-layer's overrides. Modifies the layers dict in-place.

    Args:
        layers: Dictionary of LayerConfig instances

    Raises:
        ValueError: If a ref points to a non-existent or composite layer
    """
    for layer_id, layer_config in layers.items():
        if not layer_config.is_composite():
            continue

        resolved_subs: list[CompositeSubLayer] = []
        for idx, sub in enumerate(layer_config.layers or []):
            if sub.ref is None:
                resolved_subs.append(sub)
                continue

            # Look up referenced layer
            if sub.ref not in layers:
                raise ValueError(
                    f"Layer '{layer_id}' sub-layer [{idx}] references "
                    f"undefined layer '{sub.ref}'"
                )

            ref_layer = layers[sub.ref]

            # Prevent composite-to-composite refs
            if ref_layer.is_composite():
                raise ValueError(
                    f"Layer '{layer_id}' sub-layer [{idx}] references "
                    f"composite layer '{sub.ref}' (not supported)"
                )

            # Merge: sub-layer source_args override ref layer source_args
            merged = CompositeSubLayer(
                name=sub.name or ref_layer.name,
                source=sub.source or ref_layer.source,
                zoom_levels=sub.zoom_levels
                if sub.zoom_levels
                else list(ref_layer.zoom_levels),
                opacity=sub.opacity,
                ref=None,  # Resolved — no longer a ref
                source_args={**ref_layer.source_args, **sub.source_args},
            )
            resolved_subs.append(merged)

        layer_config.layers = resolved_subs


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

    # Resolve sub-layer refs (must happen before source validation)
    if merged_layers:
        resolve_sub_layer_refs(merged_layers)

    # Resolve source references
    if merged_layers:
        resolve_references(merged_layers, merged_sources)

    return Config(sources=merged_sources, layers=merged_layers, bounds=merged_bounds)
