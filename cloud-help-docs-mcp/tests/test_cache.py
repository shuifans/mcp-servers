"""Tests for the SQLite doc cache (uses a temp file, no network)."""

from __future__ import annotations

from pathlib import Path

from mcp_servers.cloud_help_docs.config import Config
from mcp_servers.cloud_help_docs.core.cache import DocCache, normalize_url


def test_normalize_url_canonicalizes() -> None:
    a = normalize_url("HTTPS://Help.Aliyun.com/ECS/overview/?b=2&a=1#frag")
    b = normalize_url("https://help.aliyun.com/ECS/overview?a=1&b=2")
    assert a == b
    # Root slash is preserved, trailing slash otherwise stripped.
    assert normalize_url("https://help.aliyun.com/") == "https://help.aliyun.com/"


def _cache(tmp_path: Path, **cfg: object) -> DocCache:
    config = Config(**cfg)  # type: ignore[arg-type]
    return DocCache(cache_path=tmp_path / "c.sqlite", config=config)


def test_set_get_roundtrip(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    try:
        cache.set_cached("https://help.aliyun.com/x", "Title", "body content", "markdown")
        entry = cache.get_cached("https://help.aliyun.com/x")
        assert entry is not None
        assert entry["title"] == "Title"
        assert entry["content"] == "body content"
        assert entry["content_length"] == len("body content")
        assert entry["hit_count"] == 1  # incremented on read
    finally:
        cache.close()


def test_expired_entry_is_a_miss(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    try:
        cache.set_cached("https://help.aliyun.com/x", "T", "content", ttl_hours=0)
        assert cache.get_cached("https://help.aliyun.com/x") is None
        assert cache.purge_expired() == 1
    finally:
        cache.close()


def test_lru_eviction_respects_max_entries(tmp_path: Path) -> None:
    cache = _cache(tmp_path, cache_max_entries=2)
    try:
        cache.set_cached("https://help.aliyun.com/1", "1", "a")
        cache.set_cached("https://help.aliyun.com/2", "2", "b")
        cache.set_cached("https://help.aliyun.com/3", "3", "c")
        # Oldest (lowest id) evicted; newest retained; total capped at 2.
        assert cache.get_cached("https://help.aliyun.com/3") is not None
        assert cache.get_cached("https://help.aliyun.com/1") is None
    finally:
        cache.close()
