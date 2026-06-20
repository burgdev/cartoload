"""Style engine: unified API for resolving vector feature styles.

Loads rules from inline YAML definitions or QGIS QML files, then resolves
the appropriate LineStyle for a feature at a given zoom level.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cartoload.style.match import Wildcard, evaluate
from cartoload.style.model import (
    GarminStyle,
    LineStyle,
    StyleRule,
    resolve_style_for_zoom,
)
from cartoload.style.qml_parser import parse_qml
from cartoload.style.yaml_parser import parse_yaml_rules

logger = logging.getLogger(__name__)


class StyleEngine:
    """Resolves visual styles for vector features.

    Loads rules from inline YAML definitions (``rules``) or a QGIS QML
    file (``style``).  Inline rules take precedence over QML.
    """

    def __init__(
        self,
        rules: list[StyleRule] | None = None,
    ) -> None:
        self.rules: list[StyleRule] = rules or []

    @classmethod
    def from_config(
        cls,
        layer_config: Any,
        config_dir: str | None = None,
    ) -> "StyleEngine":
        """Create a StyleEngine from a LayerConfig.

        If ``layer_config.rules`` is set, it takes precedence.
        Otherwise, if ``layer_config.style`` is set, parse the QML file.

        Args:
            layer_config: Layer configuration object.
            config_dir: Directory of the config file, for resolving relative
                paths (e.g. QML style files).
        """
        rules: list[StyleRule] = []

        # Inline rules take precedence
        if layer_config.rules:
            rules = parse_yaml_rules(layer_config.rules)
            if layer_config.style:
                logger.info(
                    "Layer '%s': inline rules override QML file '%s'",
                    layer_config.id,
                    layer_config.style,
                )
        elif layer_config.style:
            style_path = Path(layer_config.style)
            if not style_path.is_absolute() and config_dir:
                style_path = Path(config_dir) / style_path
            if style_path.exists():
                rules = parse_qml(style_path)
                logger.info(
                    "Loaded %d rules from QML '%s'",
                    len(rules),
                    style_path,
                )
            else:
                logger.warning("QML file not found: %s", style_path)

        # Apply garmin_types mapping if present (for QML-based configs)
        if layer_config.garmin_types and rules:
            _apply_garmin_types(rules, layer_config.garmin_types)

        return cls(rules=rules)

    def resolve(
        self,
        feature_attrs: dict[str, Any],
        zoom: int,
    ) -> LineStyle | None:
        """Find the first matching style for a feature at a given zoom.

        Args:
            feature_attrs: Feature attributes as a dict.
            zoom: The zoom level to resolve for.

        Returns:
            A LineStyle if a matching rule is found, or None.
        """
        for rule in self.rules:
            if evaluate(rule.match, feature_attrs):
                return resolve_style_for_zoom(rule, zoom)
        return None


def _apply_garmin_types(rules: list[StyleRule], garmin_types: dict[str, dict]) -> None:
    """Attach GarminStyle to rules that match category values.

    For QML-based configs, garmin_types maps category values to
    Garmin type codes.  We look for ExactMatch rules whose tag value
    matches a garmin_types key.
    """
    from cartoload.style.match import ExactMatch

    for rule in rules:
        if rule.garmin is not None:
            continue  # already has Garmin mapping

        if isinstance(rule.match, ExactMatch):
            value = rule.match.value
            if value in garmin_types:
                gt = garmin_types[value]
                type_str = str(gt.get("type", "0x00"))
                if type_str.startswith(("0x", "0X")):
                    type_code = int(type_str, 16)
                else:
                    type_code = int(type_str)
                res = gt.get("resolution", [16, 24])
                rule.garmin = GarminStyle(
                    type_code=type_code,
                    resolution=(int(res[0]), int(res[1])),
                )
        elif isinstance(rule.match, Wildcard):
            # Catch-all rule — check if there's a wildcard mapping
            if "*" in garmin_types:
                gt = garmin_types["*"]
                type_str = str(gt.get("type", "0x00"))
                if type_str.startswith(("0x", "0X")):
                    type_code = int(type_str, 16)
                else:
                    type_code = int(type_str)
                res = gt.get("resolution", [16, 24])
                rule.garmin = GarminStyle(
                    type_code=type_code,
                    resolution=(int(res[0]), int(res[1])),
                )
