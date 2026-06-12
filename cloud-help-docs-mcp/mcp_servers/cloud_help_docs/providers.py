"""Cloud provider registry.

Each provider defines a :class:`ProviderConfig` with the site filter, URL
whitelist, cache filename and default documentation language used by the
generic tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single cloud documentation provider."""

    name: str
    display_name: str
    site_filter: str
    whitelist: list[str] = field(default_factory=list)
    cache_filename: str = ""
    doc_language: str = "en-US"


PROVIDERS: dict[str, ProviderConfig] = {
    "aliyun": ProviderConfig(
        name="aliyun",
        display_name="Aliyun",
        site_filter="help.aliyun.com",
        whitelist=["help.aliyun.com", "www.alibabacloud.com/help"],
        cache_filename="aliyun_doc_cache.sqlite",
        doc_language="zh-CN",
    ),
    "volcengine": ProviderConfig(
        name="volcengine",
        display_name="Volcengine",
        site_filter="www.volcengine.com",
        whitelist=["www.volcengine.com/docs"],
        cache_filename="volcengine_doc_cache.sqlite",
        doc_language="zh-CN",
    ),
    "tencent_cloud": ProviderConfig(
        name="tencent_cloud",
        display_name="Tencent Cloud",
        site_filter="cloud.tencent.com",
        whitelist=[
            "cloud.tencent.com/document",
            "www.tencentcloud.com/document",
        ],
        cache_filename="tencent_cloud_doc_cache.sqlite",
        doc_language="zh-CN",
    ),
    "aws": ProviderConfig(
        name="aws",
        display_name="AWS",
        site_filter="docs.aws.amazon.com",
        whitelist=["docs.aws.amazon.com"],
        cache_filename="aws_doc_cache.sqlite",
        doc_language="en-US",
    ),
    "azure": ProviderConfig(
        name="azure",
        display_name="Azure",
        site_filter="learn.microsoft.com",
        whitelist=["learn.microsoft.com"],
        cache_filename="azure_doc_cache.sqlite",
        doc_language="en-US",
    ),
    "gcp": ProviderConfig(
        name="gcp",
        display_name="GCP",
        site_filter="cloud.google.com",
        whitelist=["cloud.google.com"],
        cache_filename="gcp_doc_cache.sqlite",
        doc_language="en-US",
    ),
}

VALID_PROVIDERS = sorted(PROVIDERS.keys())


def get_provider(name: str) -> ProviderConfig:
    """Return the :class:`ProviderConfig` for ``name``.

    Raises :class:`ValueError` if ``name`` is not a registered provider.
    """

    if name not in PROVIDERS:
        raise ValueError(
            f"unknown provider: {name!r}, valid providers: {VALID_PROVIDERS}"
        )
    return PROVIDERS[name]
