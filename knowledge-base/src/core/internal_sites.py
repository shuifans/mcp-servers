import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from .db import Database
from .models import Location, SearchResult
from .parsers import ParsedPart, chunk_parts

log = logging.getLogger(__name__)


class InternalSiteAdapter:
    def __init__(
        self, source_type: str, base_url: str, search_path: str, profile, db: Database,
        vector_store=None, candidate_prefixes: tuple[str, ...] = (), use_search_page: bool = False,
    ):
        self.source_type, self.base_url, self.search_path = source_type, base_url, search_path
        self.profile, self.db, self.vector_store = profile, db, vector_store
        self.candidate_prefixes, self.use_search_page = candidate_prefixes, use_search_page

    async def _context(self, headless=True):
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=headless, channel="chrome")
        state_file = self.db.path.parent / "internal-auth-state.json"
        context = await browser.new_context(
            storage_state=str(state_file) if state_file.exists() else None,
            viewport={"width": 1440, "height": 1000},
        )
        return pw, browser, context

    async def is_authenticated(self) -> bool:
        try:
            state_file = self.db.path.parent / "internal-auth-state.json"
            if not state_file.exists():
                return False
            state = json.loads(state_file.read_text())
            now = time.time()
            relevant = [
                cookie for cookie in state.get("cookies", [])
                if cookie.get("domain", "").endswith(("alibaba-inc.com", "atatech.org"))
            ]
            return any(not cookie.get("expires") or cookie["expires"] <= 0 or cookie["expires"] > now for cookie in relevant)
        except Exception:
            return False

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            pw, browser, context = await self._context()
            page = await context.new_page()
            url = urljoin(self.base_url, self.search_path.format(query=quote(query)))
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if "login.alibaba-inc.com" in page.url:
                await context.close()
                await browser.close()
                await pw.stop()
                return []
            await page.wait_for_timeout(3000)
            if self.source_type == "yunzhidao":
                results = await self._search_yunzhidao(page, query, limit)
                await context.close()
                await browser.close()
                await pw.stop()
                return results
            if self.use_search_page:
                result = await self._fetch_with_page(page, page.url, f"云知道搜索：{query}")
                await context.close()
                await browser.close()
                await pw.stop()
                return [result] if result else []
            anchors = await page.locator("a").all()
            candidates = []
            host = urlparse(self.base_url).netloc
            for anchor in anchors[:300]:
                href, text = await anchor.get_attribute("href"), (await anchor.inner_text()).strip()
                if not href or len(text) < 4:
                    continue
                full = urljoin(self.base_url, href)
                if self.candidate_prefixes and not any(
                    urlparse(full).path.startswith(prefix) for prefix in self.candidate_prefixes
                ):
                    continue
                if urlparse(full).netloc == host and full not in [x[1] for x in candidates]:
                    candidates.append((text[:200], full))
                if len(candidates) >= limit:
                    break
            results = []
            for title, candidate_url in candidates:
                result = await self._fetch_with_page(page, candidate_url, title)
                if result:
                    results.append(result)
            await context.close()
            await browser.close()
            await pw.stop()
            return results
        except Exception as exc:
            log.warning("%s search unavailable: %s", self.source_type, exc)
            return []

    async def _search_yunzhidao(self, page, query: str, limit: int) -> list[SearchResult]:
        payload = {
            "service": "DocumentService",
            "method": "smartSearch",
            "params": [
                {"withOperator": True},
                {"query": query, "order": "RELEVANCE", "queryProcess": None, "secondRankName": None, "recordQuery": True},
                {"pageSize": limit, "pageNum": 0},
            ],
        }
        data = await page.evaluate(
            """async ({payload}) => {
                const response = await fetch('/hsf/invoke?service=DocumentService&method=smartSearch', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                return await response.json();
            }""",
            {"payload": payload},
        )
        items = ((data.get("content") or {}).get("content") or [])[:limit]
        search_url = f"https://yunzhidao.alibaba-inc.com/search?q={quote(query)}&tabKey=doc"
        results = []
        for item in items:
            title = item.get("docName") or item.get("originalName") or "云知道资料"
            metadata = " · ".join(
                str(value) for value in [
                    "官方资料" if item.get("official") else None,
                    item.get("authorName") or item.get("ownerName"),
                    (item.get("updateTime") or "")[:10],
                    item.get("concreteFormatType"),
                ] if value
            )
            content = " ".join(x for x in [title, item.get("description") or "", metadata] if x)
            document_id = hashlib.sha256(f"yunzhidao:{item.get('id')}:{title}".encode()).hexdigest()
            chunk = {
                "chunk_id": hashlib.sha256(f"{document_id}:{content}".encode()).hexdigest(),
                "document_id": document_id, "title": title, "content": content,
                "source_type": "yunzhidao", "path": None, "url": search_url,
                "location": {"section": metadata or "云知道资料搜索"},
            }
            self.db.replace_document(
                {
                    "document_id": document_id, "title": title, "source_type": "yunzhidao",
                    "content_hash": document_id, "updated_at": datetime.now(timezone.utc).isoformat(), "url": search_url,
                },
                [chunk],
            )
            if self.vector_store:
                self.vector_store.upsert([chunk])
            results.append(SearchResult(**chunk, score=1.0))
        return results

    async def _fetch_with_page(self, page, url: str, fallback_title: str) -> SearchResult | None:
        if page.url != url:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(5000 if self.source_type == "yunzhidao" else 2000)
        html, page_title = await page.content(), await page.title()
        heading = page.locator("h1").first
        title = (await heading.inner_text()).strip() if await heading.count() else fallback_title or page_title
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style", "nav", "footer", "header"]):
            node.decompose()
        text = " ".join(soup.get_text(" ", strip=True).split())
        if self.source_type == "ata":
            article = page.locator('[class*="article"]').first
            if await article.count():
                visible = " ".join((await article.inner_text()).split())
                if len(visible) > 100:
                    text = visible
        elif self.source_type == "yunzhidao":
            text = " ".join((await page.locator("body").first.inner_text()).split())
        if len(text) < 100:
            return None
        if self.source_type == "yunzhidao":
            title = fallback_title
        document_id = hashlib.sha256(url.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        parts = chunk_parts([ParsedPart(text, {"section": title})])
        chunks = [
            {
                "chunk_id": hashlib.sha256(f"{document_id}:{i}:{p.text}".encode()).hexdigest(),
                "document_id": document_id, "title": title, "content": p.text,
                "source_type": self.source_type, "path": None, "url": url, "location": p.location,
            }
            for i, p in enumerate(parts)
        ]
        self.db.replace_document(
            {"document_id": document_id, "title": title, "source_type": self.source_type, "content_hash": document_id, "updated_at": now, "url": url},
            chunks,
        )
        if self.vector_store:
            self.vector_store.upsert(chunks)
        first = chunks[0]
        return SearchResult(**first, score=1.0)


def build_internal_sites(settings, db, vector_store):
    return [
        InternalSiteAdapter(
            "ata", settings.ata_base_url, "search?q={query}", settings.internal_browser_profile,
            db, vector_store, candidate_prefixes=("/articles/",),
        ),
        InternalSiteAdapter(
            "yunzhidao", "https://yunzhidao.alibaba-inc.com/", "search?q={query}&tabKey=doc", settings.internal_browser_profile,
            db, vector_store, use_search_page=True,
        ),
    ]
