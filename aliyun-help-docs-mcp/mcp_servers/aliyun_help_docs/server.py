"""MCP Server entrypoint for ``aliyun-help-docs-mcp``.

Registers three tools (``search_aliyun_docs``, ``read_aliyun_doc``,
``retrieve_aliyun_docs``) on a stdio MCP server using the official
`mcp <https://pypi.org/project/mcp/>`_ Python SDK.

Run with::

    python -m mcp_servers.aliyun_help_docs.server
    # or
    aliyun-help-docs-mcp
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import get_config
from .tools.read import read_aliyun_doc
from .tools.retrieve import retrieve_aliyun_docs
from .tools.search import search_aliyun_docs

logger = logging.getLogger(__name__)

SERVER_NAME = "aliyun-help-docs-mcp"
SERVER_VERSION = "0.1.0"


# ---- input schemas (kept in sync with schemas/input_schemas.json) ----------

_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language search query.",
            "minLength": 1,
        },
        "product": {
            "type": ["string", "null"],
            "description": "Optional product name hint, e.g. 'ECS', 'OSS'.",
        },
        "top_k": {
            "type": "integer",
            "description": "Maximum number of candidates to return.",
            "minimum": 1,
            "maximum": 20,
            "default": 5,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}

_READ_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "HTTPS URL of an Aliyun help doc within the whitelist.",
            "minLength": 1,
        },
        "force_refresh": {
            "type": "boolean",
            "description": "If true, bypass the cache and re-fetch.",
            "default": False,
        },
    },
    "required": ["url"],
    "additionalProperties": False,
}

_RETRIEVE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language query.",
            "minLength": 1,
        },
        "product": {
            "type": ["string", "null"],
            "description": "Optional product name hint.",
        },
        "top_k_chunks": {
            "type": "integer",
            "description": "Maximum number of evidence chunks to return.",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


def _tool_definitions() -> list[Tool]:
    return [
        Tool(
            name="search_aliyun_docs",
            description=(
                "Search official Aliyun help docs (help.aliyun.com) via IQS UnifiedSearch. "
                "Returns a list of candidate URLs with titles, snippets and relevance scores. "
                "Use this to discover doc URLs before reading. Does not return full content."
            ),
            inputSchema=_SEARCH_INPUT_SCHEMA,
        ),
        Tool(
            name="read_aliyun_doc",
            description=(
                "Fetch the full content (markdown or text) of a single Aliyun help doc URL "
                "via IQS ReadPageBasic, with SQLite caching and an automatic scrape "
                "fallback when the page is too short. URLs are validated against the "
                "configured whitelist; non-whitelisted URLs are rejected."
            ),
            inputSchema=_READ_INPUT_SCHEMA,
        ),
        Tool(
            name="retrieve_aliyun_docs",
            description=(
                "End-to-end retrieval: search top-K Aliyun docs for a query, read each "
                "page, slice a 200-500 char excerpt most relevant to the query, and "
                "return a list of citable Evidence objects (id, title, url, excerpt, "
                "confidence, retrieved_at, metadata). Prefer this tool for any answer "
                "that must cite official Aliyun documentation."
            ),
            inputSchema=_RETRIEVE_INPUT_SCHEMA,
        ),
    ]


def _result_to_text(result: Any) -> list[TextContent]:
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=payload)]


async def _dispatch(name: str, arguments: dict[str, Any] | None) -> Any:
    args = arguments or {}
    if name == "search_aliyun_docs":
        return await search_aliyun_docs(
            query=args.get("query", ""),
            product=args.get("product"),
            top_k=int(args.get("top_k", 5)),
        )
    if name == "read_aliyun_doc":
        return await read_aliyun_doc(
            url=args.get("url", ""),
            force_refresh=bool(args.get("force_refresh", False)),
        )
    if name == "retrieve_aliyun_docs":
        return await retrieve_aliyun_docs(
            query=args.get("query", ""),
            product=args.get("product"),
            top_k_chunks=int(args.get("top_k_chunks", 5)),
        )
    raise ValueError(f"unknown tool: {name}")


def build_server() -> Server:
    """Construct and configure the MCP :class:`Server` instance."""

    server: Server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return _tool_definitions()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        try:
            result = await _dispatch(name, arguments)
        except ValueError as exc:
            return _result_to_text({"error": "invalid_argument", "message": str(exc)})
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("tool %s raised an unexpected error", name)
            return _result_to_text(
                {"error": "internal_error", "message": f"{type(exc).__name__}: {exc}"}
            )
        return _result_to_text(result)

    return server


async def _run_stdio() -> None:
    # Trigger config + logging setup on startup.
    cfg = get_config()
    logger.info(
        "starting %s v%s (cache=%s, whitelist=%s)",
        SERVER_NAME,
        SERVER_VERSION,
        cfg.cache_path,
        cfg.url_whitelist,
    )
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Console-script entrypoint."""

    try:
        asyncio.run(_run_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
