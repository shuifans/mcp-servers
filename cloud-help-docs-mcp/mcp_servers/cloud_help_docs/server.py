"""MCP Server entrypoint for ``cloud-help-docs-mcp``.

Registers three generic tools (``search_cloud_docs``, ``read_cloud_doc``,
``retrieve_cloud_docs``) on a stdio MCP server using the official
`mcp <https://pypi.org/project/mcp/>`_ Python SDK.

Each tool accepts a ``provider`` parameter to select the target cloud
documentation site (aliyun, volcengine, tencent_cloud, aws, azure, gcp).

Run with::

    python -m mcp_servers.cloud_help_docs.server
    # or
    cloud-help-docs-mcp
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
from .providers import VALID_PROVIDERS, get_provider
from .tools.read import read_cloud_doc
from .tools.retrieve import retrieve_cloud_docs
from .tools.search import search_cloud_docs

logger = logging.getLogger(__name__)

SERVER_NAME = "cloud-help-docs-mcp"
SERVER_VERSION = "0.1.0"


# ---- input schemas (kept in sync with schemas/input_schemas.json) ----------

_PROVIDER_DESCRIPTION = (
    "Cloud provider name. Supported values: "
    + ", ".join(f"'{p}'" for p in VALID_PROVIDERS)
    + "."
)

_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "provider": {
            "type": "string",
            "enum": VALID_PROVIDERS,
            "description": _PROVIDER_DESCRIPTION,
        },
        "query": {
            "type": "string",
            "description": "Natural language search query.",
            "minLength": 1,
        },
        "product": {
            "type": ["string", "null"],
            "description": "Optional product name hint, e.g. 'ECS', 'S3', 'BigQuery'.",
        },
        "top_k": {
            "type": "integer",
            "description": "Maximum number of candidates to return.",
            "minimum": 1,
            "maximum": 20,
            "default": 5,
        },
    },
    "required": ["provider", "query"],
    "additionalProperties": False,
}

_READ_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "provider": {
            "type": "string",
            "enum": VALID_PROVIDERS,
            "description": _PROVIDER_DESCRIPTION,
        },
        "url": {
            "type": "string",
            "description": "HTTPS URL of a cloud provider doc within the provider's whitelist.",
            "minLength": 1,
        },
        "force_refresh": {
            "type": "boolean",
            "description": "If true, bypass the cache and re-fetch.",
            "default": False,
        },
    },
    "required": ["provider", "url"],
    "additionalProperties": False,
}

_RETRIEVE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "provider": {
            "type": "string",
            "enum": VALID_PROVIDERS,
            "description": _PROVIDER_DESCRIPTION,
        },
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
    "required": ["provider", "query"],
    "additionalProperties": False,
}


def _tool_definitions() -> list[Tool]:
    return [
        Tool(
            name="search_cloud_docs",
            description=(
                "Search official cloud provider documentation via IQS UnifiedSearch. "
                "Specify the provider (aliyun, volcengine, tencent_cloud, aws, azure, gcp) "
                "to target the corresponding doc site. "
                "Returns a list of candidate URLs with titles, snippets and relevance scores. "
                "Use this to discover doc URLs before reading. Does not return full content."
            ),
            inputSchema=_SEARCH_INPUT_SCHEMA,
        ),
        Tool(
            name="read_cloud_doc",
            description=(
                "Fetch the full content (markdown or text) of a single cloud provider doc URL "
                "via IQS ReadPageBasic, with SQLite caching and an automatic scrape "
                "fallback when the page is too short. Specify the provider to apply the "
                "correct URL whitelist. Non-whitelisted URLs are rejected."
            ),
            inputSchema=_READ_INPUT_SCHEMA,
        ),
        Tool(
            name="retrieve_cloud_docs",
            description=(
                "End-to-end retrieval: search top-K docs for a query on the specified "
                "cloud provider, read each page, slice a 200-500 char excerpt most relevant "
                "to the query, and return a list of citable Evidence objects (id, title, url, "
                "excerpt, confidence, retrieved_at, metadata). Prefer this tool for any answer "
                "that must cite official cloud provider documentation."
            ),
            inputSchema=_RETRIEVE_INPUT_SCHEMA,
        ),
    ]


def _result_to_text(result: Any) -> list[TextContent]:
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=payload)]


async def _dispatch(name: str, arguments: dict[str, Any] | None) -> Any:
    args = arguments or {}
    provider = args.get("provider", "")
    if not provider:
        raise ValueError("provider is required")
    # Validate provider early for a clear error message.
    get_provider(provider)

    if name == "search_cloud_docs":
        return await search_cloud_docs(
            provider=provider,
            query=args.get("query", ""),
            product=args.get("product"),
            top_k=int(args.get("top_k", 5)),
        )
    if name == "read_cloud_doc":
        return await read_cloud_doc(
            provider=provider,
            url=args.get("url", ""),
            force_refresh=bool(args.get("force_refresh", False)),
        )
    if name == "retrieve_cloud_docs":
        return await retrieve_cloud_docs(
            provider=provider,
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
        "starting %s v%s (cache_dir=%s, providers=%s)",
        SERVER_NAME,
        SERVER_VERSION,
        cfg.cache_dir,
        VALID_PROVIDERS,
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
