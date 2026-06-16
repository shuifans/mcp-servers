"""MCP tools 注册模块"""
from src.tools.manage import register_manage_tools
from src.tools.local_search import register_local_search
from src.tools.ata_search import register_ata_search
from src.tools.yunzhidao_search import register_yunzhidao_search
from src.tools.public_search import register_public_search

__all__ = [
    "register_manage_tools",
    "register_local_search",
    "register_ata_search",
    "register_yunzhidao_search",
    "register_public_search",
]
