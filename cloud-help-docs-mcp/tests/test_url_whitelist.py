"""Tests for URL whitelist validation (no network)."""

from __future__ import annotations

import pytest

from mcp_servers.cloud_help_docs.core.url_whitelist import (
    UrlWhitelistError,
    is_url_allowed,
    validate_url,
)

ALIYUN = ["help.aliyun.com", "www.alibabacloud.com/help"]


def test_host_only_rule_allows_any_path() -> None:
    validate_url("https://help.aliyun.com/zh/ecs/overview", ALIYUN)
    assert is_url_allowed("https://help.aliyun.com/", ALIYUN)


def test_path_prefix_rule_matches_prefix_only() -> None:
    assert is_url_allowed("https://www.alibabacloud.com/help/en/ecs", ALIYUN)
    # Same host but outside the /help prefix is rejected.
    assert not is_url_allowed("https://www.alibabacloud.com/product/ecs", ALIYUN)


def test_rejects_non_https_scheme() -> None:
    with pytest.raises(UrlWhitelistError):
        validate_url("http://help.aliyun.com/x", ALIYUN)


def test_rejects_non_standard_port() -> None:
    with pytest.raises(UrlWhitelistError):
        validate_url("https://help.aliyun.com:8443/x", ALIYUN)
    # Explicit 443 is fine.
    validate_url("https://help.aliyun.com:443/x", ALIYUN)


def test_rejects_unknown_host_and_subdomain() -> None:
    assert not is_url_allowed("https://evil.com/help", ALIYUN)
    # Exact host match: subdomains are NOT implicitly allowed.
    assert not is_url_allowed("https://docs.help.aliyun.com/x", ALIYUN)


def test_empty_url_rejected() -> None:
    with pytest.raises(UrlWhitelistError):
        validate_url("", ALIYUN)
