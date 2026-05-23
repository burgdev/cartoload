"""Shared STAC collection query logic.

Provides a common function for querying STAC collection endpoints
with bbox filtering and spatial overlap checks, used by both
STACDownloader (GeoTIFF) and GPKGDownloader.
"""

from __future__ import annotations

import logging
from typing import Callable

import requests

logger = logging.getLogger(__name__)


def query_stac_collection(
    collection_url: str,
    bbox: list[float],
    asset_finder: Callable[[dict, dict[str, str] | None], str | None],
    asset_filter: dict[str, str] | None = None,
    *,
    collection_id: str = "",
    asset_label: str = "asset",
) -> list[tuple[str, str, int | None]]:
    """Query a STAC collection for items matching a bounding box.

    Fetches items from the ``/items`` sub-endpoint with a bbox filter,
    performs client-side spatial overlap checks, and applies the given
    asset finder to extract the relevant asset URL from each item.

    Args:
        collection_url: STAC collection endpoint URL.
        bbox: Bounding box as ``[west, south, east, north]``.
        asset_finder: Callable that takes ``(assets_dict, asset_filter)``
            and returns the asset href or ``None``.
        asset_filter: Optional key-value pairs to match against asset
            properties.
        collection_id: Collection identifier (used for logging).
        asset_label: Label for the asset type in log messages
            (e.g. ``"GeoTIFF"``, ``"GPKG"``).

    Returns:
        List of tuples: ``(item_id, asset_url, expected_size_bytes)``
    """
    items_url = collection_url.rstrip("/") + "/items"
    params: dict[str, str] = {
        "bbox": ",".join(str(v) for v in bbox),
        "limit": "500",
    }

    try:
        response = requests.get(items_url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception(f"Failed to query STAC items at {items_url}: {e}") from e

    data = response.json()
    features = data.get("features", [])

    if not features:
        return []

    results: list[tuple[str, str, int | None]] = []
    for feature in features:
        item_id = feature.get("id", "unknown")
        assets = feature.get("assets", {})

        # Client-side bbox filter: skip items whose footprint doesn't
        # overlap the requested bbox.
        item_bbox = feature.get("bbox")
        if item_bbox and len(item_bbox) == 4:
            if (
                item_bbox[2] < bbox[0]  # item east < query west
                or item_bbox[0] > bbox[2]  # item west > query east
                or item_bbox[3] < bbox[1]  # item north < query south
                or item_bbox[1] > bbox[3]  # item south > query north
            ):
                logger.debug(
                    "STAC item '%s' (bbox %s) does not overlap query bbox, skipping",
                    item_id,
                    item_bbox,
                )
                continue

        asset_url = asset_finder(assets, asset_filter)
        if asset_url is None:
            if asset_filter:
                logger.warning(
                    "No %s asset matching filter %s in STAC item '%s', skipping",
                    asset_label,
                    asset_filter,
                    item_id,
                )
            else:
                logger.warning(
                    "No %s asset found in STAC item '%s', skipping",
                    asset_label,
                    item_id,
                )
            continue

        results.append((item_id, asset_url, None))

    return results
