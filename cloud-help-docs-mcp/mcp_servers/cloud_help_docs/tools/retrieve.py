"""``retrieve_cloud_docs`` tool implementation.

Composes :func:`search_cloud_docs` + :func:`read_cloud_doc` into a list of
:class:`~mcp_servers.cloud_help_docs.core.evidence.Evidence` objects.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import get_config
from ..core.cache import DocCache
from ..core.evidence import EvidenceBuilder
from ..core.iqs_client import IQSClient
from ..providers import get_provider
from .read import read_cloud_doc
from .search import search_cloud_docs

logger = logging.getLogger(__name__)


async def retrieve_cloud_docs(
    provider: str,
    query: str,
    product: str | None = None,
    top_k_chunks: int = 5,
    *,
    client: IQSClient | None = None,
    cache: DocCache | None = None,
) -> dict[str, Any]:
    """Search + read top-N candidates and return ``Evidence[]``.

    Returns a dict::

        {
          "evidences": [Evidence, ...],
          "query_used": str,
          "total_sources_searched": int,
          "total_chunks_returned": int,
          "provider": str,
        }
    """

    pc = get_provider(provider)
    top_k_chunks = max(1, min(int(top_k_chunks or 5), 10))

    own_client = client is None
    iqs = client or IQSClient()
    own_cache = cache is None
    cfg = get_config()
    cache_path = cfg.ensure_cache_dir(provider)
    cache_inst = cache or DocCache(cache_path=cache_path)

    try:
        search_result = await search_cloud_docs(
            provider=provider,
            query=query,
            product=product,
            top_k=top_k_chunks,
            client=iqs,
        )
        candidates = search_result.get("results", [])
        query_used = search_result.get("query_used", query)

        if not candidates:
            return {
                "evidences": [],
                "query_used": query_used,
                "total_sources_searched": 0,
                "total_chunks_returned": 0,
                "provider": pc.name,
                "error": search_result.get("error"),
            }

        # Read pages concurrently with a small parallelism bound.
        sem = asyncio.Semaphore(4)

        async def _read(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            async with sem:
                doc = await read_cloud_doc(
                    provider=provider,
                    url=item.get("url") or item.get("link") or "",
                    cache=cache_inst,
                    client=iqs,
                )
                return item, doc

        reads = await asyncio.gather(*(_read(it) for it in candidates), return_exceptions=False)

        builder = EvidenceBuilder(provider=pc.name, tool="cloud-help-docs-mcp")
        evidences: list[dict[str, Any]] = []
        for item, doc in reads:
            if not isinstance(doc, dict) or doc.get("error"):
                logger.info(
                    "skip candidate due to read error: %s",
                    doc.get("error") if isinstance(doc, dict) else doc,
                )
                continue
            content = doc.get("content") or ""
            if not content:
                continue
            evidence = builder.build(
                query=query_used,
                url=doc.get("url") or item.get("url") or item.get("link") or "",
                title=doc.get("title") or item.get("title") or "",
                content=content,
                score=item.get("score"),
                product=product,
                doc_language=pc.doc_language,
            )
            evidences.append(evidence.model_dump())
            if len(evidences) >= top_k_chunks:
                break

        return {
            "evidences": evidences,
            "query_used": query_used,
            "total_sources_searched": len(candidates),
            "total_chunks_returned": len(evidences),
            "provider": pc.name,
        }
    finally:
        if own_client:
            await iqs.aclose()
        if own_cache:
            cache_inst.close()
