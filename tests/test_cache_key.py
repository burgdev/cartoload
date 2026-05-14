"""Tests for url_to_cache_key and migrate_cache_key."""

from __future__ import annotations

from pathlib import Path

from cartoload.downloader.cache_key import migrate_cache_key, url_to_cache_key


class TestSchemeHostStripping:
    """Step 1: scheme and host are stripped."""

    def test_https_stripped(self) -> None:
        key = url_to_cache_key("https://wmts.example.com/path/to/tiles")
        assert not key.startswith("wmts")
        # Host is stripped, only path remains
        assert "path-to-tiles" in key

    def test_http_stripped(self) -> None:
        key_http = url_to_cache_key("http://wmts.example.com/path")
        key_https = url_to_cache_key("https://wmts.example.com/path")
        # Both produce the same key (host stripped, scheme irrelevant)
        assert key_http == key_https

    def test_no_scheme(self) -> None:
        key = url_to_cache_key("just/a/path")
        assert "just-a-path" in key


class TestVariableRemoval:
    """Step 2: per-tile template variables are removed."""

    def test_dollar_brace_vars_removed(self) -> None:
        key = url_to_cache_key(
            "https://example.com/1.0.0/layer/3857/${z}/${x}/${y}.jpeg"
        )
        assert "z" not in key.split("-")  # variable segments gone
        assert "jpeg" in key

    def test_dollar_no_brace_vars_removed(self) -> None:
        key = url_to_cache_key("https://example.com/$z/$x/$y.png")
        # All variable segments removed, only extension remains
        assert "png" in key

    def test_zoom_var_removed(self) -> None:
        key = url_to_cache_key("https://example.com/${zoom}/${x}/${y}.jpeg")
        assert "jpeg" in key

    def test_bare_vars_removed(self) -> None:
        key = url_to_cache_key("https://example.com/$zoom/$x/$y.png")
        assert "png" in key


class TestSplitAndStrip:
    """Step 3: split on '/', remove empty, strip leading/trailing '.'."""

    def test_empty_segments_removed(self) -> None:
        key = url_to_cache_key("https://example.com/a///b")
        assert key == "a-b"

    def test_leading_dot_stripped(self) -> None:
        key = url_to_cache_key("https://example.com/.jpeg")
        # ".jpeg" -> "jpeg" after strip(".")
        assert "jpeg" in key

    def test_trailing_dot_stripped(self) -> None:
        key = url_to_cache_key("https://example.com/foo.")
        assert key.endswith("foo")

    def test_version_numbers_preserved(self) -> None:
        key = url_to_cache_key("https://example.com/1.0.0/layer")
        assert "1.0.0" in key


class TestExtraParameter:
    """Step 4: extra string is appended."""

    def test_extra_appended(self) -> None:
        key = url_to_cache_key("https://example.com/path", extra="resolution=10m")
        assert "resolution_10m" in key  # = replaced with _

    def test_no_extra(self) -> None:
        key = url_to_cache_key("https://example.com/path")
        assert "resolution" not in key


class TestJoinWithDash:
    """Step 5: segments are joined with '-'."""

    def test_segments_joined(self) -> None:
        key = url_to_cache_key("https://example.com/a/b/c")
        assert key == "a-b-c"


class TestCharReplacement:
    """Step 6: ? → -, = → _, & → _."""

    def test_question_mark_replaced(self) -> None:
        key = url_to_cache_key("https://example.com/path?query=value")
        assert "?" not in key
        assert "-" in key

    def test_equals_replaced(self) -> None:
        key = url_to_cache_key("https://example.com/path?key=value")
        assert "=" not in key
        assert "_" in key

    def test_ampersand_replaced(self) -> None:
        key = url_to_cache_key("https://example.com/path?a=1&b=2")
        assert "&" not in key
        assert "_" in key


class TestUrlEncoding:
    """Step 7: urllib.parse.quote(safe="-_.") for filesystem safety."""

    def test_spaces_encoded(self) -> None:
        key = url_to_cache_key("https://example.com/path with spaces")
        assert " " not in key

    def test_dots_preserved(self) -> None:
        key = url_to_cache_key("https://example.com/1.0.0/layer")
        assert "1.0.0" in key

    def test_dashes_preserved(self) -> None:
        key = url_to_cache_key("https://example.com/my-layer")
        assert "my-layer" in key


class TestDeterminism:
    """Same URL always produces the same key."""

    def test_deterministic(self) -> None:
        url = "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg"
        key1 = url_to_cache_key(url)
        key2 = url_to_cache_key(url)
        assert key1 == key2


class TestTruncation:
    """Keys longer than 200 chars are truncated."""

    def test_long_url_truncated(self) -> None:
        long_path = "/".join(["segment"] * 100)
        url = f"https://example.com/{long_path}"
        key = url_to_cache_key(url)
        assert len(key) <= 200


class TestRealWorldExamples:
    """Test with real-world URL templates from the design doc."""

    def test_swisstopo_pixelkarte(self) -> None:
        url = "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg"
        key = url_to_cache_key(url)
        assert key == "1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg"

    def test_query_style_url(self) -> None:
        url = "https://wxs.ign.fr/geoportail/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=layer&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX=${z}&TILEROW=${y}&TILECOL=${x}"
        key = url_to_cache_key(url)
        # Verify query chars are cleaned
        assert "?" not in key
        assert "=" not in key
        assert "&" not in key
        # Verify key components are present
        assert "geoportail" in key
        assert "SERVICE_WMTS" in key

    def test_stac_collection_url(self) -> None:
        url = "https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe"
        key = url_to_cache_key(url)
        assert key == "api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe"

    def test_stac_with_extra(self) -> None:
        url = "https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe"
        key = url_to_cache_key(url, extra="resolution=10m")
        assert "resolution_10m" in key


class TestMigrateCacheKey:
    """Tests for migrate_cache_key: auto-migration of hash-based dirs."""

    def test_hash_dir_renamed(self, tmp_path: Path) -> None:
        """A 12-char hex directory is renamed to the new key."""
        source_dir = tmp_path / "cache" / "swisstopo"
        hash_dir = source_dir / "a1b2c3d4e5f6"
        hash_dir.mkdir(parents=True)
        (hash_dir / "tile.jpeg").write_bytes(b"data")

        migrate_cache_key(source_dir, "new-readable-key")

        assert not hash_dir.exists()
        new_dir = source_dir / "new-readable-key"
        assert new_dir.exists()
        assert (new_dir / "tile.jpeg").read_bytes() == b"data"

    def test_skip_when_new_exists(self, tmp_path: Path) -> None:
        """If the new key dir already exists, hash dir is left in place."""
        source_dir = tmp_path / "cache" / "swisstopo"
        hash_dir = source_dir / "a1b2c3d4e5f6"
        new_dir = source_dir / "new-key"
        hash_dir.mkdir(parents=True)
        new_dir.mkdir(parents=True)
        (hash_dir / "old_tile.jpeg").write_bytes(b"old")
        (new_dir / "new_tile.jpeg").write_bytes(b"new")

        migrate_cache_key(source_dir, "new-key")

        # Both dirs remain unchanged
        assert hash_dir.exists()
        assert new_dir.exists()
        assert (hash_dir / "old_tile.jpeg").read_bytes() == b"old"
        assert (new_dir / "new_tile.jpeg").read_bytes() == b"new"

    def test_skip_when_no_hash_dirs(self, tmp_path: Path) -> None:
        """Non-hash directories are left untouched."""
        source_dir = tmp_path / "cache" / "swisstopo"
        readable_dir = source_dir / "already-migrated"
        readable_dir.mkdir(parents=True)
        (readable_dir / "tile.jpeg").write_bytes(b"data")

        migrate_cache_key(source_dir, "new-key")

        # No migration — the existing dir stays as-is
        assert readable_dir.exists()
        assert not (source_dir / "new-key").exists()

    def test_nonexistent_source_dir(self, tmp_path: Path) -> None:
        """No error when source_cache_dir doesn't exist."""
        source_dir = tmp_path / "nonexistent"
        # Should not raise
        migrate_cache_key(source_dir, "any-key")

    def test_only_first_hash_dir_migrated(self, tmp_path: Path) -> None:
        """Only the first hash directory found is migrated."""
        source_dir = tmp_path / "cache" / "swisstopo"
        hash1 = source_dir / "aaaa00000000"
        hash2 = source_dir / "bbbb11111111"
        hash1.mkdir(parents=True)
        hash2.mkdir(parents=True)
        (hash1 / "tile1.jpeg").write_bytes(b"1")
        (hash2 / "tile2.jpeg").write_bytes(b"2")

        migrate_cache_key(source_dir, "new-key")

        new_dir = source_dir / "new-key"
        assert new_dir.exists()
        # One of the hash dirs was renamed
        assert (new_dir / "tile1.jpeg").exists() or (new_dir / "tile2.jpeg").exists()
