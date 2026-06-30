"""Tests for IQS payload extraction helpers (no network)."""

from __future__ import annotations

from mcp_servers.cloud_help_docs.core.iqs_client import IQSClient


def test_extract_search_results_from_pageitems() -> None:
    data = {"pageItems": [{"url": "https://a"}, {"url": "https://b"}, "junk"]}
    out = IQSClient._extract_search_results(data)
    assert out == [{"url": "https://a"}, {"url": "https://b"}]


def test_extract_search_results_from_bare_list() -> None:
    assert IQSClient._extract_search_results([{"x": 1}]) == [{"x": 1}]


def test_extract_search_results_handles_garbage() -> None:
    assert IQSClient._extract_search_results(None) == []
    assert IQSClient._extract_search_results("nope") == []


def test_extract_page_unwraps_nested_data() -> None:
    data = {"data": {"content": "hello", "title": "T", "url": "https://u"}}
    page = IQSClient._extract_page(data, url="https://fallback", default_format="markdown")
    assert page == {
        "url": "https://u",
        "title": "T",
        "content": "hello",
        "content_format": "markdown",
    }


def test_extract_page_falls_back_on_non_dict() -> None:
    page = IQSClient._extract_page(None, url="https://u", default_format="text")
    assert page["url"] == "https://u"
    assert page["content"] == ""
    assert page["content_format"] == "text"
