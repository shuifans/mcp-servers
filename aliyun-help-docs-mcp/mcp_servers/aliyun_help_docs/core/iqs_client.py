"""HTTP client for the Aliyun IQS API.

Endpoints used:
- ``POST {base_url}/search/unified`` - UnifiedSearch.
- ``POST {base_url}/readpage/basic`` - ReadPageBasic.
- ``POST {base_url}/readpage/scrape`` - Scrape (fallback).

Authentication: ``Authorization: Bearer {IQS_API_KEY}`` header.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ..config import Config, get_config

logger = logging.getLogger(__name__)


class IQSError(RuntimeError):
    """Raised when the IQS API returns an error or fails after retries."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        kind: str = "iqs_error",
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind
        self.cause = cause

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": self.kind,
            "message": str(self),
            "status_code": self.status_code,
        }


class IQSClient:
    """Async HTTP client for the IQS API."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or get_config()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._config.iqs_base_url.rstrip("/"),
            headers=self._default_headers(),
        )

    async def __aenter__(self) -> IQSClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---- public API ------------------------------------------------------------

    async def unified_search(
        self,
        query: str,
        site: str = "help.aliyun.com",
        num_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Call UnifiedSearch and return the candidate results list."""

        payload: dict[str, Any] = {
            "query": query,
            "engineType": "LiteAdvanced",
            "contents": {
                "mainText": True,
                "markdownText": True,
                "summary": False,
                "rerankScore": True,
            },
            "advancedParams": {
                "numResults": int(num_results),
            },
        }
        if site:
            payload["advancedParams"]["site"] = site
        data = await self._post_json(
            self._config.iqs_search_path,
            payload,
            timeout=self._config.iqs_search_timeout_s,
            retries=self._config.iqs_search_retries,
            op="unified_search",
        )
        results = self._extract_search_results(data)
        return results

    async def read_page_basic(self, url: str, fmt: str = "markdown") -> dict[str, Any]:
        """Call ReadPageBasic for a single URL."""

        payload: dict[str, Any] = {"url": url, "maxAge": 0}
        data = await self._post_json(
            self._config.iqs_read_page_path,
            payload,
            timeout=self._config.iqs_read_timeout_s,
            retries=self._config.iqs_read_retries,
            op="read_page_basic",
        )
        return self._extract_page(data, url=url, default_format=fmt)

    async def read_page_scrape(self, url: str, fmt: str = "text") -> dict[str, Any]:
        """Fallback scrape endpoint when ReadPageBasic returns too little content."""

        payload: dict[str, Any] = {"url": url, "maxAge": 0}
        data = await self._post_json(
            self._config.iqs_scrape_page_path,
            payload,
            timeout=self._config.iqs_scrape_timeout_s,
            retries=0,
            op="read_page_scrape",
        )
        return self._extract_page(data, url=url, default_format=fmt)

    # ---- internals -------------------------------------------------------------

    def _default_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sa-cloud-advisory-toolkit/aliyun-help-docs-mcp",
        }
        if self._config.iqs_api_key:
            headers["Authorization"] = f"Bearer {self._config.iqs_api_key}"
        return headers

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        retries: int,
        op: str,
    ) -> Any:
        attempt = 0
        last_error: BaseException | None = None
        while attempt <= retries:
            try:
                resp = await self._client.post(path, json=payload, timeout=timeout)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning("IQS %s transport error (attempt %s): %s", op, attempt + 1, exc)
                if attempt >= retries:
                    raise IQSError(
                        f"IQS {op} transport error: {exc}",
                        kind="iqs_transport_error",
                        cause=exc,
                    ) from exc
                await asyncio.sleep(self._config.iqs_retry_backoff_s * (2 ** attempt))
                attempt += 1
                continue

            status = resp.status_code
            if 200 <= status < 300:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise IQSError(
                        f"IQS {op} returned non-JSON response",
                        status_code=status,
                        kind="iqs_invalid_response",
                        cause=exc,
                    ) from exc

            # 4xx errors are not retried.
            if 400 <= status < 500:
                snippet = (resp.text or "")[:512]
                raise IQSError(
                    f"IQS {op} client error {status}: {snippet}",
                    status_code=status,
                    kind="iqs_client_error",
                )

            # 5xx errors are retried up to ``retries`` times.
            snippet = (resp.text or "")[:512]
            logger.warning("IQS %s server error %s (attempt %s): %s", op, status, attempt + 1, snippet)
            if attempt >= retries:
                raise IQSError(
                    f"IQS {op} server error {status}: {snippet}",
                    status_code=status,
                    kind="iqs_server_error",
                )
            await asyncio.sleep(self._config.iqs_retry_backoff_s * (2 ** attempt))
            attempt += 1

        # Should not reach here.
        raise IQSError(
            f"IQS {op} failed without explicit error",
            kind="iqs_unknown_error",
            cause=last_error,
        )

    @staticmethod
    def _extract_search_results(data: Any) -> list[dict[str, Any]]:
        """Best-effort extraction of search results from heterogeneous payloads."""

        if data is None:
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("pageItems", "results", "items", "data", "hits"):
                candidate = data.get(key)
                if isinstance(candidate, list):
                    return [item for item in candidate if isinstance(item, dict)]
                if isinstance(candidate, dict):
                    nested = candidate.get("results") or candidate.get("items")
                    if isinstance(nested, list):
                        return [item for item in nested if isinstance(item, dict)]
        return []

    @staticmethod
    def _extract_page(data: Any, *, url: str, default_format: str) -> dict[str, Any]:
        """Best-effort extraction of a page object from heterogeneous payloads."""

        if isinstance(data, dict):
            page = data
            for key in ("data", "result", "page"):
                if isinstance(page.get(key), dict):
                    page = page[key]
                    break
            content = (
                page.get("content")
                or page.get("markdown")
                or page.get("text")
                or page.get("body")
                or ""
            )
            metadata = page.get("metadata") or {}
            title = page.get("title") or metadata.get("title") or page.get("name") or ""
            page_url = page.get("url") or metadata.get("url") or url
            content_format = page.get("format") or page.get("content_format") or default_format
            return {
                "url": page_url,
                "title": str(title) if title is not None else "",
                "content": str(content) if content is not None else "",
                "content_format": str(content_format),
            }
        return {
            "url": url,
            "title": "",
            "content": "",
            "content_format": default_format,
        }
