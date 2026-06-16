"""ATA 内网搜索 MCP Tool"""
from mcp.server import Server
from src.core.internal_sites import InternalSiteAdapter
from src.tools.local_search import format_results


def register_ata_search(app: Server, ata_adapter: InternalSiteAdapter):
    """注册 ATA 搜索 tool"""

    @app.tool()
    async def search_ata(query: str, limit: int = 5) -> str:
        """搜索 ATA 内部技术文档平台（https://ata.atatech.org/）。

        搜索阿里内部 ATA 技术博客和文档。需要已完成 SSO 登录。
        如未登录，请先调用 internal_login 工具。

        Args:
            query: 搜索关键词
            limit: 返回结果数量上限，默认5条
        """
        if not await ata_adapter.is_authenticated():
            return "❌ ATA 未登录。请先调用 `internal_login` 工具完成 SSO 登录后重试。"
        try:
            results = await ata_adapter.search(query, limit=limit)
            if not results:
                return f"ATA 搜索 '{query}' 未找到结果。"
            return format_results(results)
        except Exception as e:
            return f"❌ ATA 搜索失败: {e}"
