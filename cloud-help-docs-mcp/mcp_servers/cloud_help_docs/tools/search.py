"""``search_cloud_docs`` tool implementation."""

from __future__ import annotations

import logging
from typing import Any

from ..core.iqs_client import IQSClient, IQSError
from ..core.url_whitelist import is_url_allowed
from ..providers import get_provider

logger = logging.getLogger(__name__)


_PRODUCT_HINT_TEMPLATE = "{product} {query}"


def _preprocess_query(query: str, product: str | None, site_filter: str) -> str:
    """Build the IQS query string.

    Prepends ``site:{site_filter}`` to restrict results to the target
    documentation domain.  This is far more effective than the IQS
    ``site`` parameter (which is only a preference hint).
    """

    q = (query or "").strip()
    if not q:
        raise ValueError("query must be a non-empty string")
    if product and product.strip():
        q = _PRODUCT_HINT_TEMPLATE.format(product=product.strip(), query=q)
    if site_filter:
        q = f"site:{site_filter} {q}"
    return q


# Candidate field names for each output key, in priority order. IQS responses
# (and the heterogeneous payloads we accept) name these inconsistently, so we
# probe several aliases rather than hard-depend on one. Keep this aligned with
# the actual UnifiedSearch ``pageItems`` shape — verify against a live response
# (LOG_LEVEL=DEBUG dumps the raw ``raw`` list) and add aliases as needed.
_URL_KEYS = ("url", "link", "source_url", "sourceUrl", "pageUrl", "displayLink")
_TITLE_KEYS = ("title", "name", "htmlTitle", "pageTitle")
_SNIPPET_KEYS = ("snippet", "summary", "description", "mainText", "htmlSnippet", "abstract")
# Relevance score: with ``rerankScore: True`` IQS typically returns ``rerankScore``;
# fall back to other common spellings and a nested ``scoreInfo``.
_SCORE_KEYS = ("score", "rerankScore", "relevanceScore", "rerank_score", "relevance_score")


def _first_str(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _coerce_score(value: Any) -> float | None:
    if isinstance(value, bool):  # avoid bool being treated as int
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _extract_score(item: dict[str, Any]) -> float | None:
    for key in _SCORE_KEYS:
        score = _coerce_score(item.get(key))
        if score is not None:
            return score
    nested = item.get("scoreInfo")
    if isinstance(nested, dict):
        for key in _SCORE_KEYS:
            score = _coerce_score(nested.get(key))
            if score is not None:
                return score
    return None


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize an IQS search hit into a stable shape."""

    return {
        "url": _first_str(item, _URL_KEYS),
        "title": _first_str(item, _TITLE_KEYS),
        "snippet": _first_str(item, _SNIPPET_KEYS),
        "score": _extract_score(item),
    }


async def search_cloud_docs(
    provider: str,
    query: str,
    product: str | None = None,
    top_k: int = 5,
    *,
    client: IQSClient | None = None,
) -> dict[str, Any]:
    """Search cloud provider docs via IQS UnifiedSearch.

    Returns a dict with shape::

        {
          "results": [{"url", "title", "snippet", "score"}, ...],
          "total_found": int,
          "query_used": str,
          "provider": str,
        }
    """

    pc = get_provider(provider)
    top_k = max(1, min(int(top_k or 5), 20))
    query_used = _preprocess_query(query, product, pc.site_filter)

    # With site: prefix in the query, IQS returns high-quality results so
    # we only need a modest over-fetch to account for whitelist filtering.
    fetch_count = min(top_k * 4, 20)

    own_client = client is None
    iqs = client or IQSClient()
    try:
        try:
            raw = await iqs.unified_search(
                query_used, site="", num_results=fetch_count
            )
        except IQSError as exc:
            logger.warning("unified_search failed: %s", exc)
            return {
                "results": [],
                "total_found": 0,
                "query_used": query_used,
                "provider": pc.name,
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
        if not is_url_allowed(normalized["url"], pc.whitelist):
            logger.info("filtered non-whitelisted url: %s", normalized["url"])
            continue
        results.append(normalized)
        if len(results) >= top_k:
            break

    return {
        "results": results,
        "total_found": len(results),
        "query_used": query_used,
        "provider": pc.name,
    }
