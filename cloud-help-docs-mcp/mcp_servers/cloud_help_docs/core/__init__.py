"""Core building blocks for the cloud help docs MCP server.

Submodules:

- :mod:`url_whitelist`: URL whitelist validation.
- :mod:`cache`: SQLite-backed doc cache.
- :mod:`iqs_client`: HTTP client for IQS API.
- :mod:`evidence`: ``Evidence`` object construction.
"""

from .cache import DocCache
from .evidence import Evidence, EvidenceBuilder
from .iqs_client import IQSClient, IQSError
from .url_whitelist import UrlWhitelistError, is_url_allowed, validate_url

__all__ = [
    "DocCache",
    "Evidence",
    "EvidenceBuilder",
    "IQSClient",
    "IQSError",
    "UrlWhitelistError",
    "is_url_allowed",
    "validate_url",
]
