from __future__ import annotations

import logging
import os
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
    asset_filter: dict[str, str] | None = None

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
    # Style configuration for vector/rasterized layers
    rules: list[dict] | None = None  # Inline style rules (Tier 1/2)
    style: str | None = None  # Path to QML file (Tier 3)
    garmin_types: dict[str, dict] | None = None  # Garmin type mapping for QML rules
    config_dir: str | None = (
        None  # Directory of the config file (for relative path resolution)
    )

    def is_composite(self) -> bool:
        """Return True if this layer is a composite of multiple sub-layers."""
        return self.layers is not None and len(self.layers) > 0


@dataclass
class SettingsConfig:
    """Runtime settings with precedence: CLI flag > env var > config file > default."""

    cache_dir: str | None = None
    output_dir: str | None = None
    executor: str | None = None
    quality: int | None = None
    rate_limit_ms: int | None = None


@dataclass
class Config:
    """Top-level configuration container holding all sources, layers, and settings."""

    sources: dict[str, SourceConfig]
    layers: dict[str, LayerConfig]
    bounds: dict[str, float] | None = None
    settings: SettingsConfig = field(default_factory=SettingsConfig)


# Allowed source types
ALLOWED_SOURCE_TYPES = {"wmts", "stac", "geotiff", "gpkg"}

# Required fields for each source type
SOURCE_TYPE_REQUIRED_FIELDS = {
    "wmts": ["url_template"],
    "stac": ["url_template"],
    "geotiff": ["url_template"],
    "gpkg": ["url_template"],
}

# Supported settings keys and their env var names
SETTINGS_ENV_PREFIX = "CARTOLOAD_"
SETTINGS_KEYS = {"cache_dir", "output_dir", "executor", "quality", "rate_limit_ms"}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal parsers for unified config sections
# ---------------------------------------------------------------------------


def _parse_sources_section(data: dict, path: str) -> dict[str, SourceConfig]:
    """Extract and validate the `sources:` section from a unified YAML dict."""
    if "sources" not in data:
        return {}

    sources_data = data["sources"]
    if sources_data is None:
        return {}
    if not isinstance(sources_data, dict):
        raise ValueError(
            f"{path}: 'sources' must be a dict, got {type(sources_data).__name__}"
        )

    file_path = Path(path)
    sources: dict[str, SourceConfig] = {}
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


def _parse_bounds(bounds_data: dict, path: str, context: str = "") -> dict[str, float]:
    """Validate and return a bounds dict."""
    if not isinstance(bounds_data, dict):
        raise ValueError(f"{path}: {context}'bounds' must be a dict")

    required_bounds_fields = ["west", "east", "south", "north"]
    for bfield in required_bounds_fields:
        if bfield not in bounds_data:
            raise ValueError(
                f"{path}: {context}'bounds' missing required field '{bfield}'"
            )
        if not isinstance(bounds_data[bfield], (int, float)):
            raise ValueError(f"{path}: {context}'bounds.{bfield}' must be numeric")

    if bounds_data["west"] >= bounds_data["east"]:
        raise ValueError(
            f"{path}: {context}'bounds' invalid: west ({bounds_data['west']}) >= east ({bounds_data['east']})"
        )
    if bounds_data["south"] >= bounds_data["north"]:
        raise ValueError(
            f"{path}: {context}'bounds' invalid: south ({bounds_data['south']}) >= north ({bounds_data['north']})"
        )

    return bounds_data


def _parse_layers_section(
    data: dict, path: str
) -> tuple[dict[str, LayerConfig], dict[str, float] | None]:
    """Extract and validate `layers:` and `bounds:` from a unified YAML dict."""
    # Parse file-level bounds even when no layers section exists
    bounds = None
    if "bounds" in data and data["bounds"] is not None:
        bounds = _parse_bounds(data["bounds"], path)

    if "layers" not in data:
        return ({}, bounds)

    layers_data = data["layers"]
    if layers_data is None:
        return ({}, bounds)
    if not isinstance(layers_data, dict):
        raise ValueError(
            f"{path}: 'layers' must be a dict, got {type(layers_data).__name__}"
        )

    # File-level bounds already parsed above

    # Parse layers
    layers: dict[str, LayerConfig] = {}
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
            for req_field in required_layer_fields:
                if (
                    req_field not in layer_dict
                    or layer_dict[req_field] is None
                    or layer_dict[req_field] == ""
                ):
                    raise ValueError(
                        f"{path}: Layer '{layer_id}' missing required field '{req_field}'"
                    )
        else:
            all_required = required_layer_fields + ["source"]
            for req_field in all_required:
                if (
                    req_field not in layer_dict
                    or layer_dict[req_field] is None
                    or layer_dict[req_field] == ""
                ):
                    raise ValueError(
                        f"{path}: Layer '{layer_id}' missing required field '{req_field}'"
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
            layer_bounds = _parse_bounds(
                layer_dict["bounds"], path, context=f"Layer '{layer_id}' "
            )
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

        # Parse style configuration
        rules = layer_dict.get("rules")
        style = layer_dict.get("style")
        garmin_types = layer_dict.get("garmin_types")

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
            rules=rules,
            style=style,
            garmin_types=garmin_types,
            config_dir=str(Path(path).parent.resolve()),
        )

    return (layers, bounds)


def _parse_settings_section(data: dict, path: str) -> SettingsConfig:
    """Extract and validate the `settings:` section from a unified YAML dict."""
    if "settings" not in data:
        return SettingsConfig()

    settings_data = data["settings"]
    if settings_data is None:
        return SettingsConfig()
    if not isinstance(settings_data, dict):
        raise ValueError(
            f"{path}: 'settings' must be a dict, got {type(settings_data).__name__}"
        )

    known = {}
    for key, value in settings_data.items():
        if key not in SETTINGS_KEYS:
            raise ValueError(
                f"{path}: Unknown settings key '{key}'. "
                f"Valid keys: {', '.join(sorted(SETTINGS_KEYS))}"
            )
        if value is not None:
            known[key] = value

    return SettingsConfig(**known)


# ---------------------------------------------------------------------------
# Source / sub-layer field helpers (unchanged)
# ---------------------------------------------------------------------------


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


def _build_sub_source_args(
    sub_dict: dict,
) -> tuple[dict[str, str], dict[str, str] | None]:
    """Build source_args for a sub-layer from its YAML dict.

    Handles both dict-style source (extract args from dict) and
    backward-compat wmts_layer and extension fields.

    Returns:
        Tuple of (source_args, asset_filter or None)
    """
    raw_source = sub_dict.get("source", "")
    _, source_args, asset_filter = _parse_source_field(raw_source)

    # Backward compat: merge wmts_layer into source_args as 'layer'
    wmts_layer = sub_dict.get("wmts_layer")
    if wmts_layer is not None and "layer" not in source_args:
        source_args["layer"] = wmts_layer

    # Backward compat: merge extension into source_args
    extension = sub_dict.get("extension")
    if extension is not None and "extension" not in source_args:
        source_args["extension"] = extension

    return source_args, asset_filter


def _parse_sub_layers(
    path: str, layer_id: str, sub_layers_data: list
) -> list[CompositeSubLayer]:
    """Parse and validate sub-layers from a composite layer config."""
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

        source_args, sub_asset_filter = _build_sub_source_args(sub_dict)

        result.append(
            CompositeSubLayer(
                name=sub_dict.get("name", ""),
                source=_extract_source_id(sub_dict.get("source", "")),
                zoom_levels=zoom_levels,
                opacity=opacity,
                ref=sub_dict.get("ref") if has_ref else None,
                source_args=source_args,
                asset_filter=sub_asset_filter,
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


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def merge_sources(*source_dicts: dict[str, SourceConfig]) -> dict[str, SourceConfig]:
    """Merge multiple source dictionaries with last-file-wins semantics."""
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
    """Merge multiple layer results with last-file-wins semantics."""
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


def merge_settings(*settings_list: SettingsConfig) -> SettingsConfig:
    """Merge multiple SettingsConfig instances with later-wins semantics."""
    merged = SettingsConfig()
    for settings in settings_list:
        for key in SETTINGS_KEYS:
            val = getattr(settings, key, None)
            if val is not None:
                setattr(merged, key, val)
    return merged


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------


def resolve_references(
    layers: dict[str, LayerConfig], sources: dict[str, SourceConfig]
) -> None:
    """Validate that all layer source references point to loaded sources."""
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
    """Resolve ref sub-layers by merging referenced layer fields."""
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


# ---------------------------------------------------------------------------
# Settings resolution with env var support
# ---------------------------------------------------------------------------


def resolve_settings(settings: SettingsConfig) -> dict[str, object]:
    """Resolve settings with precedence: env var > config file.

    Returns a dict of resolved key-value pairs (None values excluded).
    CLI flags are applied on top of this in the CLI layer.

    Resolution order:
    1. CLI flag (applied in cli.py)
    2. Environment variable (CARTOLOAD_<UPPER_SNAKE_KEY>)
    3. Config file settings
    4. Built-in default (handled in cli.py)
    """
    resolved: dict[str, object] = {}

    for key in SETTINGS_KEYS:
        # Config file value
        config_val = getattr(settings, key, None)
        if config_val is not None:
            resolved[key] = config_val

        # Env var overrides config
        env_key = SETTINGS_ENV_PREFIX + key.upper()
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # Type coerce env vars
            if key == "quality":
                resolved[key] = int(env_val)
            elif key == "rate_limit_ms":
                resolved[key] = int(env_val)
            else:
                resolved[key] = env_val

    return resolved


# ---------------------------------------------------------------------------
# Unified config loading
# ---------------------------------------------------------------------------


def _load_unified_file(
    path: str,
    seen: set[Path],
) -> tuple[
    dict[str, SourceConfig],
    dict[str, LayerConfig],
    dict[str, float] | None,
    SettingsConfig,
]:
    """Load a single unified config file, resolving includes recursively.

    Args:
        path: Path to the YAML config file
        seen: Set of resolved file paths already loaded (for cycle detection)

    Returns:
        Tuple of (sources, layers, bounds, settings)

    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If validation fails or circular include detected
    """
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    # Circular include detection
    if file_path in seen:
        raise ValueError(
            f"Circular include detected: '{file_path}' is already being loaded"
        )
    seen.add(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: Expected YAML dict, got {type(data).__name__}")

    # Process includes first (depth-first)
    merged_sources: dict[str, SourceConfig] = {}
    merged_layers: dict[str, LayerConfig] = {}
    merged_bounds: dict[str, float] | None = None
    merged_settings = SettingsConfig()

    includes = data.get("includes")
    if includes:
        if not isinstance(includes, list):
            raise ValueError(
                f"{path}: 'includes' must be a list, got {type(includes).__name__}"
            )
        for include_path in includes:
            if not isinstance(include_path, str):
                raise ValueError(
                    f"{path}: Each include path must be a string, got {type(include_path).__name__}"
                )
            # Resolve relative to the current file's directory
            resolved = (file_path.parent / include_path).resolve()
            inc_sources, inc_layers, inc_bounds, inc_settings = _load_unified_file(
                str(resolved), seen | {file_path}
            )

            # Merge included results
            merged_sources = merge_sources(merged_sources, inc_sources)
            merged_layers_dict, merged_bounds = merge_layers(
                (merged_layers, merged_bounds), (inc_layers, inc_bounds)
            )
            merged_layers = merged_layers_dict
            merged_settings = merge_settings(merged_settings, inc_settings)

    # Parse current file's sections
    cur_sources = _parse_sources_section(data, path)
    cur_layers, cur_bounds = _parse_layers_section(data, path)
    cur_settings = _parse_settings_section(data, path)

    # Merge current file on top of includes
    final_sources = merge_sources(merged_sources, cur_sources)
    final_layers, final_bounds = merge_layers(
        (merged_layers, merged_bounds), (cur_layers, cur_bounds)
    )
    final_settings = merge_settings(merged_settings, cur_settings)

    return (final_sources, final_layers, final_bounds, final_settings)


def load_config(config_paths: list[str]) -> Config:
    """Load and merge config files into a single Config object.

    Each config file uses the unified format with optional sections:
    includes, sources, layers, bounds, settings.

    Args:
        config_paths: List of paths to YAML config files

    Returns:
        Config object containing merged sources, layers, bounds, and settings

    Raises:
        FileNotFoundError: If any config file does not exist
        ValueError: If validation fails
    """
    all_sources: dict[str, SourceConfig] = {}
    all_layers: dict[str, LayerConfig] = {}
    all_bounds: dict[str, float] | None = None
    all_settings = SettingsConfig()

    for path in config_paths:
        sources, layers, bounds, settings = _load_unified_file(path, seen=set())
        all_sources = merge_sources(all_sources, sources)
        all_layers, all_bounds = merge_layers(
            (all_layers, all_bounds), (layers, bounds)
        )
        all_settings = merge_settings(all_settings, settings)

    # Resolve sub-layer refs (must happen before source validation)
    if all_layers:
        resolve_sub_layer_refs(all_layers)

    # Resolve source references
    if all_layers:
        resolve_references(all_layers, all_sources)

    return Config(
        sources=all_sources,
        layers=all_layers,
        bounds=all_bounds,
        settings=all_settings,
    )
