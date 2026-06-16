import asyncio
import hashlib
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import httpx

from .models import Location, SearchResult


PREFERRED_DOMAINS = {
    "openai.com": 5.0,
    "anthropic.com": 5.0,
    "deepmind.google": 5.0,
    "blog.google": 4.8,
    "cloud.google.com": 4.8,
    "aws.amazon.com": 4.8,
    "azure.microsoft.com": 4.8,
    "microsoft.com": 4.5,
    "nvidia.com": 4.5,
    "ai.meta.com": 4.5,
    "mistral.ai": 4.5,
    "cohere.com": 4.2,
    "x.ai": 4.2,
    "huggingface.co": 4.2,
    "arxiv.org": 4.2,
    "github.blog": 4.0,
    "cncf.io": 4.2,
    "kubernetes.io": 4.2,
    "cloudflare.com": 4.2,
    "databricks.com": 4.2,
    "snowflake.com": 4.0,
    "redhat.com": 4.0,
    "oracle.com": 4.0,
    "ibm.com": 4.0,
    "developer.aliyun.com": 4.5,
    "help.aliyun.com": 4.5,
    "alibabacloud.com": 4.5,
    "reuters.com": 3.8,
    "bloomberg.com": 3.8,
    "ft.com": 3.8,
    "techcrunch.com": 3.2,
    "theverge.com": 3.0,
    "thenewstack.io": 3.5,
    "infoq.com": 3.2,
    "gartner.com": 3.8,
    "mckinsey.com": 3.6,
    "technologyreview.com": 3.6,
    "hai.stanford.edu": 3.8,
    "nature.com": 3.8,
    "acm.org": 3.8,
    "ieee.org": 3.8,
    "semianalysis.com": 3.6,
}

BLOCKED_DOMAINS = {
    "toutiao.com", "m.toutiao.com", "baijiahao.baidu.com", "tieba.baidu.com",
    "zhihu.com", "csdn.net", "sohu.com", "163.com", "qq.com", "bilibili.com",
    "microsoftedge.microsoft.com",
}

TARGETED_DOMAIN_QUERIES = (
    "site:openai.com",
    "site:anthropic.com",
    "site:deepmind.google OR site:blog.google",
    "site:aws.amazon.com",
    "site:cloud.google.com",
    "site:azure.microsoft.com",
    "site:developer.aliyun.com OR site:alibabacloud.com OR site:cncf.io",
)

QUERY_TRANSLATIONS = {
    "云计算": "cloud computing",
    "基础设施": "infrastructure",
    "最新": "latest",
    "趋势": "trends",
    "行业": "industry",
    "大模型": "large language model",
    "智能体": "AI agent",
    "人工智能": "artificial intelligence",
}


def hostname(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host.removeprefix("www.")


def domain_weight(host: str) -> float:
    return max((weight for domain, weight in PREFERRED_DOMAINS.items() if host == domain or host.endswith("." + domain)), default=0)


def is_blocked(item: dict) -> bool:
    host = hostname(item.get("link", ""))
    tags = item.get("tags") or {}
    return (
        any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS)
        or str(tags.get("isUgc", "")).lower() == "true"
        or str(tags.get("isListPage", "")).lower() == "true"
    )


def is_generic_page(url: str, title: str) -> bool:
    path = urlparse(url).path.rstrip("/").lower()
    generic_paths = {
        "", "/cn", "/blog", "/blogs", "/news", "/resources", "/solutions",
        "/cn/blogs/china", "/jp/blogs/news", "/zh/about/analyst-reports",
    }
    generic_titles = {"aws blog", "openai", "anthropic", "google cloud", "microsoft azure"}
    generic_fragments = (
        "/campaigns/", "/builder/", "/solutions/architect-center", "/whois/",
        "/category/", "/tags/", "/tag/",
    )
    return (
        path in generic_paths
        or title.strip().lower() in generic_titles
        or any(fragment in path for fragment in generic_fragments)
    )


def expand_query(query: str) -> str:
    translated = [english for chinese, english in QUERY_TRANSLATIONS.items() if chinese in query]
    return f"{query} {' '.join(translated)}".strip()


def relevance_score(query: str, item: dict) -> float:
    haystack = f"{item.get('title', '')} {item.get('summary', '')} {item.get('snippet', '')}".lower()
    terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", expand_query(query)) if len(term) > 1]
    matched = sum(1 for term in set(terms) if term in haystack)
    return min(matched * 0.35, 2.0)


def has_temporal_intent(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in ("最新", "趋势", "动态", "新闻", "latest", "trend", "news", "recent"))


def has_temporal_evidence(item: dict) -> bool:
    title = item.get("title", "").lower()
    path = urlparse(item.get("link", "")).path.lower()
    return (
        bool(re.search(r"202[5-9]", title))
        or any(term in title for term in ("latest", "release", "announcement", "发布", "推出", "更新", "趋势", "动态"))
        or any(fragment in path for fragment in ("/blog/", "/blogs/", "/news/", "/index/", "/release"))
    )


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def freshness_score(value: str | None) -> float:
    if not value:
        return 0
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        age_days = max(0, (datetime.now(timezone.utc) - published.astimezone(timezone.utc)).days)
        return 2.0 * math.exp(-age_days / 240)
    except ValueError:
        return 0


class IQSSearchProvider:
    def __init__(self, endpoint: str, api_key: str, engine_type: str = "LiteAdvanced"):
        self.endpoint, self.api_key, self.engine_type = endpoint, api_key, engine_type

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.endpoint or not self.api_key:
            return []
        try:
            expanded = expand_query(query)
            async with httpx.AsyncClient(timeout=15) as client:
                searches = [self._request(client, expanded, 20)]
                searches.extend(
                    self._request(client, f"{expanded} latest news blog release announcement {domains}", 8)
                    for domains in TARGETED_DOMAIN_QUERIES
                )
                batches = await asyncio.gather(*searches, return_exceptions=True)
            items = [item for batch in batches if isinstance(batch, list) for item in batch]
            return self._rank(items, limit, query)
        except Exception:
            return []

    async def _request(self, client: httpx.AsyncClient, query: str, limit: int) -> list[dict]:
        response = await client.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "query": query[:1000],
                "engineType": self.engine_type,
                "contents": {
                    "mainText": True, "markdownText": False, "summary": True, "rerankScore": True,
                },
                "advancedParams": {"numResults": limit},
            },
        )
        response.raise_for_status()
        return response.json().get("pageItems") or []

    def _rank(self, items: list[dict], limit: int, query: str = "") -> list[SearchResult]:
        deduped: dict[str, tuple[float, dict]] = {}
        for item in items:
            url = item.get("link", "")
            content = item.get("summary") or item.get("mainText") or item.get("snippet", "")
            if not url or not content or is_blocked(item):
                continue
            host = hostname(url)
            authority = domain_weight(host)
            if authority == 0 or is_generic_page(url, item.get("title", "")):
                continue
            relevance = relevance_score(query, item) if query else 0
            if query and relevance == 0:
                continue
            if query and has_temporal_intent(query) and not has_temporal_evidence(item):
                continue
            score = (
                float(item.get("rerankScore") or 0)
                + authority
                + freshness_score(item.get("publishedTime"))
                + min(float(item.get("websiteAuthorityScore") or 0), 5) * 0.2
                + relevance
            )
            canonical = canonical_url(url)
            if canonical not in deduped or score > deduped[canonical][0]:
                deduped[canonical] = (score, item)
        ranked = sorted(deduped.values(), key=lambda x: x[0], reverse=True)
        results, per_domain = [], {}
        for score, item in ranked:
            host = hostname(item["link"])
            if per_domain.get(host, 0) >= 2:
                continue
            per_domain[host] = per_domain.get(host, 0) + 1
            published = item.get("publishedTime", "")
            results.append(
                SearchResult(
                    chunk_id=f"public:{hashlib.sha256(item['link'].encode()).hexdigest()}",
                    document_id=f"public:{hashlib.sha256(item['link'].encode()).hexdigest()}",
                    title=item.get("title", "公网搜索结果"),
                    content=item.get("summary") or item.get("mainText") or item.get("snippet", ""),
                    source_type="public", url=item["link"],
                    location=Location(section=f"{host} · {published[:10]}" if published else host),
                    score=score,
                )
            )
            if len(results) >= limit:
                break
        return results
