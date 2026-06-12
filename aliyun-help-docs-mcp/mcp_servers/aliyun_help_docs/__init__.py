"""Aliyun help docs MCP server.

This package implements an MCP (Model Context Protocol) server that exposes
three tools for searching, reading and retrieving citable evidence from
Aliyun official documentation:

- ``search_aliyun_docs``: search candidate docs via IQS UnifiedSearch.
- ``read_aliyun_doc``: read a single doc page (cached) via IQS ReadPageBasic.
- ``retrieve_aliyun_docs``: search + read + slice into ``Evidence[]`` objects.
"""

from .config import Config, get_config

__all__ = ["Config", "get_config"]
