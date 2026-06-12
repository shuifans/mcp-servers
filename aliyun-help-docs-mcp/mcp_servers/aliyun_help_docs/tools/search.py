"""``search_aliyun_docs`` tool implementation."""

from __future__ import annotations

import logging
from typing import Any

from ..core.iqs_client import IQSClient, IQSError
from ..core.url_whitelist import is_url_allowed

logger = logging.getLogger(__name__)


_PRODUCT_HINT_TEMPLATE = "{product} {query}"


def _preprocess_query(query: str, product: str | None) -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError("query must be a non-empty string")
    if product and product.strip():
        return _PRODUCT_HINT_TEMPLATE.format(product=product.strip(), query=q)
    return q


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize an IQS search hit into a stable shape."""

    url = item.get("url") or item.get("link") or item.get("source_url") or ""
    title = item.get("title") or item.get("name") or ""
    snippet = item.get("snippet") or item.get("summary") or item.get("description") or ""
    score = item.get("score")
    if isinstance(score, str):
        try:
            score = float(score)
        except ValueError:
            score = None
    return {
        "url": str(url),
        "title": str(title),
        "snippet": str(snippet),
        "score": float(score) if isinstance(score, (int, float)) else None,
    }


async def search_aliyun_docs(
    query: str,
    product: str | None = None,
    top_k: int = 5,
    *,
    client: IQSClient | None = None,
    site: str = "help.aliyun.com",
) -> dict[str, Any]:
    """Search Aliyun docs via IQS UnifiedSearch.

    Returns a dict with shape::

        {
          "results": [{"url", "title", "snippet", "score"}, ...],
          "total_found": int,
          "query_used": str,
        }
    """

    top_k = max(1, min(int(top_k or 5), 20))
    query_used = _preprocess_query(query, product)

    own_client = client is None
    iqs = client or IQSClient()
    try:
        try:
            raw = await iqs.unified_search(query_used, site=site, num_results=top_k)
        except IQSError as exc:
            logger.warning("unified_search failed: %s", exc)
            return {
                "results": [],
                "total_found": 0,
                "query_used": query_used,
                "error": exc.to_payload(),
            }
    finally:
        if own_client:
            await iqs.aclose()

    results: list[dict[str, Any]] = []
    for item in raw:
        normalized = _normalize_result(item)
        if not normalized["url"]:
            continue
        if not is_url_allowed(normalized["url"]):
            logger.info("filtered non-whitelisted url: %s", normalized["url"])
            continue
        results.append(normalized)
        if len(results) >= top_k:
            break

    return {
        "results": results,
        "total_found": len(results),
        "query_used": query_used,
    }
