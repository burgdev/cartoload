"""Human-readable cache key derivation from URL templates."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse, quote

logger = logging.getLogger(__name__)

# Per-tile template variables to strip (both ${VAR} and $VAR forms)
_TILE_VARS = ["x", "y", "z", "zoom"]
_TILE_VAR_PATTERN = re.compile(
    "|".join(r"\$?\{" + v + r"\}|\$" + v for v in _TILE_VARS)
)

_MAX_KEY_LENGTH = 200


def _is_old_hash(name: str) -> bool:
    """Check if a directory name looks like an old 12-char hex hash key."""
    return len(name) == 12 and all(c in "0123456789abcdef" for c in name)


def url_to_cache_key(url: str, extra: str = "") -> str:
    """Derive a human-readable, filesystem-safe cache key from a URL.

    Algorithm:
      1. Strip scheme and host
      2. Remove per-tile template variables (${x}, ${y}, ${z}, ${zoom}, $x, etc.)
      3. Split on '/', remove empty segments, strip leading/trailing '.' from each
      4. Append 'extra' string if provided
      5. Join segments with '-'
      6. Replace '?' with '-', '=' and '&' with '_'
      7. urllib.parse.quote(safe="-_.") for filesystem safety

    Truncate to 200 chars.
    """
    # 1. Strip scheme and host
    parsed = urlparse(url)
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"

    # 2. Remove per-tile template variables
    path = _TILE_VAR_PATTERN.sub("", path)

    # 3. Split on '/', remove empty, strip leading/trailing '.'
    segments = [s.strip(".") for s in path.split("/") if s]

    # 4. Append extra
    if extra:
        segments.append(extra)

    # 5. Join with '-'
    key = "-".join(segments)

    # 6. Replace query-string characters
    key = key.replace("?", "-").replace("=", "_").replace("&", "_")

    # 7. URL-encode for filesystem safety
    key = quote(key, safe="-_.")

    return key[:_MAX_KEY_LENGTH]


def migrate_cache_key(source_cache_dir: Path, new_key: str) -> None:
    """Auto-migrate old hash-based cache directories to the new format.

    Scans source_cache_dir for 12-char hex directory names and renames
    them to new_key. Skips if new_key already exists.
    """
    if not source_cache_dir.is_dir():
        return

    new_path = source_cache_dir / new_key
    if new_path.exists():
        return

    for entry in source_cache_dir.iterdir():
        if entry.is_dir() and _is_old_hash(entry.name):
            logger.info(
                "Migrating cache directory: %s -> %s",
                entry.name,
                new_key,
            )
            entry.rename(new_path)
            return
