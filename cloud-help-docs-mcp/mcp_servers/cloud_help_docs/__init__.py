"""Unified cloud help docs MCP server.

This package implements an MCP (Model Context Protocol) server that exposes
three generic tools for searching, reading and retrieving citable evidence
from multiple cloud provider documentation sites:

- ``search_cloud_docs``: search candidate docs via IQS UnifiedSearch.
- ``read_cloud_doc``: read a single doc page (cached) via IQS ReadPageBasic.
- ``retrieve_cloud_docs``: search + read + slice into ``Evidence[]`` objects.

Supported providers: Aliyun, Volcengine, Tencent Cloud, AWS, Azure, GCP.
"""

from .config import Config, get_config

__all__ = ["Config", "get_config"]
