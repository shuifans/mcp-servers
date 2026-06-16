"""公网搜索 MCP Tool"""
from mcp.server import Server
from src.core.public_search import IQSSearchProvider
from src.tools.local_search import format_results


def register_public_search(app: Server, iqs_provider: IQSSearchProvider):
    """注册公网搜索 tool"""

    @app.tool()
    async def search_public(query: str, limit: int = 5) -> str:
        """搜索公网优质来源（AI 官方、云厂商、研究机构、行业权威媒体）。

        使用 IQS 搜索引擎检索公网内容，自动过滤 UGC 和低质量来源，
        优先返回 OpenAI/Anthropic/Google/阿里云/AWS 等权威源的结果。
        适合搜索英文术语、行业最佳实践、技术文档。

        Args:
            query: 搜索关键词（建议使用英文以获得更好的公网结果）
            limit: 返回结果数量上限，默认5条
        """
        if not iqs_provider:
            return "❌ 公网搜索未配置（IQS_ENDPOINT 或 IQS_API_KEY 为空）。"
        try:
            results = await iqs_provider.search(query, limit=limit)
            if not results:
                return f"公网搜索 '{query}' 未找到高质量结果。"
            return format_results(results)
        except Exception as e:
            return f"❌ 公网搜索失败: {e}"
