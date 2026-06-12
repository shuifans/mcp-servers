"""Evidence object construction.

An :class:`Evidence` object follows the spec defined in
``schemas/evidence_schema.json`` and forms the unit of citable knowledge
returned by the ``retrieve_cloud_docs`` tool.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = Literal["high", "medium", "low"]


class Evidence(BaseModel):
    """Citable evidence chunk returned by the docs MCP."""

    id: str = Field(..., description="Unique evidence id, format ev_{short_uuid}")
    source_type: str = Field(default="official_doc")
    provider: str = Field(default="aliyun")
    title: str
    url: str
    excerpt: str = Field(..., description="200-500 chars relevant slice from the page")
    retrieved_at: str = Field(..., description="ISO-8601 timestamp")
    published_at: str | None = None
    confidence: Confidence = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


def _short_uuid() -> str:
    return uuid.uuid4().hex[:12]


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def confidence_from_score(score: float | None) -> Confidence:
    """Map a search relevance score to a confidence bucket.

    - ``score > 0.8`` -> ``high``
    - ``0.5 <= score <= 0.8`` -> ``medium``
    - ``score < 0.5`` -> ``low``
    - missing score -> ``medium`` (neutral default)
    """

    if score is None:
        return "medium"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "medium"
    if s > 0.8:
        return "high"
    if s >= 0.5:
        return "medium"
    return "low"


_TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if t]


def slice_excerpt(
    content: str,
    query: str,
    *,
    min_chars: int = 200,
    max_chars: int = 500,
) -> str:
    """Return a 200-500 char excerpt from ``content`` most relevant to ``query``.

    Strategy:
    1. Tokenize the query into search terms.
    2. Find the position with the highest token-density window of size
       ``max_chars``.
    3. Pad the window to at least ``min_chars`` if shorter.
    4. Trim to whitespace boundaries when possible.
    """

    text = (content or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    tokens = _tokenize(query)
    if not tokens:
        return text[:max_chars].rstrip() + ("…" if len(text) > max_chars else "")

    lower = text.lower()
    # Score each candidate window by counting occurrences of any query token.
    best_start = 0
    best_score = -1
    step = max(1, max_chars // 4)
    for start in range(0, max(1, len(text) - min_chars), step):
        window = lower[start : start + max_chars]
        score = sum(window.count(tok) for tok in tokens if tok)
        if score > best_score:
            best_score = score
            best_start = start

    end = min(len(text), best_start + max_chars)
    # Try to extend to nearest whitespace for cleaner cuts.
    while best_start > 0 and not text[best_start - 1].isspace() and best_start > best_start - 32:
        best_start -= 1
        if text[best_start].isspace():
            best_start += 1
            break
    while end < len(text) and not text[end - 1].isspace() and end < best_start + max_chars + 32:
        end += 1

    excerpt = text[best_start:end].strip()
    if len(excerpt) < min_chars and len(text) >= min_chars:
        # Fallback: take leading min_chars
        excerpt = text[:max_chars].strip()
    if best_start > 0:
        excerpt = "…" + excerpt
    if end < len(text):
        excerpt = excerpt + "…"
    return excerpt


class EvidenceBuilder:
    """Build :class:`Evidence` objects from search/read pipeline outputs."""

    def __init__(
        self,
        provider: str = "aliyun",
        tool: str = "cloud-help-docs-mcp",
    ):
        self.provider = provider
        self.tool = tool

    def build(
        self,
        *,
        query: str,
        url: str,
        title: str,
        content: str,
        score: float | None = None,
        product: str | None = None,
        doc_language: str = "en-US",
        published_at: str | None = None,
        retrieved_at: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> Evidence:
        excerpt = slice_excerpt(content, query)
        metadata: dict[str, Any] = {
            "doc_language": doc_language,
            "tool": self.tool,
        }
        if product:
            metadata["product"] = product
        if score is not None:
            metadata["search_score"] = float(score)
        if extra_metadata:
            metadata.update(extra_metadata)

        return Evidence(
            id=f"ev_{_short_uuid()}",
            source_type="official_doc",
            provider=self.provider,
            title=title or url,
            url=url,
            excerpt=excerpt,
            retrieved_at=retrieved_at or _utc_iso_now(),
            published_at=published_at,
            confidence=confidence_from_score(score),
            metadata=metadata,
        )
