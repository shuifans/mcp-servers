"""云知道搜索 MCP Tool"""
from mcp.server import Server
from src.core.internal_sites import InternalSiteAdapter
from src.tools.local_search import format_results


def register_yunzhidao_search(app: Server, yunzhidao_adapter: InternalSiteAdapter):
    """注册云知道搜索 tool"""

    @app.tool()
    async def search_yunzhidao(query: str, limit: int = 5) -> str:
        """搜索云知道内部知识库（https://yunzhidao.alibaba-inc.com/）。

        搜索阿里内部云知道知识库文档。需要已完成 SSO 登录。
        如未登录，请先调用 internal_login 工具。

        Args:
            query: 搜索关键词
            limit: 返回结果数量上限，默认5条
        """
        if not await yunzhidao_adapter.is_authenticated():
            return "❌ 云知道未登录。请先调用 `internal_login` 工具完成 SSO 登录后重试。"
        try:
            results = await yunzhidao_adapter.search(query, limit=limit)
            if not results:
                return f"云知道搜索 '{query}' 未找到结果。"
            return format_results(results)
        except Exception as e:
            return f"❌ 云知道搜索失败: {e}"
