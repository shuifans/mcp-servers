"""URL whitelist validation.

The MCP server may only fetch documentation from a curated set of domains
defined per provider. Each provider supplies its own whitelist entries.

Rules:
- Only ``https://`` is allowed.
- Non-standard ports are rejected.
- Whitelist entries can be host-only (``help.aliyun.com``) or
  ``host/path-prefix`` (``www.alibabacloud.com/help``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit


class UrlWhitelistError(ValueError):
    """Raised when a URL fails whitelist validation."""

    def __init__(self, message: str, allowed_domains: list[str]):
        super().__init__(message)
        self.message = message
        self.allowed_domains = allowed_domains

    def to_error_payload(self) -> dict[str, object]:
        return {
            "error": "url_not_allowed",
            "message": self.message,
            "allowed_domains": list(self.allowed_domains),
        }


@dataclass(frozen=True)
class _Rule:
    """A single whitelist rule.

    ``host`` is matched case-insensitively (exact match, no implicit subdomain).
    ``path_prefix`` is optional and, if set, the request path must start with it.
    """

    host: str
    path_prefix: str | None = None

    @classmethod
    def parse(cls, raw: str) -> _Rule | None:
        raw = raw.strip().lower()
        if not raw:
            return None
        if "/" in raw:
            host, _, prefix = raw.partition("/")
            host = host.strip()
            prefix = "/" + prefix.strip().lstrip("/")
            return cls(host=host, path_prefix=prefix)
        return cls(host=raw, path_prefix=None)

    def matches(self, host: str, path: str) -> bool:
        if host != self.host:
            return False
        if self.path_prefix is None:
            return True
        normalized_path = path or "/"
        prefix = self.path_prefix.rstrip("/") or "/"
        return (
            normalized_path == prefix
            or normalized_path.startswith(prefix + "/")
            or normalized_path.startswith(self.path_prefix)
        )


def _load_rules(whitelist: Iterable[str]) -> list[_Rule]:
    rules: list[_Rule] = []
    for raw in whitelist:
        rule = _Rule.parse(raw)
        if rule is not None:
            rules.append(rule)
    return rules


def _allowed_domains_view(rules: list[_Rule]) -> list[str]:
    domains: list[str] = []
    for r in rules:
        if r.path_prefix:
            domains.append(f"{r.host}{r.path_prefix}")
        else:
            domains.append(r.host)
    return domains


def validate_url(url: str, whitelist: Iterable[str]) -> None:
    """Validate ``url`` against the whitelist.

    Raises :class:`UrlWhitelistError` if the URL is not allowed.
    """

    rules = _load_rules(whitelist)
    allowed_domains = _allowed_domains_view(rules)

    if not isinstance(url, str) or not url:
        raise UrlWhitelistError("url must be a non-empty string", allowed_domains)

    parsed = urlsplit(url)

    if parsed.scheme.lower() != "https":
        raise UrlWhitelistError(
            f"only https scheme is allowed, got '{parsed.scheme or '<empty>'}'",
            allowed_domains,
        )

    host = (parsed.hostname or "").lower()
    if not host:
        raise UrlWhitelistError("url has no host component", allowed_domains)

    # Reject non-standard ports.
    if parsed.port is not None and parsed.port != 443:
        raise UrlWhitelistError(
            f"non-standard port {parsed.port} is not allowed",
            allowed_domains,
        )

    path = parsed.path or "/"

    for rule in rules:
        if rule.matches(host, path):
            return

    raise UrlWhitelistError(
        f"url host '{host}' (path '{path}') is not in the whitelist",
        allowed_domains,
    )


def is_url_allowed(url: str, whitelist: Iterable[str]) -> bool:
    """Return True iff ``url`` passes whitelist validation."""

    try:
        validate_url(url, whitelist)
        return True
    except UrlWhitelistError:
        return False
