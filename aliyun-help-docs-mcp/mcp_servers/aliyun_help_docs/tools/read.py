"""``read_aliyun_doc`` tool implementation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..core.cache import DocCache
from ..core.iqs_client import IQSClient, IQSError
from ..core.url_whitelist import UrlWhitelistError, validate_url

logger = logging.getLogger(__name__)


# Below this content length we treat ReadPageBasic as insufficient and fall
# back to the scrape endpoint.
_MIN_USEFUL_CONTENT = 200


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def read_aliyun_doc(
    url: str,
    force_refresh: bool = False,
    *,
    cache: DocCache | None = None,
    client: IQSClient | None = None,
) -> dict[str, Any]:
    """Read a single Aliyun doc page, with cache and scrape fallback.

    Returns a dict::

        {
          "url", "title", "content", "content_format", "content_length",
          "cache_status": "hit"|"miss"|"refresh",
          "retrieved_at": ISO timestamp,
          "fallback_used": bool,
        }
    """

    if not isinstance(url, str) or not url.strip():
        return {"error": "invalid_argument", "message": "url must be a non-empty string"}

    try:
        validate_url(url)
    except UrlWhitelistError as exc:
        return exc.to_error_payload()

    own_cache = cache is None
    cache_inst = cache or DocCache()

    try:
        if not force_refresh:
            entry = cache_inst.get_cached(url)
            if entry is not None:
                return {
                    "url": entry["url"],
                    "title": entry.get("title") or "",
                    "content": entry.get("content") or "",
                    "content_format": entry.get("content_format") or "markdown",
                    "content_length": int(entry.get("content_length") or 0),
                    "cache_status": "hit",
                    "retrieved_at": entry.get("cached_at") or _utc_iso_now(),
                    "fallback_used": (entry.get("fetched_via") or "") == "ReadPageScrape",
                }

        own_client = client is None
        iqs = client or IQSClient()
        try:
            fallback_used = False
            fetched_via = "ReadPageBasic"
            try:
                page = await iqs.read_page_basic(url, fmt="markdown")
            except IQSError as exc:
                logger.warning("read_page_basic failed for %s: %s", url, exc)
                page = {}

            content = (page.get("content") or "").strip()
            content_format = page.get("content_format") or "markdown"
            title = page.get("title") or ""

            if len(content) < _MIN_USEFUL_CONTENT:
                logger.info(
                    "ReadPageBasic returned %s chars (<%s); attempting scrape fallback for %s",
                    len(content),
                    _MIN_USEFUL_CONTENT,
                    url,
                )
                try:
                    scraped = await iqs.read_page_scrape(url, fmt="text")
                    scraped_content = (scraped.get("content") or "").strip()
                    if len(scraped_content) > len(content):
                        content = scraped_content
                        content_format = scraped.get("content_format") or "text"
                        title = title or scraped.get("title") or ""
                        fallback_used = True
                        fetched_via = "ReadPageScrape"
                except IQSError as exc:
                    logger.warning("read_page_scrape fallback failed for %s: %s", url, exc)

            if not content:
                return {
                    "error": "empty_content",
                    "message": f"failed to fetch content for {url}",
                    "url": url,
                }

            entry = cache_inst.set_cached(
                url=url,
                title=title,
                content=content,
                content_format=content_format,
                fetched_via=fetched_via,
            )
        finally:
            if own_client:
                await iqs.aclose()

        return {
            "url": entry["url"],
            "title": entry.get("title") or "",
            "content": entry.get("content") or "",
            "content_format": entry.get("content_format") or "markdown",
            "content_length": int(entry.get("content_length") or 0),
            "cache_status": "refresh" if force_refresh else "miss",
            "retrieved_at": entry.get("cached_at") or _utc_iso_now(),
            "fallback_used": fallback_used,
        }
    finally:
        if own_cache:
            cache_inst.close()
