"""Tests for search-result normalization and score extraction (no network)."""

from __future__ import annotations

from mcp_servers.cloud_help_docs.tools.search import (
    _extract_score,
    _normalize_result,
    _preprocess_query,
)


def test_score_from_common_aliases() -> None:
    assert _extract_score({"score": 0.5}) == 0.5
    assert _extract_score({"rerankScore": 0.91}) == 0.91
    assert _extract_score({"relevanceScore": 0.3}) == 0.3
    assert _extract_score({"scoreInfo": {"rerankScore": 0.77}}) == 0.77
    assert _extract_score({"score": "0.42"}) == 0.42
    assert _extract_score({}) is None
    # bools must not be coerced to 0.0/1.0
    assert _extract_score({"score": True}) is None


def test_normalize_result_uses_field_aliases() -> None:
    item = {"link": "https://x", "name": "Title", "mainText": "snippet", "rerankScore": 0.8}
    out = _normalize_result(item)
    assert out == {
        "url": "https://x",
        "title": "Title",
        "snippet": "snippet",
        "score": 0.8,
    }


def test_preprocess_query_prepends_site_and_product() -> None:
    q = _preprocess_query("launch instance", "ECS", "help.aliyun.com")
    assert q == "site:help.aliyun.com ECS launch instance"
