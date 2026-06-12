"""WMTS Capabilities XML parser.

Parses a WMTS GetCapabilities document and extracts layer metadata,
TileMatrixSet definitions, and ResourceURL templates.
Uses stdlib xml.etree.ElementTree — no external dependencies.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# XML namespaces used in WMTS Capabilities documents
NS_WMTS = "{http://www.opengis.net/wmts/1.0}"
NS_OWS = "{http://www.opengis.net/ows/1.1}"


@dataclass
class TileMatrix:
    """A single tile matrix (one zoom level within a TileMatrixSet)."""

    identifier: str
    scale_denominator: float
    top_left_x: float
    top_left_y: float
    tile_width: int
    tile_height: int
    matrix_width: int
    matrix_height: int


@dataclass
class TileMatrixSet:
    """A WMTS TileMatrixSet — defines the tiling grid for a CRS."""

    identifier: str
    supported_crs: str
    tile_matrices: list[TileMatrix] = field(default_factory=list)

    @property
    def epsg_code(self) -> str | None:
        """Extract EPSG code from CRS URN (e.g. 'urn:ogc:def:crs:EPSG::3857' -> '3857')."""
        crs = self.supported_crs
        if "EPSG" not in crs:
            return None
        # Handle both urn:ogc:def:crs:EPSG::3857 and urn:ogc:def:crs:EPSG:6.18.3:3857
        parts = crs.split("EPSG")
        code_part = parts[-1].lstrip(":")
        # Take the last numeric segment
        for segment in reversed(code_part.split(":")):
            if segment.isdigit():
                return segment
        return None


@dataclass
class ResourceUrl:
    """A RESTful ResourceURL template for a layer+TMS+format combination."""

    format: str
    template: str
    resource_type: str = "tile"


@dataclass
class WmtsLayer:
    """A WMTS layer from the Capabilities document."""

    identifier: str
    title: str
    bounding_box: tuple[float, float, float, float] | None = (
        None  # (min_lon, min_lat, max_lon, max_lat)
    )
    tile_matrix_set_ids: list[str] = field(default_factory=list)
    resource_urls: list[ResourceUrl] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    dimensions: dict[str, str] = field(
        default_factory=dict
    )  # dimension_id -> default_value


@dataclass
class WmtsCapabilities:
    """Parsed WMTS GetCapabilities document."""

    layers: list[WmtsLayer] = field(default_factory=list)
    tile_matrix_sets: list[TileMatrixSet] = field(default_factory=list)

    def get_layer(self, layer_id: str) -> WmtsLayer | None:
        """Find a layer by its identifier."""
        for layer in self.layers:
            if layer.identifier == layer_id:
                return layer
        return None

    def get_tile_matrix_set(self, tms_id: str) -> TileMatrixSet | None:
        """Find a TileMatrixSet by its identifier."""
        for tms in self.tile_matrix_sets:
            if tms.identifier == tms_id:
                return tms
        return None

    def get_tms_by_crs(self, crs: str) -> list[TileMatrixSet]:
        """Find all TileMatrixSets matching a CRS (by full URN or EPSG code)."""
        results = []
        for tms in self.tile_matrix_sets:
            if crs in tms.supported_crs:
                results.append(tms)
            elif tms.epsg_code == crs:
                results.append(tms)
        return results

    def resolve_layer(
        self,
        layer_id: str,
        tms_id: str | None = None,
        tile_format: str | None = None,
    ) -> tuple[WmtsLayer, TileMatrixSet, ResourceUrl]:
        """Resolve a layer to a specific TileMatrixSet and ResourceURL.

        Args:
            layer_id: Layer identifier.
            tms_id: TileMatrixSet identifier (optional, defaults to first linked TMS).
            tile_format: Desired tile format, e.g. 'image/jpeg' (optional).

        Returns:
            Tuple of (layer, tile_matrix_set, resource_url).

        Raises:
            ValueError: If layer not found, TMS not found, or no matching ResourceURL.
        """
        layer = self.get_layer(layer_id)
        if layer is None:
            available = ", ".join(lyr.identifier for lyr in self.layers[:10])
            raise ValueError(
                f"Layer '{layer_id}' not found in Capabilities. "
                f"Available layers (first 10): {available}"
            )

        # Resolve TMS
        if tms_id:
            tms = self.get_tile_matrix_set(tms_id)
            if tms is None:
                available = ", ".join(t.identifier for t in self.tile_matrix_sets)
                raise ValueError(
                    f"TileMatrixSet '{tms_id}' not found. Available: {available}"
                )
        else:
            # Use first linked TMS, prefer 3857 if available
            if not layer.tile_matrix_set_ids:
                raise ValueError(f"Layer '{layer_id}' has no TileMatrixSet links")
            preferred = None
            for linked_id in layer.tile_matrix_set_ids:
                candidate = self.get_tile_matrix_set(linked_id)
                if candidate and candidate.epsg_code == "3857":
                    preferred = candidate
                    break
            tms = preferred or self.get_tile_matrix_set(layer.tile_matrix_set_ids[0])
            if tms is None:
                raise ValueError(
                    f"TileMatrixSet '{layer.tile_matrix_set_ids[0]}' not found in Capabilities"
                )

        # Resolve ResourceURL
        resource_url = _find_resource_url(layer, tms.identifier, tile_format)
        return layer, tms, resource_url

    def layer_ids(self) -> list[str]:
        """Return all layer identifiers."""
        return [lyr.identifier for lyr in self.layers]


def _find_resource_url(
    layer: WmtsLayer,
    tms_id: str,
    tile_format: str | None = None,
) -> ResourceUrl:
    """Find the best ResourceURL for a layer+TMS combination."""
    candidates = layer.resource_urls

    # Filter by format if specified
    if tile_format:
        format_candidates = [r for r in candidates if r.format == tile_format]
        if format_candidates:
            candidates = format_candidates

    if not candidates:
        raise ValueError(
            f"No ResourceURL found for layer '{layer.identifier}'"
            + (f" with format '{tile_format}'" if tile_format else "")
        )

    # Prefer ResourceURLs that reference the TMS in their template
    for rurl in candidates:
        if tms_id in rurl.template:
            return rurl

    # Fall back to first available
    return candidates[0]


def parse_capabilities(xml_text: str) -> WmtsCapabilities:
    """Parse a WMTS GetCapabilities XML document.

    Args:
        xml_text: Raw XML string of the Capabilities document.

    Returns:
        Parsed WmtsCapabilities.

    Raises:
        ValueError: If the XML is malformed or missing required elements.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML in Capabilities document: {e}") from e

    contents = root.find(f"{NS_WMTS}Contents")
    if contents is None:
        raise ValueError("Capabilities document missing <Contents> element")

    # Parse TileMatrixSets first
    tile_matrix_sets = []
    for tms_el in contents.findall(f"{NS_WMTS}TileMatrixSet"):
        tms = _parse_tile_matrix_set(tms_el)
        if tms is not None:
            tile_matrix_sets.append(tms)

    # Parse Layers
    layers = []
    for layer_el in contents.findall(f"{NS_WMTS}Layer"):
        layer = _parse_layer(layer_el)
        if layer is not None:
            layers.append(layer)

    logger.info(
        "Parsed WMTS Capabilities: %d layers, %d TileMatrixSets",
        len(layers),
        len(tile_matrix_sets),
    )

    return WmtsCapabilities(
        layers=layers,
        tile_matrix_sets=tile_matrix_sets,
    )


def _parse_tile_matrix_set(tms_el: ET.Element) -> TileMatrixSet | None:
    """Parse a <TileMatrixSet> element."""
    ident_el = tms_el.find(f"{NS_OWS}Identifier")
    crs_el = tms_el.find(f"{NS_OWS}SupportedCRS")

    if ident_el is None:
        logger.warning("TileMatrixSet missing Identifier, skipping")
        return None

    identifier = ident_el.text or ""
    crs_text = crs_el.text if crs_el is not None else ""
    supported_crs = crs_text if crs_text is not None else ""

    tile_matrices = []
    for tm_el in tms_el.findall(f"{NS_WMTS}TileMatrix"):
        tm = _parse_tile_matrix(tm_el)
        if tm is not None:
            tile_matrices.append(tm)

    # Sort by scale denominator (largest first = lowest zoom)
    tile_matrices.sort(key=lambda t: t.scale_denominator, reverse=True)

    return TileMatrixSet(
        identifier=identifier,
        supported_crs=supported_crs,
        tile_matrices=tile_matrices,
    )


def _parse_tile_matrix(tm_el: ET.Element) -> TileMatrix | None:
    """Parse a <TileMatrix> element."""
    ident_el = tm_el.find(f"{NS_OWS}Identifier")
    scale_el = tm_el.find(f"{NS_WMTS}ScaleDenominator")
    origin_el = tm_el.find(f"{NS_WMTS}TopLeftCorner")
    tw_el = tm_el.find(f"{NS_WMTS}TileWidth")
    th_el = tm_el.find(f"{NS_WMTS}TileHeight")
    mw_el = tm_el.find(f"{NS_WMTS}MatrixWidth")
    mh_el = tm_el.find(f"{NS_WMTS}MatrixHeight")

    if ident_el is None or scale_el is None or origin_el is None:
        logger.warning("TileMatrix missing required fields, skipping")
        return None

    try:
        origin_text = origin_el.text or ""
        origin_parts = origin_text.strip().split()
        top_left_x = float(origin_parts[0])
        top_left_y = float(origin_parts[1])
    except (ValueError, IndexError):
        logger.warning("Invalid TopLeftCorner: %s", origin_el.text)
        return None

    return TileMatrix(
        identifier=ident_el.text or "",
        scale_denominator=float(scale_el.text or "0"),
        top_left_x=top_left_x,
        top_left_y=top_left_y,
        tile_width=int(tw_el.text or "256") if tw_el is not None else 256,
        tile_height=int(th_el.text or "256") if th_el is not None else 256,
        matrix_width=int(mw_el.text or "0") if mw_el is not None else 0,
        matrix_height=int(mh_el.text or "0") if mh_el is not None else 0,
    )


def _parse_layer(layer_el: ET.Element) -> WmtsLayer | None:
    """Parse a <Layer> element."""
    ident_el = layer_el.find(f"{NS_OWS}Identifier")
    title_el = layer_el.find(f"{NS_OWS}Title")

    if ident_el is None:
        logger.warning("Layer missing Identifier, skipping")
        return None

    identifier = ident_el.text or ""
    title_text = title_el.text if title_el is not None else None
    title = title_text if title_text is not None else identifier

    # Parse bounding box
    bbox = _parse_bbox(layer_el)

    # Parse TileMatrixSetLinks
    tms_ids = []
    for tmsl_el in layer_el.findall(f"{NS_WMTS}TileMatrixSetLink"):
        tms_id_el = tmsl_el.find(f"{NS_WMTS}TileMatrixSet")
        if tms_id_el is not None and tms_id_el.text:
            tms_ids.append(tms_id_el.text)

    # Parse ResourceURLs
    resource_urls = []
    for rurl_el in layer_el.findall(f"{NS_WMTS}ResourceURL"):
        resource_urls.append(
            ResourceUrl(
                format=rurl_el.get("format", ""),
                template=rurl_el.get("template", ""),
                resource_type=rurl_el.get("resourceType", "tile"),
            )
        )

    # Parse formats
    formats = []
    for fmt_el in layer_el.findall(f"{NS_WMTS}Format"):
        if fmt_el.text:
            formats.append(fmt_el.text)

    # Parse dimensions (e.g. Time)
    dimensions = {}
    for dim_el in layer_el.findall(f"{NS_WMTS}Dimension"):
        dim_id_el = dim_el.find(f"{NS_OWS}Identifier")
        default_el = dim_el.find(f"{NS_WMTS}Default")
        if dim_id_el is not None and dim_id_el.text:
            default_val = (default_el.text if default_el is not None else "") or ""
            dimensions[dim_id_el.text] = default_val

    return WmtsLayer(
        identifier=identifier,
        title=title,
        bounding_box=bbox,
        tile_matrix_set_ids=tms_ids,
        resource_urls=resource_urls,
        formats=formats,
        dimensions=dimensions,
    )


def _parse_bbox(layer_el: ET.Element) -> tuple[float, float, float, float] | None:
    """Parse WGS84BoundingBox from a Layer element."""
    bbox_el = layer_el.find(f"{NS_OWS}WGS84BoundingBox")
    if bbox_el is None:
        return None

    lower = bbox_el.find(f"{NS_OWS}LowerCorner")
    upper = bbox_el.find(f"{NS_OWS}UpperCorner")

    if lower is None or upper is None:
        return None

    try:
        lower_parts = (lower.text or "").strip().split()
        upper_parts = (upper.text or "").strip().split()
        min_lon, min_lat = float(lower_parts[0]), float(lower_parts[1])
        max_lon, max_lat = float(upper_parts[0]), float(upper_parts[1])
        return (min_lon, min_lat, max_lon, max_lat)
    except (ValueError, IndexError):
        return None


def resource_url_to_template(
    template: str, dimensions: dict[str, str] | None = None
) -> str:
    """Convert a WMTS ResourceURL template to cartoload's internal format.

    Maps WMTS template variables to cartoload's ${var} syntax:
      {TileMatrix}  -> ${z}
      {TileCol}     -> ${x}
      {TileRow}     -> ${y}
      {Style}       -> resolved to default style value
      {Time}        -> resolved to default or 'current'
      {TileMatrixSet} -> kept as-is (resolved from TMS id)

    Args:
        template: The ResourceURL template from Capabilities.
        dimensions: Dimension defaults from the layer (e.g. {'Time': 'current'}).

    Returns:
        Template string using cartoload's ${var} syntax.
    """
    dims = dimensions or {}

    result = template
    result = result.replace("{TileMatrix}", "${z}")
    result = result.replace("{TileCol}", "${x}")
    result = result.replace("{TileRow}", "${y}")

    # Resolve dimension placeholders
    for dim_name, default_val in dims.items():
        result = result.replace(f"{{{dim_name}}}", default_val)

    return result
